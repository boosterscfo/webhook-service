# Amazon 키워드 성분 분석 도구 — 개발 스펙

## 1. 목적

제품 개발 시 아마존에서 특정 키워드(예: hair serum, toner pad)를 검색하여,
경쟁 제품들이 마케팅에서 강조하는 **성분(ingredient)**을 추출하고,
시장 성과(검색 순위, 리뷰 수, 평점, 구매량) 기반 **가중치**를 부여하여
어떤 성분이 시장에서 가장 유효한지를 한눈에 파악할 수 있게 해주는 도구.

일회성 리서치 도구 — 제품 기획 단계에서 슬랙 커맨드 한번으로 실행.

---

## 2. 전체 아키텍처

```
Slack (/amz hair serum)
  → FastAPI 서버 (POST /slack/amz)
    → 즉시 200 + 접수 메시지 반환 (Slack 3초 타임아웃 대응)
    → BackgroundTasks:
        ① Browse.ai 검색 로봇 실행 + polling (retry 대응)
        ② 검색 결과 파싱 (상위 30개 ASIN 추출)
        ③ Browse.ai 상세 로봇 실행 + polling (30개)
        ④ Gemini Flash로 성분 일괄 추출
        ⑤ 가중치 계산
        ⑥ 엑셀 파일 생성 (5개 시트)
        ⑦ Slack response_url로 요약 메시지 전송
        ⑧ Slack API로 엑셀 파일 업로드
```

n8n 불필요 — Slack Slash Command가 FastAPI를 직접 호출.

### Slack Slash Command 설정
- Command: `/amz`
- Request URL: `https://{서버도메인}/slack/amz`

### FastAPI 엔드포인트 설계

Slack Slash Command는 `application/x-www-form-urlencoded` 형태로 전송:

```python
@app.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),              # 키워드
    response_url: str = Form(""),      # 지연 응답 URL
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    # 즉시 응답 (3초 내)
    background_tasks.add_task(run_research, text, response_url, channel_id)
    return {
        "response_type": "in_channel",
        "text": f"🔍 *{text}* 검색 시작합니다. 약 10~15분 소요됩니다."
    }
```

---

## 3. API 스펙

### FastAPI 엔드포인트

Slack Slash Command는 `application/x-www-form-urlencoded`로 전송:

```
POST /slack/amz
Content-Type: application/x-www-form-urlencoded

text=hair+serum&response_url=https://hooks.slack.com/...&channel_id=C06PT07RK40&user_id=U03C4A8DVT4

Response: 200 OK (즉시 반환, Slack이 이 응답을 채널에 표시)
{
  "response_type": "in_channel",
  "text": "🔍 *hair serum* 검색 시작합니다. 약 10~15분 소요됩니다."
}
```

로컬 테스트용 엔드포인트 (curl로 테스트):

```
POST /research
Content-Type: application/json

{
  "keyword": "hair serum",
  "response_url": "https://hooks.slack.com/...",
  "channel_id": "C06PT07RK40"
}
```

### 환경 변수

```properties
AMZ_BROWSE_AI_API_KEY=
AMZ_GEMINI_API_KEY=
AMZ_BOT_TOKEN=xoxb-...        # Slack Bot Token (파일 업로드용, response_url로는 파일 못 보냄)
AMZ_SEARCH_ROBOT_ID=019cbd49-85aa-72bb-b5f5-ae97a1caabe0
AMZ_DETAIL_ROBOT_ID=019cbd6a-4448-7b63-acca-869c3a13afea
```

모든 환경 변수에 `AMZ_` 접두어 사용. 다른 서비스와 충돌 방지.

---

## 4. Browse.ai API 상세

### 검색 로봇 실행

```
POST https://api.browse.ai/v2/robots/{SEARCH_ROBOT_ID}/tasks
Authorization: Bearer {API_KEY}

{
  "inputParameters": {
    "amazon_url": "https://www.amazon.com/s?k=hair+serum"
  }
}
```

**주의**: 파라미터명이 `originUrl`이 아니라 `amazon_url`임.

### 상세 로봇 실행

```
POST https://api.browse.ai/v2/robots/{DETAIL_ROBOT_ID}/tasks
Authorization: Bearer {API_KEY}

{
  "inputParameters": {
    "originUrl": "https://www.amazon.com/dp/{ASIN}"
  }
}
```

상세 로봇은 `originUrl` 사용 (로봇마다 파라미터명이 다름).

### Task 상태 확인

