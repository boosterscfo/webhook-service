# Design: Amazon Keyword Ingredient Researcher

> Plan: `docs/01-plan/features/amazon-researcher.plan.md`
> Spec: `docs/amazon_researcher/amz_researcher_spec.md`
> Reference Excel: `docs/amazon_researcher/hair_serum_ingredient_analysis.xlsx`

---

## 1. File Structure

```
webhook-service/
├── main.py                              # amz_router include 추가
├── app/
│   └── config.py                        # AMZ_* 환경 변수 추가
├── amz_researcher/
│   ├── __init__.py
│   ├── router.py                        # POST /slack/amz, POST /research
│   ├── orchestrator.py                  # run_research 파이프라인
│   ├── models.py                        # Pydantic 모델
│   └── services/
│       ├── __init__.py
│       ├── browse_ai.py                 # Browse.ai API + polling
│       ├── gemini.py                    # Gemini Flash 성분 추출
│       ├── analyzer.py                  # 가중치 계산 + 집계
│       ├── excel_builder.py             # openpyxl 엑셀 생성
│       └── slack_sender.py              # response_url 메시지 + 파일 업로드
└── lib/
    └── slack.py                         # 기존 유지 (재사용하지 않음)
```

---

## 2. Config 변경 (`app/config.py`)

기존 `Settings` 클래스에 추가:

```python
# Amazon Researcher
AMZ_BROWSE_AI_API_KEY: str = ""
AMZ_GEMINI_API_KEY: str = ""
AMZ_BOT_TOKEN: str = ""               # Slack Bot Token (파일 업로드용)
AMZ_SEARCH_ROBOT_ID: str = ""
AMZ_DETAIL_ROBOT_ID: str = ""
```

모든 필드에 기본값 `""` → 다른 서비스 배포 시 환경 변수 없어도 앱 기동 가능.

---

## 3. Data Models (`amz_researcher/models.py`)

```python
from pydantic import BaseModel

class SearchProduct(BaseModel):
    """Browse.ai 검색 결과에서 파싱한 제품 정보"""
    position: int
    title: str
    asin: str
    price: float | None = None          # parse_price 결과
    price_raw: str = ""                  # 원본 문자열
    reviews: int = 0                     # parse_reviews 결과
    reviews_raw: str = ""
    rating: float = 0.0
    sponsored: bool = False
    product_link: str = ""

class ProductDetail(BaseModel):
    """Browse.ai 상세 로봇 결과"""
    asin: str
    title: str = ""
    top_highlights: str = ""
    features: str = ""
    measurements: str = ""
    bsr: str = ""
    volume_raw: str = ""                 # "1K+ bought"
    volume: int = 0                      # parse_volume 결과
    product_url: str = ""

class Ingredient(BaseModel):
    """Gemini가 추출한 성분"""
    name: str                            # 영문 표준명
    category: str                        # Natural Oil, Vitamin, etc.

class ProductIngredients(BaseModel):
    """제품별 추출 성분"""
    asin: str
    ingredients: list[Ingredient] = []

class GeminiResponse(BaseModel):
    """Gemini API 응답 구조"""
    products: list[ProductIngredients]

class WeightedProduct(BaseModel):
    """가중치 계산 완료된 제품"""
    asin: str
    title: str
    position: int
    price: float | None = None
    reviews: int = 0
    rating: float = 0.0
    volume: int = 0
    composite_weight: float = 0.0
    ingredients: list[Ingredient] = []

class IngredientRanking(BaseModel):
    """성분별 집계 결과"""
    rank: int = 0
    ingredient: str
    weighted_score: float
    product_count: int
    avg_weight: float
    category: str
    avg_price: float | None = None
    price_range: str = ""
    key_insight: str = ""

class CategorySummary(BaseModel):
    """카테고리별 집계"""
    category: str
    total_weighted_score: float
    type_count: int                      # 성분 종류 수
    mention_count: int                   # 총 언급 횟수
    avg_price: float | None = None
    price_range: str = ""
    top_ingredients: str = ""            # 상위 성분 나열
```

