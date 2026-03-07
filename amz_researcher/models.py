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


class ProductDetail(BaseModel):
    """Browse.ai 상세 크롤링 결과 (V2 — capturedTexts 신규 필드)."""
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


class Ingredient(BaseModel):
    name: str
    category: str


class ProductIngredients(BaseModel):
    asin: str
    ingredients: list[Ingredient] = []


class GeminiResponse(BaseModel):
    products: list[ProductIngredients]


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
