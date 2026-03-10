# HTML Report Serving — Plan Document

> **Summary**: HTML 인사이트 리포트를 파일 다운로드 대신 임시 URL로 서빙하여 Slack UX 개선
>
> **Project**: amz_researcher
> **Author**: CTO
> **Date**: 2026-03-10
> **Status**: Draft

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Slack에서 HTML 파일 다운로드 → 로컬에서 열기 UX가 불편함. 모바일에서 특히 접근성 저하 |
| **Solution** | 리포트를 파일시스템에 저장하고 FastAPI 엔드포인트로 30일간 URL 서빙 |
| **Function UX Effect** | Slack 메시지의 링크 클릭 한 번으로 브라우저에서 즉시 리포트 열람 |
| **Core Value** | 리포트 공유·접근의 마찰 제거, 모바일 포함 모든 디바이스에서 원클릭 접근 |

---

## 1. Overview

### 1.1 Purpose

현재 HTML 인사이트 리포트는 Slack에 파일로 업로드되어, 사용자가 다운로드 후 브라우저에서 열어야 한다. 이를 서버에서 직접 서빙하는 방식으로 변경하여, Slack 메시지에 포함된 URL 클릭만으로 즉시 열람 가능하게 한다.

### 1.2 Background

- 기존 `html-insight-report` Plan에서 "호스팅 페이지 (URL 공유 방식)"를 Out of Scope / Phase 2로 분류했음
- 현재 HTML 리포트는 self-contained (~300KB 이하)로 이미 구현 완료
- FastAPI 서버가 이미 운영 중이므로 엔드포인트 추가만으로 구현 가능
- 조회 빈도가 낮아 고가용성/캐시 인프라 불필요

### 1.3 Related Documents

- `docs/01-plan/features/html-insight-report.plan.md` (원본 HTML 리포트 Plan)
- `amz_researcher/services/html_report_builder.py` (현재 HTML 생성기)
- `amz_researcher/orchestrator.py` (리포트 생성 → Slack 전달 흐름)

---

## 2. Scope

### 2.1 In Scope

- [ ] 파일시스템 기반 리포트 저장 서비스 (`report_store.py`)
- [ ] `GET /reports/{report_id}` 서빙 엔드포인트
- [ ] 30일 TTL — 만료 파일 자동 정리
- [ ] Slack 메시지에 리포트 URL 포함 (파일 업로드 대체)
- [ ] 카테고리 분석 + 키워드 검색 분석 양쪽 적용

### 2.2 Out of Scope

- 인증/접근 제어 (UUID 추측 불가로 충분)
- CDN / S3 외부 저장소
- 리포트 목록 조회 API
- PDF 변환

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | 리포트 생성 시 `data/reports/{uuid}.html` 파일로 저장 | Must |
| FR-02 | `GET /reports/{uuid}` 엔드포인트로 HTML 응답 (Content-Type: text/html) | Must |
| FR-03 | 존재하지 않는 report_id 요청 시 404 응답 | Must |
| FR-04 | Slack 메시지에 `{WEBHOOK_BASE_URL}/reports/{uuid}` 링크 포함 | Must |
| FR-05 | 30일 경과 파일 자동 삭제 (서버 startup 시 정리) | Must |
| FR-06 | 기존 Slack 파일 업로드(HTML) 제거, Excel 업로드는 유지 | Should |
| FR-07 | 리포트 저장 실패 시 fallback으로 기존 파일 업로드 방식 사용 | Should |

### 3.2 Non-Functional Requirements

| Category | Criteria |
|----------|----------|
| Storage | 리포트 1개 < 300KB, 30일 최대 ~150개 = ~45MB |
| Performance | 서빙 응답 < 100ms (파일 읽기) |
| Availability | 서버 재시작 시 기존 리포트 유지 (파일시스템) |
| Security | UUID v4로 URL 추측 불가 (122bit entropy) |

---

## 4. Architecture Decision

### 4.1 저장 방식