```
GET https://api.browse.ai/v2/robots/{ROBOT_ID}/tasks/{TASK_ID}
Authorization: Bearer {API_KEY}
```

### 상태값
- `in-progress`: 진행 중 → 계속 polling
- `successful`: 완료 → 결과 사용
- `failed`: 실패 → `retriedByTaskId` 확인
  - 있으면: Browse.ai가 자동 retry한 새 task ID → 그 ID로 polling 전환
  - 없으면: 진짜 실패 → 에러 처리

### Polling 설계

```python
async def poll_task(robot_id, task_id, max_attempts=20, interval=30):
    current_id = task_id
    for i in range(max_attempts):
        await asyncio.sleep(interval)
        result = await check_task(robot_id, current_id)

        if result.status == "successful":
            return result
        elif result.status == "failed":
            if result.retriedByTaskId:
                current_id = result.retriedByTaskId  # retry task로 전환
                continue
            else:
                raise Exception(f"Task failed: {result.userFriendlyError}")
    raise TimeoutError("Polling timeout")
```

### 검색 결과 데이터 구조

Browse.ai가 모니터링 모드로 동작하여 변경 추적 필드가 포함됨:

```json
{
  "_STATUS": "CHANGED",        // CHANGED | ADDED | REMOVED
  "Position": "1",
  "Title": "Product Title...",
  "Product Link": "https://www.amazon.com/...",
  "Price": "$18.99",           // 또는 "KRW 27,904" (로케일에 따라)
  "Reviews": "(7.6K)",
  "Rating": "4.5",
  "Sponsored": "Sponsored",    // 또는 null
  "_PREV_Position": "6",       // 이전 값 (무시해도 됨)
  "_PREV_Price": "$18.99",
  // ...
}
```

**파싱 규칙:**
- `_STATUS === "REMOVED"` → 제외 (현재 데이터가 null)
- `_STATUS === "CHANGED"` 또는 `"ADDED"` → 현재 데이터 사용
- `_PREV_*` 필드는 무시
- `Position`이 null인 항목도 제외

### ASIN 추출

Product Link에서 ASIN 추출. Sponsored 제품은 URL이 `/sspa/click?...` 형태이므로 URL decode 필요:

```python
from urllib.parse import unquote
import re

def extract_asin(url):
    if not url:
        return None
    # 직접 매칭
    m = re.search(r'/dp/([A-Z0-9]{10})', url)
    if m:
        return m.group(1)
    # URL decode 후 매칭 (sponsored 링크)
    decoded = unquote(url)
    m = re.search(r'/dp/([A-Z0-9]{10})', decoded)
    if m:
        return m.group(1)
    return None
```

### 상세 결과 데이터 구조

```json
{
  "capturedTexts": {
    "top_highlights": "Top highlights\nProduct Benefits\t...\nActive Ingredients\t...\nAbout this item\n...",
    "features": "Features & Specs\nProduct Benefits\t...\nHair Type\t...",
    "measurements": "Measurements\nLiquid Volume\t1.7 Fluid Ounces\n...",
    "bsr": "",
    "volumn": "1K+ bought"    // 오타 그대로 (Browse.ai 셀렉터명)
  }
}
```

---

## 5. Gemini Flash 성분 추출

### API 호출

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}

{
  "contents": [{
    "parts": [{
      "text": "{프롬프트}"
    }]
  }],
  "generationConfig": {
    "temperature": 0.1,
    "maxOutputTokens": 4096,
    "responseMimeType": "application/json"
  }
}
```

### 프롬프트

```
아래는 아마존에서 수집한 제품 목록이다.
각 제품의 설명 텍스트에서 마케팅적으로 강조하고 있는 성분(ingredient)을 추출하라.

규칙:
1. 성분명은 영문 표준명으로 통일 (예: 아르간오일 → Argan Oil)
2. 같은 성분의 다른 이름은 가장 널리 쓰이는 이름으로 통일
   (예: Vitamin B7 = Biotin → "Biotin", Tocopherol = Vitamin E → "Vitamin E")
3. 각 성분에 카테고리 부여:
   Natural Oil / Essential Oil / Vitamin / Protein / Peptide /
   Active/Functional / Hair Growth Complex / Silicone / Botanical /
   Pharmaceutical / Humectant / Other
4. 제품의 기능·효과(Moisturizing, Shine, Strengthening 등)는 성분이 아니므로 제외
5. 화학적으로 식별 가능한 물질만 추출
6. JSON만 출력:

