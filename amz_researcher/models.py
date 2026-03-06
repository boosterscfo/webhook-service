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
    asin: str
    title: str = ""
    top_highlights: str = ""
    features: str = ""
    measurements: str = ""
    bsr: str = ""
    volume_raw: str = ""
    volume: int = 0
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
    volume: int = 0
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