---

## 4. Service Designs

### 4.1 Browse.ai Service (`amz_researcher/services/browse_ai.py`)

#### Public Interface

```python
class BrowseAiService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.browse.ai/v2"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def run_search(self, keyword: str) -> list[SearchProduct]:
        """검색 로봇 실행 → polling → 결과 파싱 → SearchProduct 리스트 반환"""
        # 1. POST /robots/{SEARCH_ROBOT_ID}/tasks
        #    inputParameters: {"amazon_url": f"https://www.amazon.com/s?k={keyword}"}
        # 2. poll_task() 로 완료 대기
        # 3. parse_search_results() 로 SearchProduct 리스트 변환
        # 4. 상위 30개 반환 (Position 기준 정렬)

    async def run_detail(self, asin: str) -> ProductDetail | None:
        """상세 로봇 실행 → polling → ProductDetail 반환"""
        # inputParameters: {"originUrl": f"https://www.amazon.com/dp/{asin}"}

    async def run_details_batch(self, asins: list[str], max_concurrent: int = 5) -> list[ProductDetail]:
        """30개 ASIN 병렬 상세 크롤링 (semaphore로 동시 실행 제한)"""
        # asyncio.Semaphore(max_concurrent)
        # 개별 실패 허용, 성공 건만 반환

    async def close(self):
        await self.client.aclose()
```

#### Internal Methods

```python
    async def _create_task(self, robot_id: str, input_params: dict) -> str:
        """로봇 task 생성 → task_id 반환"""

    async def _check_task(self, robot_id: str, task_id: str) -> dict:
        """GET /robots/{robot_id}/tasks/{task_id} → raw response"""

    async def _poll_task(self, robot_id: str, task_id: str,
                         max_attempts: int = 20, interval: int = 30) -> dict:
        """Polling loop with retry task tracking"""
        # failed + retriedByTaskId → current_id 전환
        # failed + no retry → raise
        # 10분 타임아웃 → raise TimeoutError
```

#### Parsing Functions (모듈 레벨)

```python
def extract_asin(url: str) -> str | None:
    """Product Link에서 ASIN 추출 (URL decode 포함)"""

def parse_search_results(raw_items: list[dict]) -> list[SearchProduct]:
    """Browse.ai 검색 결과 파싱
    - _STATUS == "REMOVED" 제외
    - Position이 null인 항목 제외
    - _PREV_* 필드 무시
    """

def parse_reviews(s: str) -> int:
    """'(7.6K)' → 7600, '(451)' → 451"""

def parse_volume(s: str) -> int:
    """'1K+ bought' → 1000, '100+ bought' → 100"""

def parse_price(s: str) -> float | None:
    """'$18.99' → 18.99, None if unparseable"""
```

### 4.2 Gemini Service (`amz_researcher/services/gemini.py`)

```python
class GeminiService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = "gemini-2.0-flash"
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def extract_ingredients(self, products: list[dict]) -> list[ProductIngredients]:
        """제품 목록에서 성분 추출
        Args:
            products: [{"asin": "...", "title": "...", "text": "..."}]
                      text = (top_highlights + " " + features)[:800]
        Returns:
            ProductIngredients 리스트
        """
        # 1. 프롬프트 생성 (스펙 섹션 5 참조)
        # 2. POST API 호출 (temperature=0.1, maxOutputTokens=4096, responseMimeType=application/json)
        # 3. JSON 파싱 → GeminiResponse.products
        # 4. 파싱 실패 시 1회 retry
        # 5. retry 실패 시 빈 리스트 반환

    async def close(self):
        await self.client.aclose()
```

#### Prompt Template (상수)

스펙 섹션 5의 프롬프트를 그대로 사용. `{products_json}` 자리에 `json.dumps(products, ensure_ascii=False)` 삽입.

### 4.3 Analyzer (`amz_researcher/services/analyzer.py`)

순수 계산 로직, 외부 I/O 없음.