{
  "products": [
    {
      "asin": "제품ASIN",
      "ingredients": [
        {"name": "Argan Oil", "category": "Natural Oil"}
      ]
    }
  ]
}

제품 목록:
{products_json}
```

### 입력 데이터 형태

```python
products_for_gemini = [
    {
        "asin": "B081JHTPKP",
        "title": "Mise En Scene Perfect Serum...",
        "text": (top_highlights + " " + features)[:800]  # 800자 제한
    },
    ...
]
```

### 30개 제품을 한번에 전송
- 30개 × 800자 ≈ 25K input tokens → Gemini Flash 무료 tier 내
- API 호출 1회로 처리
- `responseMimeType: "application/json"` 으로 JSON 강제

---

## 6. 가중치 계산

### 공식

각 제품의 복합 가중치:

```
Weight = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
```

각 요소는 0~1로 정규화:
- **Position**: `1 - (position - 1) / max_position` (순위 높을수록 높은 값)
- **Reviews**: `reviews / max_reviews`
- **Rating**: `rating / 5.0`
- **Volume**: `volume / max_volume`

### 파싱 함수

```python
def parse_reviews(s):
    """'(7.6K)' → 7600, '(451)' → 451"""

def parse_volume(s):
    """'1K+ bought' → 1000, '100+ bought' → 100"""

def parse_price(s):
    """'$18.99' → 18.99"""
```

### 성분별 집계

각 성분에 대해:
- **Weighted Score**: 해당 성분이 포함된 모든 제품의 weight 합
- **# Products**: 포함 제품 수
- **Avg Weight**: Weighted Score / # Products
- **Avg Price**: 포함 제품의 평균 가격
- **Price Range**: 최저 ~ 최고

---

## 7. 엑셀 출력 (레퍼런스: hair_serum_ingredient_analysis.xlsx)

### 시트 구조 (5개)

#### Sheet 1: Ingredient Ranking
성분별 가중치 순위. 핵심 시트.

| 컬럼 | 설명 |
|------|------|
| Rank | 순위 |
| Ingredient | 성분명 (Gemini 추출) |
| Weighted Score | 가중치 합산 |
| # Products | 해당 성분 포함 제품 수 |
| Avg Weight | 제품당 평균 가중치 |
| Category | 성분 카테고리 (Gemini 분류) |
| Avg Price | 해당 성분 포함 제품 평균가 |
| Price Range | 최저 ~ 최고 |
| Key Insight | 자동 생성 코멘트 |

Key Insight 로직:
- Top 3: "Top-tier: dominant across high-performing products"
- 4개+ 제품: "Broadly adopted (N products)"
- Avg Weight > 0.4: "High avg weight — niche but in top products"
- 1개 제품 & Score > 0.3: "Single-product signal — monitor trend"

#### Sheet 2: Category Summary
성분 카테고리별 집계.

| 컬럼 | 설명 |
|------|------|
| Category | Natural Oil, Vitamin, etc. |
| Total Weighted Score | 카테고리 내 성분 가중치 총합 |
| # Types | 성분 종류 수 |
| # Mentions | 총 언급 횟수 |
| Avg Price | 카테고리 평균가 |
| Price Range | 가격 범위 |
| Top Ingredients | 상위 성분 나열 |

#### Sheet 3: Product Detail
제품별 상세 데이터 + 추출된 성분.

| 컬럼 | 설명 |
|------|------|
| ASIN | 아마존 제품 ID |
| Title | 제품명 |
| Position | 검색 순위 |
| Price | 가격 |
| Reviews | 리뷰 수 |
| Rating | 평점 |
| Volume | 구매량 |
| Composite Weight | 복합 가중치 |
| Ingredients Found | Gemini가 추출한 성분 목록 |

#### Sheet 4: Raw - Search Results
검색 결과 원본 데이터 전체.

| 컬럼 | 설명 |
|------|------|
| Position | 순위 |
| Title | 제품명 |
| ASIN | 제품 ID |
| Price | 가격 |
| Reviews | 리뷰 수 |
| Rating | 평점 |
| Sponsored | 광고 여부 |
| Product Link | 상품 URL |

#### Sheet 5: Raw - Product Detail
상세 크롤링 원본 데이터.

| 컬럼 | 설명 |
|------|------|
| ASIN | 제품 ID |
| Title | 제품명 |
| BSR | Best Seller Rank |
| Volume | 구매량 |
| Top Highlights | 원문 전체 |
| Features | 원문 전체 |
| Measurements | 원문 전체 |
| Product URL | 상품 URL |

### 스타일링

```python
# 색상 팔레트
HEADER_FILL = '1B2A4A'      # 진한 남색 헤더
HEADER_FONT = 'FFFFFF'       # 흰색 헤더 텍스트
ACCENT_FILL = 'F5F7FA'       # 교대행 배경 (연회색)
BORDER_COLOR = 'D0D5DD'      # 연한 회색 하단 보더
TITLE_COLOR = '1B2A4A'       # 시트 제목 색상

