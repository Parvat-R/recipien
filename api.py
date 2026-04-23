from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal

from search import (
    load_canonical_index,
    resolve_ingredients,
    search_recipes,
    search_recipes_by_name,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_canonical_index()
    yield


app = FastAPI(
    title="Recipe Search API",
    description="Search recipes by ingredients or name.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Schemas ───────────────────────────────────────────────────────────────────

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


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingredients/resolve", response_model=ResolveResponse, tags=["Ingredients"])
def resolve(body: ResolveRequest):
    """Resolve messy ingredient names to canonical forms before searching."""
    return ResolveResponse(resolved=resolve_ingredients(body.ingredients))


@app.post("/recipes/search", response_model=SearchResponse, tags=["Recipes"])
def search_recipes_post(body: SearchRequest):
    """Search recipes by ingredients (POST). Auto-resolves typos and variants."""
    try:
        resolved = [resolve_ingredients([ing])[ing] for ing in body.ingredients]
        results = search_recipes(body.ingredients, body.limit, body.fuzzy_threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SearchResponse(
        query=body.ingredients,
        resolved=resolved,
        count=len(results),
        results=[RecipeResult.model_validate(r) for r in results],
    )


@app.get("/recipes/search", response_model=SearchResponse, tags=["Recipes"])
def search_recipes_get(
    ingredients: list[str] = Query(...),
    limit: int = Query(5, ge=1, le=50),
    fuzzy_threshold: float = Query(0.4, ge=0.0, le=1.0),
):
    """Search recipes by ingredients (GET). Example: ?ingredients=chicken&ingredients=garlic"""
    try:
        resolved = [resolve_ingredients([ing])[ing] for ing in ingredients]
        results = search_recipes(ingredients, limit, fuzzy_threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SearchResponse(
        query=ingredients,
        resolved=resolved,
        count=len(results),
        results=[RecipeResult.model_validate(r) for r in results],
    )


@app.post("/recipes/search/name", response_model=NameSearchResponse, tags=["Recipes"])
def search_by_name_post(body: NameSearchRequest):
    """Search recipes by title (POST)."""
    try:
        results = search_recipes_by_name(body.query, body.limit, body.fuzzy_threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return NameSearchResponse(
        query=body.query,
        count=len(results),
        results=[NameSearchResult.model_validate(r) for r in results],
    )


@app.get("/recipes/search/name", response_model=NameSearchResponse, tags=["Recipes"])
def search_by_name_get(
    q: str = Query(...),
    limit: int = Query(5, ge=1, le=50),
    fuzzy_threshold: float = Query(0.3, ge=0.0, le=1.0),
):
    """Search recipes by title (GET). Example: ?q=butter+chicken"""
    try:
        results = search_recipes_by_name(q, limit, fuzzy_threshold)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return NameSearchResponse(
        query=q,
        count=len(results),
        results=[NameSearchResult.model_validate(r) for r in results],
    )


@app.get("/recipes/{recipe_id}", response_model=RecipeResult, tags=["Recipes"])
def get_recipe(recipe_id: int):
    """Fetch a single recipe by ID."""
    import psycopg as _psycopg
    from search import _parse_ingredients, _parse_directions, DB_URI
    try:
        with _psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, ingredients, directions, link, source FROM recipe WHERE id = %(id)s",
                    {"id": recipe_id}
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found")
        cols = ["id", "title", "ingredients", "directions", "link", "source"]
        result = dict(zip(cols, row))
        result["ingredients"] = _parse_ingredients(result["ingredients"])
        result["directions"] = _parse_directions(result["directions"])
        result["exact_count"] = 0
        result["total_ingredients"] = len(result["ingredients"])
        result["coverage"] = 0.0
        return RecipeResult.model_validate(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))