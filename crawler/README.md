# Auto-Selp Crawler

도매처 사이트에서 상품 데이터를 자동 수집하고 품절을 모니터링하는 크로스플랫폼 데스크톱 앱입니다.

## 주요 기능

- **도매처 관리**: 사이트별 로그인 계정, 어댑터, 모니터링 주기 설정
- **LLM 어댑터 빌더**: 신규 도매처 사이트를 LLM(OpenAI GPT)으로 분석하여 크롤링 어댑터 YAML 자동 생성
- **카테고리 크롤링**: 전체상품/카테고리 트리 선택 후 자동 수집 (의존 옵션 지원)
- **품절 모니터링**: 주기적 재크롤링으로 품절/복구/가격변동 감지
- **엑셀 내보내기**: Auto-Selp 표준 스키마(`products`/`product_options`) 엑셀 출력 → 기존 `/upload`와 연동
- **QML 데스크톱 UI**: 사이드바 내비게이션, 작업 공간, 공유 상세 패널, 시스템 테마/감소된 모션/적응형 효과 지원
- **Windows 지원**: 시스템 Edge/Chrome 사용, PyInstaller + Inno Setup 인스톨러 배포

## 시스템 요구사항

### Windows
- Windows 10 64비트 이상
- Microsoft Edge 또는 Google Chrome 설치됨
- 인터넷 연결 (LLM 사이트 분석 시)

### macOS (개발자용)
- macOS 12+
- Python 3.11+
- Microsoft Edge 또는 Google Chrome 설치됨

## 설치 (개발 환경)

```bash
cd crawler
python3.11 -m venv .venv
source .venv/bin/activate    # macOS
# .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt
playwright install chromium   # 폴백용 (시스템 Edge/Chrome 우선 사용)
```

## 실행

```bash
cd crawler
source .venv/bin/activate
python main.py
```

첫 실행 시 앱 안의 초기 설정 화면이 표시됩니다:
1. OpenAI API 키 입력
2. 브라우저 채널 확인 (Edge 권장)
3. 설정을 완료하면 사이드바 기반 작업 공간으로 이동

## 사용 순서

### 1. 도매처 등록 (도매처 작업 공간)
- "새 도매처 추가" 버튼
- 도매처명, 웹사이트 URL, 로그인 계정 입력
- 어댑터가 없으면 어댑터 빌더에서 생성

### 2. 어댑터 생성 (어댑터 스튜디오)
- 도매처명, 메인 URL, (선택) 목록/상세 URL 입력
- "1. 사이트 프로브" → DOM 구조 자동 분석
- "2. LLM 어댑터 생성" → OpenAI GPT가 YAML 어댑터 생성
- YAML 에디터에서 내용 확인/수정
- "3. 어댑터 저장"

### 3. 크롤링 실행 (크롤링 작업 공간)
- 도매처 선택 → "카테고리 탐색"
- 카테고리 트리에서 크롤링할 항목 체크
- 최대 페이지, 지연 설정
- "크롤링 시작"

### 4. 내보내기 (내보내기 작업 공간)
- 도매처 선택 (또는 전체)
- "엑셀로 내보내기" → 파일 저장
- 저장된 엑셀을 Auto-Selp `/upload` 페이지에서 업로드

### 5. 품절 모니터링 (모니터 작업 공간)
- 도매처 등록 시 "품절 모니터링 활성화" 체크
- 주기(6/12/24시간) 설정
- 품절/복구/가격변동 이력을 대시보드에서 확인

## 설정 (설정 작업 공간)

| 설정 | 설명 |
| --- | --- |
| LLM 제공자 | OpenAI (gpt-5.6-luna, reasoning medium) |
| LLM API 키 | OS 키체인에 안전 저장 |
| 브라우저 채널 | msedge(권장) / chrome / chromium |
| 전역 지연 | 페이지/상품 사이 대기 시간 (0-10초, 기본 0초) |
| 업데이트 확인 | GitHub Release에서 최신 버전 확인 |

## Windows 빌드

```bash
# PyInstaller
pyinstaller build_windows.spec

# Inno Setup 인스톨러 (Inno Setup 설치 필요)
iscc installer.iss

# 결과: dist/AutoSelpCrawler-Setup-0.1.0.exe
```

GitHub Actions(`crawler-v*` 태그 푸시 시)에서 Windows 빌드 및 인스톨러 생성이 자동으로 이루어집니다.

### Windows 검증 대상

- Windows 10 64비트: Edge 설치 환경에서 실행, 초기 설정 화면, 사이드바 내비게이션, 크롤링/내보내기 기본 흐름 확인
- Windows 11 64비트: 시스템 라이트/다크 테마 연동, 감소된 모션 설정, Mica/반투명 효과의 안전한 폴백 확인
- Windows 10/11 공통: PyInstaller 배포본에서 QML 화면과 assets가 로드되고 `global.qss` 없이 시작되는지 확인
- 릴리스 전 macOS, Windows 10, Windows 11 체크리스트는 `docs/qml-ui-release-checklist.md`에 기록합니다. Windows는 100%, 125%, 150%, 200% 배율 조합을 포함합니다.

## 데이터 저장 위치

| OS | 경로 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\auto-selp-crawler\` |
| macOS | `~/Library/Application Support/auto-selp-crawler/` |

## 보안

- 로그인 계정과 LLM API 키는 OS 키체인(Windows Credential Manager / macOS Keychain)에 저장됩니다.
- 데이터베이스에는 자격증명 값이 저장되지 않으며, 키체인 참조 키만 저장됩니다.
- 어댑터 YAML 파일에 자격증명이 포함되지 않습니다.

## 테스트

```bash
cd crawler
source .venv/bin/activate
python -m pytest tests/ -v
```

## 기술 스택

- PySide6 (Qt Quick/QML for Python) - GUI
- Playwright - 브라우저 자동화
- SQLAlchemy + SQLite - 로컬 저장
- keyring - 자격증명 관리
- APScheduler - 품절 모니터링 스케줄
- google-generativeai / openai - LLM 사이트 분석
- openpyxl - 엑셀 출력
- PyInstaller + Inno Setup - Windows 배포