# 폰트
DEFAULT_FONT = 'Arial'
TITLE_SIZE = 14
HEADER_SIZE = 11
DATA_SIZE = 10
SMALL_SIZE = 9

# 탭 색상
SHEET1_TAB = '1B2A4A'        # Ingredient Ranking
SHEET2_TAB = '2E86AB'        # Category Summary
SHEET3_TAB = '4CAF50'        # Product Detail
SHEET4_TAB = 'FF6B35'        # Raw Search
SHEET5_TAB = '9B59B6'        # Raw Detail
```

- 교대행 색상 (짝수행에 ACCENT_FILL)
- 하단 thin border
- 헤더행 freeze panes
- 숫자 포맷: 가격 `$#,##0.00`, 가중치 `0.000`, 리뷰 `#,##0`
- Top Highlights/Features는 wrap_text + 행 높이 80

---

## 8. Slack 출력

### 진행 메시지 (response_url로 전송)

```
🔍 *hair serum* 검색 시작합니다. 약 10~15분 소요됩니다.
```

```
✅ 검색 완료: 28개 제품 확인. 상세 크롤링 시작...
```

```
🧪 성분 추출 중... (Gemini Flash)
```

### 최종 요약 메시지

```
🧪 Amazon "hair serum" 성분 분석 완료
분석 대상: 28개 제품 | Powered by Gemini Flash

 1. *Argan Oil* [Natural Oil]
     Score: 3.93 | 10개 제품 | 평균가 $18
 2. *Biotin* [Vitamin]
     Score: 2.84 | 8개 제품 | 평균가 $22
 3. *Vitamin E* [Vitamin]
     Score: 2.32 | 6개 제품 | 평균가 $15
...

Score = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
성분 추출: 마케팅 소구 기준 (INCI 전성분 아님)
```

### 엑셀 파일 업로드

response_url로는 파일 업로드 불가. Slack Bot Token + files.upload API 사용:

```
POST https://slack.com/api/files.upload
Authorization: Bearer {SLACK_BOT_TOKEN}

Form data:
  channels: {channel_id}
  file: @hair_serum_analysis.xlsx
  initial_comment: "📊 상세 분석 엑셀 파일"
```

---

## 9. 에러 처리

| 상황 | 대응 |
|------|------|
| Browse.ai 검색 실패 (retry 없음) | 슬랙에 에러 메시지 전송 |
| Browse.ai polling 타임아웃 (10분) | 슬랙에 타임아웃 메시지 |
| 상세 크롤링 일부 실패 | 성공한 것만으로 진행, 실패 수 슬랙 안내 |
| Gemini JSON 파싱 실패 | retry 1회, 그래도 실패면 빈 성분으로 처리 |
| 키워드 누락 | 즉시 400 반환 |

---

## 10. 파일 구조 (예상)

```
amz-researcher/
├── main.py                  # FastAPI 앱 + 엔드포인트
├── services/
│   ├── browse_ai.py         # Browse.ai API 호출 + polling
│   ├── gemini.py            # Gemini 성분 추출
│   ├── analyzer.py          # 가중치 계산 + 데이터 가공
│   ├── excel_builder.py     # 엑셀 생성 (openpyxl)
│   └── slack.py             # Slack 메시지/파일 전송
├── models/
│   └── schemas.py           # Pydantic 모델
├── config.py                # 환경 변수
├── requirements.txt
├── Dockerfile
└── .env
```

---

## 11. 기술 스택

- **Python 3.11+**
- **FastAPI** + **uvicorn**
- **httpx** (async HTTP 클라이언트)
- **openpyxl** (엑셀 생성)
- **Pydantic** (데이터 검증)

---

## 12. 레퍼런스 파일

이 스펙과 함께 제공되는 파일:
- `hair_serum_ingredient_analysis.xlsx` — 엑셀 출력 레퍼런스 (스타일, 시트 구조, 데이터 형태)

이 엑셀의 품질(포맷, 색상, 컬럼 구조, 인사이트 텍스트)을 그대로 재현해야 함.