| Option | Pros | Cons | Decision |
|--------|------|------|:--------:|
| **파일시스템** (`data/reports/`) | 서버 재시작에 안전, 구현 간단, OS 레벨 캐시 | Docker 볼륨 마운트 필요 | **Selected** |
| 메모리 dict | 가장 간단 | 서버 재시작 시 소실 | - |
| MySQL BLOB | 가장 안정적 | 300KB blob 과잉, DB 부하 | - |

**전제**: Docker 배포 시 `data/reports/` 디렉토리를 볼륨 마운트한다.

### 4.2 TTL 정리 방식

| Option | Pros | Cons | Decision |
|--------|------|------|:--------:|
| **Startup 정리** | 구현 간단, 별도 스케줄러 불필요 | 장기 무재시작 시 정리 지연 | **Selected** |
| Background 주기 정리 | 정확한 TTL | asyncio task 관리 필요 | Phase 2 |
| Cron job | 서버 외부에서 관리 | 인프라 추가 | - |

서버 재배포 주기가 잦으므로 startup 정리로 충분하다.

### 4.3 Slack 전달 방식 변경

```
Before:
  slack.upload_file(html_bytes, "*.html")  → 파일 다운로드 필요

After:
  report_url = report_store.save(html_bytes, keyword)
  slack.send_message(..., "📊 리포트: {report_url}")  → 클릭 즉시 열림
```

---

## 5. Implementation Plan

### 5.1 신규 파일

| File | Role |
|------|------|
| `amz_researcher/services/report_store.py` | 리포트 저장/조회/정리 서비스 |

### 5.2 변경 파일

| File | Changes |
|------|---------|
| `amz_researcher/router.py` | `GET /reports/{report_id}` 엔드포인트 추가 |
| `amz_researcher/orchestrator.py` | `upload_file(html)` → `report_store.save()` + URL 링크 전달 |
| `main.py` | 없음 (amz_router에 이미 포함) |
| `app/config.py` | `REPORT_TTL_DAYS: int = 30`, `REPORT_DIR: str = "data/reports"` 설정 추가 |

### 5.3 구현 순서

1. `report_store.py` — save / get / cleanup 구현
2. `app/config.py` — 설정 추가
3. `router.py` — GET 엔드포인트 추가
4. `orchestrator.py` — 리포트 저장 + Slack 메시지에 URL 포함 (2곳: `run_analysis`, `_run_keyword_analysis_pipeline`)
5. startup 이벤트에 cleanup 등록

---

## 6. API Design

### GET /reports/{report_id}

```
Request:  GET /reports/{report_id}
Response: 200 OK, Content-Type: text/html, body: HTML content
          404 Not Found (만료 또는 미존재)
```

---

## 7. report_store.py 핵심 인터페이스

```python
class ReportStore:
    def __init__(self, base_dir: str, ttl_days: int = 30): ...

    def save(self, html_bytes: bytes, label: str = "") -> str:
        """HTML 저장, report_id(uuid) 반환."""

    def get(self, report_id: str) -> bytes | None:
        """report_id로 HTML 조회. 없으면 None."""

    def cleanup_expired(self) -> int:
        """TTL 초과 파일 삭제, 삭제 건수 반환."""
```

---

## 8. Risks and Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Docker 볼륨 미마운트 시 재배포로 파일 소실 | Medium | 배포 설정에 볼륨 마운트 명시, fallback으로 파일 업로드 유지 |
| 디스크 용량 초과 (극단적 사용) | Low | 30일 TTL + 300KB 제한 = 최대 ~45MB |
| UUID 충돌 | Negligible | UUID v4 충돌 확률 무시 가능 |
| WEBHOOK_BASE_URL 미설정 시 링크 깨짐 | Medium | 설정 누락 시 fallback으로 파일 업로드 |

---

## 9. Success Criteria

- [ ] Slack 메시지의 URL 클릭으로 브라우저에서 리포트 즉시 열림
- [ ] 카테고리 분석 + 키워드 검색 분석 모두 URL 서빙 적용
- [ ] 30일 경과 리포트 자동 정리 확인
- [ ] 기존 Excel 파일 업로드 정상 유지 (regression 없음)
- [ ] WEBHOOK_BASE_URL 미설정 시 기존 방식으로 fallback

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-10 | Initial draft | CTO |
