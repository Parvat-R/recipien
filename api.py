from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
import psycopg
import dotenv
import os
import getpass
from search_recipe import _parse_ingredients, search_recipes_by_name, search_recipes
dotenv.load_dotenv()  # Load DB_URI from .env file if present

DB_URI = os.environ.get("DB_URI", "postgresql://postgres:root@localhost:5432/postgres")

app = FastAPI(
    title="Recipe Search API",
    description="Search recipes by ingredients or name using exact, full-text, and fuzzy matching.",
    version="1.0.0",
)


# ── Schemas ──────────────────────────────────────────────────────────────────

class RecipeResult(BaseModel):
    id: int
    title: str
    ingredients: list[str]
    directions: str
    link: Optional[str] = None
    source: Optional[str] = None
    exact_count: int = Field(description="Number of user ingredients matched exactly")
    total_ingredients: int = Field(description="Total ingredients in the recipe")
    coverage: float = Field(description="Fraction of recipe ingredients the user has (0–1)")


class SearchResponse(BaseModel):
    query: list[str]
    count: int
    results: list[RecipeResult]


class SearchRequest(BaseModel):
    ingredients: list[str] = Field(
        ...,
        min_length=1,
        description="List of ingredients you have",
        examples=[["chicken", "butter", "garlic"]],
    )
    limit: int = Field(5, ge=1, le=50, description="Max number of recipes to return")
    fuzzy_threshold: float = Field(
        0.4, ge=0.0, le=1.0, description="Similarity threshold for fuzzy fallback (0–1)"
    )


class NameSearchResult(BaseModel):
    id: int
    title: str
    ingredients: list[str]
    directions: str
    link: Optional[str] = None
    source: Optional[str] = None
    match_type: Literal["fts", "fuzzy"] = Field(
        description="How the recipe was matched: 'fts' = full-text search, 'fuzzy' = trigram"
    )
    rank: float = Field(description="Relevance score (higher = better)")


class NameSearchResponse(BaseModel):
    query: str
    count: int
    results: list[NameSearchResult]


class NameSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Recipe name or partial phrase to search for",
        examples=["butter chicken", "pasta carbonara"],
    )
    limit: int = Field(5, ge=1, le=50, description="Max number of recipes to return")
    fuzzy_threshold: float = Field(
        0.3, ge=0.0, le=1.0,
        description="Trigram similarity threshold used as fallback when FTS finds nothing (0–1)"
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Simple liveness check."""
    return {"status": "ok"}
 
 
@app.post("/recipes/search", response_model=SearchResponse, tags=["Recipes"])
def search_recipes_post(body: SearchRequest):
    """
    Search recipes by ingredients (POST body).
 
    Returns recipes ranked by exact ingredient matches first,
    then fuzzy matches as fallback.
    """
    try:
        results = search_recipes(
            user_ingredients=body.ingredients,
            limit=body.limit,
            fuzzy_threshold=body.fuzzy_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    return SearchResponse(
        query=body.ingredients,
        count=len(results),
        results=[RecipeResult.model_validate(r) for r in results],
    )
 
 
@app.get("/recipes/search", response_model=SearchResponse, tags=["Recipes"])
def search_recipes_get(
    ingredients: list[str] = Query(..., description="Ingredients you have"),
    limit: int = Query(5, ge=1, le=50, description="Max results"),
    fuzzy_threshold: float = Query(0.4, ge=0.0, le=1.0, description="Fuzzy similarity threshold"),
):
    """
    Search recipes by ingredients (GET query params).
 
    Example: `/recipes/search?ingredients=chicken&ingredients=garlic&limit=5`
    """
    try:
        results = search_recipes(
            user_ingredients=ingredients,
            limit=limit,
            fuzzy_threshold=fuzzy_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    return SearchResponse(
        query=ingredients,
        count=len(results),
        results=[RecipeResult.model_validate(r) for r in results],
    )
 
 
@app.post("/recipes/search/name", response_model=NameSearchResponse, tags=["Recipes"])
def search_recipes_by_name_post(body: NameSearchRequest):
    """
    Search recipes by name/title (POST body).
 
    Uses PostgreSQL full-text search first (`tsvector`), then falls back to
    trigram similarity (`pg_trgm`) if FTS doesn't fill the requested limit.
 
    **One-time DB setup required** — run this once in your database:
    ```sql
    CREATE INDEX IF NOT EXISTS idx_recipe_title_fts
        ON recipe USING GIN (to_tsvector('english', title));
 
    CREATE INDEX IF NOT EXISTS idx_recipe_title_trgm
        ON recipe USING GIN (title gin_trgm_ops);
    ```
    """
    try:
        results = search_recipes_by_name(
            query=body.query,
            limit=body.limit,
            fuzzy_threshold=body.fuzzy_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    return NameSearchResponse(query=body.query, count=len(results), results=[NameSearchResult.model_validate(r) for r in results])
 
 
@app.get("/recipes/search/name", response_model=NameSearchResponse, tags=["Recipes"])
def search_recipes_by_name_get(
    q: str = Query(..., description="Recipe name or partial phrase"),
    limit: int = Query(5, ge=1, le=50),
    fuzzy_threshold: float = Query(0.3, ge=0.0, le=1.0),
):
    """
    Search recipes by name/title (GET).
 
    Example: `/recipes/search/name?q=butter+chicken&limit=5`
    """
    try:
        results = search_recipes_by_name(
            query=q,
            limit=limit,
            fuzzy_threshold=fuzzy_threshold,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 
    return NameSearchResponse(query=q, count=len(results), results=[NameSearchResult.model_validate(r) for r in results])
 
 
@app.get("/recipes/{recipe_id}", response_model=RecipeResult, tags=["Recipes"])
def get_recipe(recipe_id: int):
    """Fetch a single recipe by its ID."""
    try:
        with psycopg.connect(DB_URI) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, ingredients, directions, link, source
                    FROM recipe
                    WHERE id = %(id)s
                """, {"id": recipe_id})
                row = cur.fetchone()
 
        if not row:
            raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found")
 
        cols = ["id", "title", "ingredients", "directions", "link", "source"]
        result = dict(zip(cols, row))
        result["ingredients"] = _parse_ingredients(result["ingredients"])
        result["exact_count"] = 0
        result["total_ingredients"] = len(result["ingredients"])
        result["coverage"] = 0.0
        return result
 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))