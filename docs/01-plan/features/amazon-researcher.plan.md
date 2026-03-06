# Plan: Amazon Keyword Ingredient Researcher

## 1. Overview

Amazon 키워드 기반 경쟁 제품 성분 분석 도구. Slack Slash Command(`/amz`)로 키워드를 입력하면, 아마존 검색 상위 30개 제품의 마케팅 강조 성분을 추출하고 시장 성과 기반 가중치를 부여하여 엑셀 보고서를 생성한다.

- **트리거**: Slack `/amz {keyword}` → FastAPI 엔드포인트
- **처리 시간**: 10~15분 (Background Task)
- **출력**: Slack 요약 메시지 + 엑셀 파일 업로드 (5개 시트)

## 2. Problem Statement

제품 기획 시 아마존 경쟁 분석을 수동으로 진행하면 수 시간이 소요된다. Browse.ai 크롤링 + Gemini Flash 성분 추출 + 가중치 계산을 자동화하여 슬랙 커맨드 한번으로 분석 결과를 제공한다.

## 3. Architecture Decision: 기존 프로젝트 통합

### 현재 프로젝트 구조

```
webhook-service/
├── main.py                    # FastAPI app
├── app/
│   ├── config.py              # Settings (pydantic-settings)
│   ├── router.py              # /webhook 엔드포인트 + job dispatcher
│   └── dependencies.py        # verify_webhook
├── jobs/                      # 동기 job 모듈들
│   ├── cash_mgmt.py
│   ├── meta_ads_manager.py
│   └── ...
└── lib/                       # 공통 라이브러리
    ├── slack.py               # SlackNotifier
    ├── mysql_connector.py
    └── google_sheet.py
```

### 통합 전략

스펙 문서의 독립 구조(`amz-researcher/`)를 기존 webhook-service에 **서브 패키지**로 통합한다.

**이유**:
1. 동일 FastAPI 서버에서 운영 → 인프라 비용 절감
2. Slack 관련 공통 라이브러리(`lib/slack.py`) 재사용 가능
3. 환경 변수 관리 일원화 (`app/config.py`)

### 계획 파일 구조

```
webhook-service/
├── main.py                          # amz_router include 추가
├── app/
│   ├── config.py                    # AMZ_* 환경 변수 추가
│   └── router.py                    # 기존 유지
├── amz_researcher/                  # 신규 서브 패키지
│   ├── __init__.py
│   ├── router.py                    # POST /slack/amz, POST /research
│   ├── services/
│   │   ├── __init__.py
│   │   ├── browse_ai.py            # Browse.ai API 호출 + polling
│   │   ├── gemini.py               # Gemini Flash 성분 추출
│   │   ├── analyzer.py             # 가중치 계산 + 데이터 가공
│   │   ├── excel_builder.py        # openpyxl 엑셀 생성 (5시트)
│   │   └── slack_sender.py         # response_url 메시지 + 파일 업로드
│   ├── models.py                    # Pydantic 모델 (SearchResult, ProductDetail 등)
│   └── orchestrator.py              # run_research: 전체 파이프라인 조율
└── lib/                             # 기존 유지
```

**핵심 결정**:
- `amz_researcher/` 패키지를 프로젝트 루트에 배치 (jobs/ 하위가 아닌 독립 패키지)
- 기존 `jobs/`는 동기 함수 + webhook dispatcher 패턴이나, amazon researcher는 **async Background Task** 기반으로 동작하므로 별도 패키지가 적합
- Slack 파일 업로드는 기존 `lib/slack.py`의 `SlackNotifier`와 역할이 다르므로 `slack_sender.py`로 분리

## 4. Feature Requirements

### FR-01: Slack Slash Command 엔드포인트
- `POST /slack/amz` (application/x-www-form-urlencoded)
- 즉시 200 응답 반환 (Slack 3초 타임아웃 대응)
- BackgroundTasks로 `run_research` 실행
- 키워드 누락 시 에러 메시지 즉시 반환

### FR-02: Browse.ai 검색 로봇 연동
- 검색 로봇 실행 (`AMZ_SEARCH_ROBOT_ID`)
- Polling: 30초 간격, 최대 20회 (10분)
- `failed` + `retriedByTaskId` → 자동 retry task 추적
- 결과에서 상위 30개 ASIN 추출 (`_STATUS !== "REMOVED"`, `Position !== null`)

### FR-03: Browse.ai 상세 로봇 연동
- 30개 ASIN에 대해 상세 로봇 실행 (`AMZ_DETAIL_ROBOT_ID`)
- 병렬 실행 + 개별 polling
- 일부 실패 허용 (성공 건만 진행)

