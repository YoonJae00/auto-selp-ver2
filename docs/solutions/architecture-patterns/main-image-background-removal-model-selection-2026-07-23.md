---
title: "Main Image Background Removal Model Selection"
date: "2026-07-23"
category: "docs/solutions/architecture-patterns"
module: "processor"
problem_type: "architecture_decision"
component: "main_image_processing"
severity: "medium"
applies_when:
  - "CPU 기반 상품 대표이미지 배경제거 모델을 선택하거나 교체할 때"
tags:
  - "rembg"
  - "isnet"
  - "background-removal"
  - "onnxruntime"
  - "product-image"
---

# Main Image Background Removal Model Selection

## Context

도매 상품의 대표사진은 여러 판매자가 동일하게 사용하는 경우가 많다. 판매 채널에서 동일 이미지가 함께 식별되거나 묶이면 상품 차별화가 어려워질 수 있다. 상품 형태를 왜곡할 수 있는 생성형 각도 변경 대신, 원본 상품의 전경을 분리해 밝은 스튜디오 배경에 다시 합성하는 방식을 선택했다.

운영 환경은 GPU가 없는 로컬 CPU Docker이며 이미지 작업은 전용 `image` 큐에서 concurrency 1로 실행된다. 따라서 모델 선택에서는 경계 품질뿐 아니라 제한된 메모리 안에서 실제 추론이 끝나는지가 필수 조건이다.

## Decision

대표이미지 배경제거 모델로 rembg 2.0.77의 `isnet-general-use`를 사용한다. 구현 위치는 `services/processor/utils/main_image.py`이며, `@lru_cache(maxsize=1)`로 rembg 세션을 프로세스당 한 번 생성해 상주 워커에서 재사용한다.

`U2NET_HOME`은 U2Net 전용 설정명이 아니라 rembg가 모델 파일 전반에 사용하는 공식 캐시 환경 변수다. 모델을 IS-Net으로 바꾸더라도 이름과 저장 경로를 유지한다.

## Candidate Comparison

| 후보 | 발표 시점 | ONNX 크기 | 판단 |
|---|---:|---:|---|
| U2Net | 2020 | 175,997,641 bytes | 기존 기준선이지만 상대적으로 오래된 모델이다. |
| BiRefNet General Lite | 2024 | 224,005,088 bytes | 경계 품질이 우수한 후보지만 실제 CPU Docker 추론에서 OOM이 발생했다. |
| IS-Net General Use | 2022, ECCV | 178,648,008 bytes | U2Net과 크기가 거의 같고, 1024 입력 adaptation과 intermediate supervision으로 세밀한 경계를 개선했으며 실제 환경을 통과했다. |

`u2netp`와 `silueta`는 더 작지만, 이번 목표인 U2Net 대비 품질 개선을 뒷받침할 근거가 부족해 제외했다.

## Measured Results

측정 당시 Docker 엔진에 할당된 총 메모리는 8,217,145,344 bytes였다. 입력은 저장소의 `frontend/public/product-assortment.webp` 한 장이며 해상도는 1536x1024였다.

- BiRefNet 기본 설정: 모델 다운로드 후 추론 중 exit 137로 종료됐다.
- BiRefNet 저메모리 설정: ONNX 최적화 비활성화, CPU arena와 memory pattern 비활성화, sequential 실행, thread 1 조건에서 세션 생성은 3.90초와 RSS 874,836KB로 성공했지만 추론 중 exit 137로 종료됐다.
- IS-Net: 최초 모델 다운로드와 세션 생성에 32.10초, 배경제거 추론에 1.67초가 걸렸으며 343,643-byte PNG를 정상 생성했다.
- IS-Net 전체 대표이미지 가공: 새 프로세스 cold start에서 21.85초가 걸렸고, 최종 결과는 1000x1000 RGB JPEG 57,648 bytes였다. 상주 워커에서는 캐시된 세션을 재사용한다.

이 수치는 단일 저장소 샘플을 사용한 실측값이며 다양한 실상품의 평균 처리시간이나 품질을 대표하지 않는다.

## Why This Matters

모델 선택 기준은 이론상 품질을 최대화하는 것이 아니라 현재 메모리 안에서 정상 완료되는 모델 중 품질과 크기의 균형을 찾는 것이다. BiRefNet은 더 최신이고 경계 품질이 우수한 후보지만 현재 배포 환경에서는 저메모리 설정으로도 추론을 완료하지 못하므로 선택할 수 없다.

IS-Net은 절대적으로 최신인 발표 모델은 아니다. 다만 U2Net과 비슷한 파일 크기로 CPU 환경에서 정상 동작하며, 공식 자료의 U2Net 기반 176.6MB급 image component에 intermediate supervision과 1024 입력 adaptation을 적용한 현재 제약의 균형안이다.

## When to Reconsider

다음 조건 중 하나가 발생하면 BiRefNet 계열을 다시 평가한다.

- GPU 또는 외부 inference worker를 도입한다.
- 이미지 워커의 메모리 예산이 증가한다.
- 실상품 50~100개 품질검수에서 실패율이나 경계 품질이 허용 수준에 미달한다.
- 대표이미지 처리량 SLA를 충족하지 못한다.

## Verification

정확한 모델명과 세션 캐시 재사용은 `services/processor/tests/test_main_image.py`에서 실제 모델 다운로드 없이 검증한다.

```bash
PYTHONPATH=services/processor python -m pytest -q \
  services/processor/tests/test_main_image.py \
  services/processor/tests/test_marketplace_snapshot.py \
  services/processor/tests/test_task_access.py
```

검증 결과는 25 passed였으며 image-worker Docker 이미지 빌드도 통과했다.

## Sources

- [rembg models](https://github.com/danielgatis/rembg#models)
- [IS-Net paper](https://arxiv.org/abs/2203.03041)
- [IS-Net official repository](https://github.com/xuebinqin/DIS)
- [BiRefNet official repository](https://github.com/ZhengPeng7/BiRefNet)

## Related

- `services/processor/utils/main_image.py`
- `services/processor/tests/test_main_image.py`
- `docker-compose.yml`
