from pydantic import BaseModel


class SearchProduct(BaseModel):
    position: int
    title: str
    asin: str
    price: float | None = None
    price_raw: str = ""
    reviews: int = 0
    reviews_raw: str = ""
    rating: float = 0.0
    sponsored: bool = False
    product_link: str = ""
    bought_past_month: int | None = None


class ProductDetail(BaseModel):
    """제품 상세 정보 (Bright Data 기반)."""
    asin: str
    ingredients_raw: str = ""
    features: dict = {}
    measurements: dict = {}
    item_details: dict = {}
    additional_details: dict = {}
    bsr_category: int | None = None
    bsr_subcategory: int | None = None
    bsr_category_name: str = ""
    bsr_subcategory_name: str = ""
    rating: float | None = None
    review_count: int | None = None
    brand: str = ""
    manufacturer: str = ""
    product_url: str = ""


class BrightDataProduct(BaseModel):
    """Bright Data 기반 제품 모델. V3의 SearchProduct + ProductDetail 통합."""
    asin: str
    title: str = ""
    brand: str = ""
    description: str = ""
    initial_price: float | None = None
    final_price: float | None = None
    currency: str = "USD"
    rating: float = 0.0
    reviews_count: int = 0
    bs_rank: int | None = None
    bs_category: str = ""
    root_bs_rank: int | None = None
    root_bs_category: str = ""
    subcategory_ranks: list[dict] = []
    ingredients: str = ""
    features: list[str] = []
    product_details: list[dict] = []
    manufacturer: str = ""
    department: str = ""
    image_url: str = ""
    url: str = ""
    badge: str = ""
    bought_past_month: int | None = None
    categories: list[str] = []
    customer_says: str = ""
    unit_price: str = ""
    sns_price: float | None = None
    variations_count: int = 0
    number_of_sellers: int = 1
    coupon: str = ""
    plus_content: bool = False


class Ingredient(BaseModel):
    name: str  # INCI 학명 또는 원본 성분명
    common_name: str = ""  # 핵심 성분명 (마케팅용 일반명)
    category: str


class ProductIngredients(BaseModel):
    asin: str
    ingredients: list[Ingredient] = []


class GeminiResponse(BaseModel):
    products: list[ProductIngredients]


class VoiceKeyword(BaseModel):
    keyword: str
    asins: list[str] = []


class VoiceKeywordResult(BaseModel):
    positive_keywords: list[VoiceKeyword] = []
    negative_keywords: list[VoiceKeyword] = []


class WeightedProduct(BaseModel):
    asin: str
    title: str
    position: int
    price: float | None = None
    reviews: int = 0
    rating: float = 0.0
    bsr_category: int | None = None
    bsr_subcategory: int | None = None
    composite_weight: float = 0.0
    ingredients: list[Ingredient] = []
    # V4 확장 필드
    bought_past_month: int | None = None
    brand: str = ""
    sns_price: float | None = None
    unit_price: str = ""
    number_of_sellers: int = 1
    coupon: str = ""
    plus_content: bool = False
    customer_says: str = ""
    sponsored: bool = False
    # V5 신규 필드
    badge: str = ""
    initial_price: float | None = None
    manufacturer: str = ""
    variations_count: int = 0


class IngredientRanking(BaseModel):
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
    category: str
    total_weighted_score: float
    type_count: int
    mention_count: int
    avg_price: float | None = None
    price_range: str = ""
    top_ingredients: str = ""