### FR-04: Gemini Flash 성분 추출
- 30개 제품 데이터를 단일 API 호출로 처리
- `responseMimeType: "application/json"` 으로 JSON 강제
- 성분명 영문 표준명 통일 + 카테고리 분류
- JSON 파싱 실패 시 1회 retry

### FR-05: 가중치 계산
- 복합 가중치: Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
- 각 요소 0~1 정규화
- 성분별 집계: Weighted Score, # Products, Avg Weight, Avg Price, Price Range

### FR-06: 엑셀 생성 (5개 시트)
1. **Ingredient Ranking** — 성분별 가중치 순위 + Key Insight
2. **Category Summary** — 카테고리별 집계
3. **Product Detail** — 제품별 상세 + 추출 성분
4. **Raw - Search Results** — 검색 원본
5. **Raw - Product Detail** — 상세 크롤링 원본
- 스타일: 남색 헤더, 교대행 색상, freeze panes, 숫자 포맷
- 레퍼런스 엑셀(`hair_serum_ingredient_analysis.xlsx`) 품질 재현

### FR-07: Slack 출력
- 진행 상태 메시지 (response_url): 검색 시작 → 검색 완료 → 성분 추출 중
- 최종 요약 메시지: Top 10 성분 + Score + 제품 수 + 평균가
- 엑셀 파일 업로드 (Slack Bot Token + files.upload API)

### FR-08: 로컬 테스트 엔드포인트
- `POST /research` (application/json)
- curl로 테스트 가능한 JSON 엔드포인트

## 5. Environment Variables (신규)

```
AMZ_BROWSE_AI_API_KEY=        # Browse.ai API 키
AMZ_GEMINI_API_KEY=           # Gemini API 키
AMZ_BOT_TOKEN=xoxb-...       # Slack Bot Token (파일 업로드용)
AMZ_SEARCH_ROBOT_ID=          # Browse.ai 검색 로봇 ID
AMZ_DETAIL_ROBOT_ID=          # Browse.ai 상세 로봇 ID
```

모든 환경 변수에 `AMZ_` 접두어 사용.

## 6. Tech Stack (추가 의존성)

| 패키지 | 용도 |
|--------|------|
| `httpx` | async HTTP 클라이언트 (Browse.ai, Gemini, Slack API) |
| `openpyxl` | 엑셀 생성 |

기존 프로젝트에 `httpx`는 이미 설치되어 있음. `openpyxl` 추가 필요.

## 7. Implementation Order

| Phase | 작업 | 의존성 |
|-------|------|--------|
| 1 | `app/config.py`에 AMZ_* 설정 추가 + `amz_researcher/models.py` | 없음 |
| 2 | `amz_researcher/services/browse_ai.py` | Phase 1 |
| 3 | `amz_researcher/services/gemini.py` | Phase 1 |
| 4 | `amz_researcher/services/analyzer.py` | Phase 1 |
| 5 | `amz_researcher/services/excel_builder.py` | Phase 4 |
| 6 | `amz_researcher/services/slack_sender.py` | Phase 1 |
| 7 | `amz_researcher/orchestrator.py` | Phase 2~6 |
| 8 | `amz_researcher/router.py` + `main.py` 연동 | Phase 7 |

## 8. Error Handling Strategy

| 상황 | 대응 |
|------|------|
| Browse.ai 검색 실패 (retry 없음) | Slack 에러 메시지 전송, 작업 종료 |
| Browse.ai polling 타임아웃 (10분) | Slack 타임아웃 메시지, 작업 종료 |
| 상세 크롤링 일부 실패 | 성공 건만 진행, 실패 수 Slack 안내 |
| Gemini JSON 파싱 실패 | 1회 retry, 실패 시 빈 성분 처리 |
| 키워드 누락 | 즉시 에러 응답 반환 |

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Browse.ai API 불안정 | 크롤링 실패 | retry 추적 + polling 타임아웃 |
| Gemini 응답 비정형 | 성분 추출 실패 | JSON 강제 + retry 1회 |
| 30개 상세 크롤링 동시 실행 | Browse.ai rate limit | 동시 실행 수 제한 (semaphore) |
| Slack 3초 타임아웃 | 응답 지연 | 즉시 200 반환 + BackgroundTasks |

## 10. Success Criteria

- [ ] `/amz hair serum` 실행 시 10~15분 내 엑셀 리포트 Slack 전달
- [ ] 5개 시트 모두 레퍼런스 엑셀과 동일한 품질
- [ ] 에러 발생 시 Slack으로 상태 안내
- [ ] 기존 webhook-service 기능에 영향 없음