```python
def calculate_weights(
    search_products: list[SearchProduct],
    details: list[ProductDetail],
    gemini_results: list[ProductIngredients],
) -> tuple[list[WeightedProduct], list[IngredientRanking], list[CategorySummary]]:
    """전체 분석 파이프라인
    Returns:
        (weighted_products, ingredient_rankings, category_summaries)
    """
```

#### Internal Functions

```python
def _compute_composite_weight(
    position: int, reviews: int, rating: float, volume: int,
    max_position: int, max_reviews: int, max_volume: int,
) -> float:
    """Weight = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
    각 요소 0~1 정규화
    """

def _aggregate_ingredients(
    weighted_products: list[WeightedProduct],
) -> list[IngredientRanking]:
    """성분별 집계: Weighted Score, # Products, Avg Weight, Avg Price, Price Range"""

def _generate_key_insight(rank: int, product_count: int,
                          weighted_score: float, avg_weight: float) -> str:
    """Key Insight 자동 생성
    - rank <= 3: "Top-tier: dominant across high-performing products"
    - product_count >= 4: "Broadly adopted (N products)"
    - avg_weight > 0.4: "High avg weight - niche but in top products"
    - product_count == 1 and weighted_score > 0.3: "Single-product signal - monitor trend"
    - else: ""
    """

def _aggregate_categories(
    rankings: list[IngredientRanking],
    weighted_products: list[WeightedProduct],
) -> list[CategorySummary]:
    """카테고리별 집계"""
```

### 4.4 Excel Builder (`amz_researcher/services/excel_builder.py`)

```python
def build_excel(
    keyword: str,
    weighted_products: list[WeightedProduct],
    rankings: list[IngredientRanking],
    categories: list[CategorySummary],
    search_products: list[SearchProduct],
    details: list[ProductDetail],
) -> bytes:
    """엑셀 파일 생성 → bytes 반환 (BytesIO)"""
```

#### Sheet Layout (레퍼런스 엑셀 기반)

