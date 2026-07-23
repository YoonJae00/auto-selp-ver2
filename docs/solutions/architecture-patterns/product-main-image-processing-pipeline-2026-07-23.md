---
title: "Product Main Image Processing Pipeline"
date: "2026-07-23"
category: "docs/solutions/architecture-patterns"
module: "processor"
problem_type: "architecture_pattern"
component: "main_image_processing"
severity: "medium"
applies_when:
  - "대표이미지 가공 흐름을 운영하거나 수정할 때"
  - "이미지 worker 분리 또는 확장을 판단할 때"
tags:
  - "celery"
  - "rembg"
  - "isnet"
  - "product-image"
  - "docker"
---

# Product Main Image Processing Pipeline

## Context

도매 상품의 대표사진은 여러 판매자가 동일하게 사용하는 경우가 많아 상품 차별화가 어렵다. 이 파이프라인은 원본 상품의 형태를 유지하면서 전경을 분리하고 밝은 스튜디오 배경에 다시 합성해 별도의 대표이미지를 만든다.

목표는 상품 보존형 이미지 가공과 원본 대비 검수 흐름이다. 새로운 상품 형태를 생성하거나 촬영 각도를 바꾸는 생성형 이미지 기능이 아니며, 판매 채널의 상품 묶임 방지를 보장하지 않는다.

## Current Architecture

대표이미지 가공은 별도 HTTP 마이크로서비스가 아니라 기존 processor와 동일한 Dockerfile·빌드 컨텍스트를 사용하는 Celery 프로세스·큐 분리 방식이다.

```text
Frontend Stage 3
  -> Processor API: POST /products/process-main-images
  -> Redis: image queue
  -> image-worker: concurrency=1
       -> 원본 URL 검증 및 다운로드
       -> cached IS-Net session으로 전경 분리
       -> 스튜디오 배경 합성
       -> uploads_data에 JPEG 원자적 저장
       -> Product 상태 갱신 및 marketplace draft refresh
  -> 기존 task polling으로 진행 상태 조회

Frontend / Marketplace snapshot
  -> Processor API의 인증된 가공 이미지 URL
  -> uploads_data의 실제 JPEG
```

### Container and Storage Roles

| 구성 요소 | 역할 | 큐/동시성 | 공유 저장소 |
|---|---|---|---|
| `processor` | FastAPI 요청 검증, 작업 생성, 상태·통계·이미지 조회 | 작업을 `image` 큐로 발행 | `uploads_data:/app/uploads` |
| `worker` | 기존 상품 가공 작업 실행 | `processor` 큐 | `uploads_data:/app/uploads` |
| `image-worker` | CPU 배경제거와 이미지 합성 실행 | `image` 큐, concurrency 1 | `uploads_data:/app/uploads`, `U2NET_HOME=/app/uploads/.u2net` |
| Redis | Celery broker와 결과 backend | 큐·작업 상태 전달 | 해당 없음 |

세 processor 계열 컨테이너는 `./services/processor`의 Dockerfile과 코드를 공유한다. `U2NET_HOME`은 rembg의 범용 모델 캐시 경로이며 IS-Net 모델 파일도 이 위치에 보존된다.

## Processing Sequence

1. 프런트엔드 Stage 3에서 기본 상품 가공이 완료됐고 대표 원본 URL이 있는 상품을 선택한다.
2. `POST /products/process-main-images`가 인증, 상품 소유권, `Product.status == "completed"`, 첫 유효 이미지 URL 존재 여부를 검사한다.
3. API는 `ProcessingTask` 소유권 레코드를 저장하고 Celery 작업을 `queue="image"`로 발행한다.
4. image-worker는 상품을 직렬 처리한다. 각 상품의 상태를 `processing`으로 저장한 뒤 원본 URL을 검증하고 다운로드한다.
5. `process_main_image`가 캐시된 IS-Net 세션으로 전경을 분리하고 마스크를 검증한 뒤 1000x1000 스튜디오 이미지로 합성한다.
6. 결과를 임시 파일에 쓴 다음 `/app/uploads/processed/{user_id}/{product_id}.jpg`로 원자적으로 교체한다.
7. 성공한 상품은 `completed`와 결과 경로를 저장한 뒤 marketplace draft refresh를 요청한다. 상품별 완료 결과와 진행률은 기존 Celery polling metadata로 전달된다.
8. 프런트엔드는 인증된 GET API로 원본과 가공 결과를 비교한다. 서버 측 `image_processing_status` 필터가 페이지네이션 전체에 적용되며, 실패 상품은 원본 이미지와 함께 `확인 필요`로 표시한다.
9. marketplace snapshot은 DB 상태, 예상 UUID 경로, 실제 파일 존재를 모두 확인한 경우에만 첫 이미지를 가공 URL로 교체한다. 추가 원본 이미지는 유지하며 조건이 맞지 않으면 전체 원본 목록으로 복귀한다.

## Data Model and API Contract

`Product`에는 다음 두 필드가 있다.

- `image_processing_status`: `not_started`, `processing`, `completed`, `failed`
- `processed_image_path`: 서버 내부 절대 경로

`processed_image_path`와 경로 검증에 필요한 `user_id`는 `ProductResponse` 직렬화에서 제외한다. 클라이언트에는 상태와, 완료 상태·예상 경로·실제 파일이 모두 유효할 때만 상대 URL인 `processed_main_image_url`을 제공한다.

