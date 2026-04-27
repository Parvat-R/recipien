from pydantic import BaseModel, Field
from typing import Optional, Literal

class RecipeResult(BaseModel):
    id: int
    title: str
    ingredients: list[str]
    directions: list[str]
    link: Optional[str] = None
    source: Optional[str] = None
    exact_count: int = Field(description="Number of user ingredients matched exactly")
    total_ingredients: int = Field(description="Total ingredients in the recipe")
    coverage: float = Field(description="Fraction of recipe ingredients the user has (0-1)")


class SearchResponse(BaseModel):
    query: list[str]
    resolved: list[str] = Field(description="Ingredients after canonical resolution")
    count: int
    results: list[RecipeResult]


class SearchRequest(BaseModel):
    ingredients: list[str] = Field(..., min_length=1, examples=[["chicken", "butter", "garlic"]])
    limit: int = Field(5, ge=1, le=50)
    fuzzy_threshold: float = Field(0.4, ge=0.0, le=1.0)


class NameSearchResult(BaseModel):
    id: int
    title: str
    ingredients: list[str]
    directions: list[str]
    link: Optional[str] = None
    source: Optional[str] = None
    match_type: Literal["fts", "fuzzy"]
    rank: float


class NameSearchResponse(BaseModel):
    query: str
    count: int
    results: list[NameSearchResult]


class NameSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, examples=["butter chicken"])
    limit: int = Field(5, ge=1, le=50)
    fuzzy_threshold: float = Field(0.3, ge=0.0, le=1.0)


class ResolveRequest(BaseModel):
    ingredients: list[str] = Field(..., examples=[["zuchini", "mozzerella", "tomatos"]])


class ResolveResponse(BaseModel):
    resolved: dict[str, str] = Field(description="Maps each input to its canonical form")