모든 시트 공통 패턴:
- **Row 1**: 제목 (merged, 14pt bold, color #1B2A4A)
- **Row 2**: 부제목 또는 빈 행
- **Row 3**: 컬럼 헤더 (bold, fill #1B2A4A, font white, 11pt Arial)
- **Row 4+**: 데이터 (10pt, 교대행 #F5F7FA)
- **Freeze**: A4 (Sheet1만 A5 — 제목+부제 2줄이므로)

**Sheet 1: Ingredient Ranking**
- Row 1: `{Keyword} Ingredient Analysis - Weighted by Market Performance` (merged A1:I1)
- Row 2: `Weight = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%) | {N} products, {M} ingredients` (merged A2:I2)
- Row 3: 빈 행
- Row 4: 헤더 — Rank | Ingredient | Weighted Score | # Products | Avg Weight | Category | Avg Price | Price Range | Key Insight
- Row 5+: 데이터
- Freeze: A5
- Column widths: A=7, B=28, C=15, D=12, E=13, F=20, G=12, H=18, I=42
- Number formats: Weighted Score `0.000`, Avg Weight `0.000`, Avg Price `$#,##0.00`

**Sheet 2: Category Summary**
- Row 1: `Ingredient Category Summary` (merged A1:G1)
- Row 3: 헤더 — Category | Total Weighted Score | # Types | # Mentions | Avg Price | Price Range | Top Ingredients
- Freeze: A4

**Sheet 3: Product Detail**
- Row 1: `Product-Level Data with Weight Breakdown` (merged A1:I1)
- Row 3: 헤더 — ASIN | Title | Position | Price | Reviews | Rating | Volume | Composite Weight | Ingredients Found
- Freeze: A4

**Sheet 4: Raw - Search Results**
- Row 1: `Amazon Search Results - "{keyword}" (Raw Data, {N} products)` (merged A1:H1)
- Row 3: 헤더 — Position | Title | ASIN | Price | Reviews | Rating | Sponsored | Product Link
- Freeze: A4

**Sheet 5: Raw - Product Detail**
- Row 1: `Amazon Product Detail - Top Highlights & Features (Raw Data)` (merged A1:H1)
- Row 3: 헤더 — ASIN | Title | BSR | Volume | Top Highlights | Features | Measurements | Product URL
- Freeze: A4
- Top Highlights/Features: wrap_text=True, row height=80

#### Styling Constants

```python
HEADER_FILL = "1B2A4A"
HEADER_FONT_COLOR = "FFFFFF"
ACCENT_FILL = "F5F7FA"
BORDER_COLOR = "D0D5DD"
TITLE_COLOR = "1B2A4A"

DEFAULT_FONT = "Arial"
TITLE_SIZE = 14
HEADER_SIZE = 11
DATA_SIZE = 10

TAB_COLORS = {
    "Ingredient Ranking": "1B2A4A",
    "Category Summary": "2E86AB",
    "Product Detail": "4CAF50",
    "Raw - Search Results": "FF6B35",
    "Raw - Product Detail": "9B59B6",
}
```

### 4.5 Slack Sender (`amz_researcher/services/slack_sender.py`)

`httpx`만 사용하여 Slack API 직접 호출 (기존 `lib/slack.py`의 `slack_sdk`와 독립).

```python
class SlackSender:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.client = httpx.AsyncClient(timeout=30.0)

    async def send_message(self, response_url: str, text: str):
        """response_url로 in_channel 메시지 전송 (지연 응답)"""
        await self.client.post(response_url, json={
            "response_type": "in_channel",
            "text": text,
        })

    async def upload_file(self, channel_id: str, file_bytes: bytes,
                          filename: str, comment: str = ""):
        """Slack files.upload API로 엑셀 파일 업로드"""
        # POST https://slack.com/api/files.upload
        # Authorization: Bearer {bot_token}
        # Form data: channels, file, initial_comment

    async def close(self):
        await self.client.aclose()
```

#### Message Templates

```python
# 진행 메시지
MSG_SEARCH_START = "🔍 *{keyword}* 검색 시작합니다. 약 10~15분 소요됩니다."
MSG_SEARCH_DONE = "✅ 검색 완료: {count}개 제품 확인. 상세 크롤링 시작..."
MSG_EXTRACTING = "🧪 성분 추출 중... (Gemini Flash)"
MSG_ERROR = "❌ *{keyword}* 분석 실패: {error}"

# 최종 요약 (Top 10)
SUMMARY_TEMPLATE = """🧪 Amazon "{keyword}" 성분 분석 완료
분석 대상: {product_count}개 제품 | Powered by Gemini Flash

{rankings}

Score = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)
성분 추출: 마케팅 소구 기준 (INCI 전성분 아님)"""

# 각 성분 라인: " 1. *Argan Oil* [Natural Oil]\n     Score: 3.93 | 10개 제품 | 평균가 $18"
```

---

## 5. Orchestrator (`amz_researcher/orchestrator.py`)

전체 파이프라인을 조율하는 단일 async 함수.

```python
import logging
from app.config import settings
from amz_researcher.services.browse_ai import BrowseAiService
from amz_researcher.services.gemini import GeminiService
from amz_researcher.services.analyzer import calculate_weights
from amz_researcher.services.excel_builder import build_excel
from amz_researcher.services.slack_sender import SlackSender

logger = logging.getLogger(__name__)

async def run_research(keyword: str, response_url: str, channel_id: str):
    """Background Task로 실행되는 전체 리서치 파이프라인"""
    browse = BrowseAiService(settings.AMZ_BROWSE_AI_API_KEY)
    gemini = GeminiService(settings.AMZ_GEMINI_API_KEY)
    slack = SlackSender(settings.AMZ_BOT_TOKEN)

    try:
        # Step 1: 검색 로봇 실행
        search_products = await browse.run_search(keyword)
        await slack.send_message(response_url,
            f"✅ 검색 완료: {len(search_products)}개 제품 확인. 상세 크롤링 시작...")

        # Step 2: 상세 크롤링 (병렬, max_concurrent=5)
        asins = [p.asin for p in search_products]
        details = await browse.run_details_batch(asins)

        # Step 3: Gemini 성분 추출
        await slack.send_message(response_url, "🧪 성분 추출 중... (Gemini Flash)")
        products_for_gemini = [
            {
                "asin": d.asin,
                "title": d.title,
                "text": (d.top_highlights + " " + d.features)[:800],
            }
            for d in details
        ]
        gemini_results = await gemini.extract_ingredients(products_for_gemini)

        # Step 4: 가중치 계산 + 집계
        weighted_products, rankings, categories = calculate_weights(
            search_products, details, gemini_results
        )

        # Step 5: 엑셀 생성
        excel_bytes = build_excel(
            keyword, weighted_products, rankings, categories,
            search_products, details
        )

        # Step 6: Slack 요약 메시지 전송
        summary = _build_summary(keyword, len(weighted_products), rankings[:10])
        await slack.send_message(response_url, summary)

        # Step 7: 엑셀 파일 업로드
        filename = f"{keyword.replace(' ', '_')}_analysis.xlsx"
        await slack.upload_file(channel_id, excel_bytes, filename,
                                comment="📊 상세 분석 엑셀 파일")

    except Exception as e:
        logger.exception(f"Research failed for keyword={keyword}")
        await slack.send_message(response_url,
            f"❌ *{keyword}* 분석 실패: {str(e)}")
    finally:
        await browse.close()
        await gemini.close()
        await slack.close()


def _build_summary(keyword: str, product_count: int,
                   top_rankings: list) -> str:
    """Top 10 성분 요약 메시지 생성"""
    lines = []
    for r in top_rankings:
        avg_price_str = f"${r.avg_price:.0f}" if r.avg_price else "N/A"
        lines.append(
            f" {r.rank}. *{r.ingredient}* [{r.category}]\n"
            f"     Score: {r.weighted_score:.2f} | {r.product_count}개 제품 | 평균가 {avg_price_str}"
        )
    rankings_text = "\n".join(lines)

    return (
        f'🧪 Amazon "{keyword}" 성분 분석 완료\n'
        f"분석 대상: {product_count}개 제품 | Powered by Gemini Flash\n\n"
        f"{rankings_text}\n\n"
        f"Score = Position(20%) + Reviews(30%) + Rating(20%) + Volume(30%)\n"
        f"성분 추출: 마케팅 소구 기준 (INCI 전성분 아님)"
    )
```

---

## 6. Router (`amz_researcher/router.py`)

```python
import logging
from fastapi import APIRouter, BackgroundTasks, Form
from pydantic import BaseModel
from amz_researcher.orchestrator import run_research

logger = logging.getLogger(__name__)
router = APIRouter()

class ResearchRequest(BaseModel):
    keyword: str
    response_url: str = ""
    channel_id: str = ""

@router.post("/slack/amz")
async def slack_amz(
    background_tasks: BackgroundTasks,
    text: str = Form(""),
    response_url: str = Form(""),
    channel_id: str = Form(""),
    user_id: str = Form(""),
):
    """Slack Slash Command 엔드포인트"""
    keyword = text.strip()
    if not keyword:
        return {
            "response_type": "ephemeral",
            "text": "사용법: /amz {키워드} (예: /amz hair serum)",
        }

    background_tasks.add_task(run_research, keyword, response_url, channel_id)
    return {
        "response_type": "in_channel",
        "text": f"🔍 *{keyword}* 검색 시작합니다. 약 10~15분 소요됩니다.",
    }

@router.post("/research")
async def research_test(
    background_tasks: BackgroundTasks,
    req: ResearchRequest,
):
    """로컬 테스트용 JSON 엔드포인트"""
    if not req.keyword.strip():
        return {"error": "keyword is required"}

    background_tasks.add_task(run_research, req.keyword, req.response_url, req.channel_id)
    return {"status": "started", "keyword": req.keyword}
```

---

## 7. main.py 변경

```python
from fastapi import FastAPI

from app.router import router
from amz_researcher.router import router as amz_router   # 추가

app = FastAPI(title="Webhooks Service")
app.include_router(router)
app.include_router(amz_router)                            # 추가

@app.get("/health")
async def health():
    return {"status": "ok"}
```

---

## 8. Sequence Diagram

```
Slack User        FastAPI         BrowseAi       Gemini       SlackSender
    |                |               |              |              |
    |-- /amz kw ---->|               |              |              |
    |<-- 200 OK -----|               |              |              |
    |                |-- search ---->|              |              |
    |                |<-- poll ... --|              |              |
    |                |<-- results ---|              |              |
    |                |               |              |  send_msg    |
    |                |-------------------------------------------->|
    |                |               |              |  "검색 완료"  |
    |                |-- detail x30->|              |              |
    |                |<-- poll ... --|              |              |
    |                |               |              |  send_msg    |
    |                |-------------------------------------------->|
    |                |               |              | "성분 추출중" |
    |                |-- extract ----|------------->|              |
    |                |<-- JSON ------|--------------|              |
    |                |               |              |              |
    |                |-- [analyze + excel locally]  |              |
    |                |               |              |              |
    |                |-------------------------------------------->|
    |                |               |              |  summary msg |
    |                |-------------------------------------------->|
    |                |               |              |  file upload |
    |<--------------------------------------------------------------|
```

---

## 9. Implementation Order

| Phase | File | Description | Dependencies |
|-------|------|-------------|--------------|
| 1 | `app/config.py` | AMZ_* 설정 5개 추가 | - |
| 2 | `amz_researcher/__init__.py` | 빈 파일 | - |
| 2 | `amz_researcher/models.py` | Pydantic 모델 정의 | - |
| 2 | `amz_researcher/services/__init__.py` | 빈 파일 | - |
| 3 | `amz_researcher/services/browse_ai.py` | Browse.ai 클라이언트 + 파싱 | models |
| 4 | `amz_researcher/services/gemini.py` | Gemini Flash 클라이언트 | models |
| 5 | `amz_researcher/services/analyzer.py` | 가중치 계산 + 집계 | models |
| 6 | `amz_researcher/services/excel_builder.py` | 5시트 엑셀 생성 | models |
| 7 | `amz_researcher/services/slack_sender.py` | Slack 메시지 + 파일 업로드 | - |
| 8 | `amz_researcher/orchestrator.py` | 파이프라인 조율 | all services |
| 9 | `amz_researcher/router.py` | 엔드포인트 정의 | orchestrator |
| 10 | `main.py` | amz_router include | router |

---

## 10. Error Handling Matrix

| Location | Error | Action |
|----------|-------|--------|
| `router.py` | keyword 누락 | 즉시 ephemeral 응답 반환 |
| `browse_ai.py` | 검색 task 생성 실패 | raise → orchestrator에서 catch → Slack 에러 전송 |
| `browse_ai.py` | polling 타임아웃 (20회 x 30초) | raise TimeoutError → 에러 전송 |
| `browse_ai.py` | failed + no retriedByTaskId | raise → 에러 전송 |
| `browse_ai.py` | 상세 개별 실패 | 로그 후 skip, 성공 건만 반환 |
| `gemini.py` | JSON 파싱 실패 | 1회 retry, 실패 시 빈 리스트 반환 |
| `gemini.py` | API 호출 실패 | raise → 에러 전송 |
| `orchestrator.py` | 미처리 예외 | catch-all → Slack 에러 메시지 전송 + 로깅 |

---

## 11. Dependencies

기존 `pyproject.toml` 또는 requirements에 추가 필요:

```
openpyxl>=3.1.0
```

`httpx`는 이미 설치됨. `slack_sdk`도 있으나 이 모듈에서는 사용하지 않음 (httpx로 직접 호출).