| 계약 | 동작 |
|---|---|
| `POST /products/process-main-images` | 선택 상품 검증 후 `task_id`, `total`을 반환하고 image 큐에 발행 |
| `GET /products/{product_id}/processed-main-image` | 인증·소유권·완료 상태·정확한 UUID 경로·파일 존재 확인 후 JPEG 반환 |
| `GET /products` | `image_processing_status` 서버 측 필터를 목록과 전체 count에 동일 적용 |
| `GET /products/stats` | `image_completed`, `image_failed` 집계 제공 |
| `GET /status/{task_id}` | 기존 `ProcessingTask` 소유권과 Celery progress/result 계약 사용 |

## Security and Quality Guards

원본 이미지 URL은 신뢰하지 않는다.

- HTTP(S)만 허용하고 URL credentials를 거부한다.
- 최초 URL과 각 redirect 목적지의 DNS를 확인해 global IP가 아닌 주소를 거부한다.
- 환경 proxy를 신뢰하지 않으며 redirect를 자동 추적하지 않는다.
- JPEG, PNG, WebP MIME과 디코딩 포맷만 허용한다.
- 다운로드는 최대 20MB, 디코딩 이미지는 최대 40MP, 짧은 변은 최소 500px이다.
- EXIF orientation을 적용한 뒤 배경제거를 실행한다.

분리된 alpha mask는 전경 비율 5~95% 범위와 유효 bounding box를 만족해야 한다. 전경은 비율을 유지해 최대 820x820 안에 배치하고 결정적인 세 가지 밝은 배경 중 하나와 alpha 기반 그림자를 합성한다. 결과는 1000x1000 RGB JPEG, quality 90, progressive, subsampling 0이다.

모델 선택 근거와 CPU 실측은 [Main Image Background Removal Model Selection](./main-image-background-removal-model-selection-2026-07-23.md)에 기록한다.

## Failure and Cleanup Policy

- 한 상품의 다운로드, 배경제거, 품질 검사 또는 저장 실패는 해당 상품만 `failed`로 만들고 배치를 계속한다.
- 실패 정보는 `main_image_processing` stage/key의 processing warning으로 합쳐지며 원본 `images_list`는 덮어쓰지 않는다.
- draft refresh는 이미지 저장 성공 후에만 요청한다. refresh 요청 실패는 기록하지만 이미 완료된 이미지 상태를 실패로 되돌리지 않는다.
- 파일 저장은 동일 디렉터리의 임시 파일과 `os.replace`를 사용해 부분 파일 노출을 막는다.
- 도매 원본 `images_list`가 바뀌면 이미지 상태와 경로를 초기화하고 이전 결과 파일을 best-effort로 삭제한다.
- 상품 삭제가 완료되면 해당 사용자·상품 UUID에서 계산한 결과 파일을 best-effort로 삭제한다.
- DB 상태가 완료여도 볼륨 파일이 없으면 응답 URL을 내보내지 않고 marketplace snapshot도 원본으로 복귀한다.

## Operational Characteristics

현재 구성은 단일 Docker 엔진과 단일 named volume을 전제로 한다. API와 image-worker가 같은 `uploads_data`를 공유하므로 별도 object storage나 이미지 HTTP 서비스가 필요하지 않다. 모델 cache와 결과 파일은 컨테이너 재시작 후에도 named volume에 남는다.

image-worker에는 Docker CPU·memory hard limit이 없으며 다른 컨테이너와 host resource를 공유한다. 현재 보호 장치는 전용 큐와 concurrency 1이다. 따라서 동시에 여러 이미지를 처리해 처리량을 높이는 구성보다 한 작업이 메모리 안에서 끝나는 것을 우선한다.

다중 호스트, GPU·원격 inference worker, 사용자 증가 또는 처리량 SLA가 실제 요구가 되면 S3 호환 object storage와 remote image worker를 함께 재검토한다. 그 전에는 단일 서버 구성을 유지한다.

## Verification

백엔드 계약과 이미지 유틸리티 검증:

```bash
PYTHONPATH=services/processor python -m pytest -q \
  services/processor/tests/test_main_image.py \
  services/processor/tests/test_marketplace_snapshot.py \
  services/processor/tests/test_task_access.py
```

결과는 25 passed였다. `test_main_image.py`는 정확한 `isnet-general-use` 모델명, 세션 cache 재사용, 합성 결과, 품질 gate, 인증·소유권·파일 guard, 상품별 실패 격리를 검증한다.

추가로 다음 검증이 통과했다.

```bash
npm --prefix frontend run build
npm --prefix frontend run lint
docker compose config --quiet
docker compose build image-worker
docker compose run --rm --no-deps image-worker \
  python -c "import rembg; from PIL import Image"
```

실제 `frontend/public/product-assortment.webp` 1536x1024 샘플도 IS-Net 배경제거와 1000x1000 JPEG 생성을 완료했다. 저장소 전체 DB 통합 테스트의 통과를 의미하지는 않는다.

## Related

- `services/processor/main.py`
- `services/processor/tasks.py`
- `services/processor/utils/main_image.py`
- `services/processor/models.py`
- `services/processor/schemas.py`
- `services/processor/tests/test_main_image.py`
- `frontend/src/app/(ai-mall)/process/page.tsx`
- `docker-compose.yml`
- [Main Image Background Removal Model Selection](./main-image-background-removal-model-selection-2026-07-23.md)
