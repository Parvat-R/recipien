from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException
from backend.models import (
    ResolveRequest, ResolveResponse, SearchRequest,
    SearchResponse, NameSearchRequest, NameSearchResponse,
    RecipeResult, NameSearchResult,
)
from fastapi import FastAPI, Query, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from backend.agent import ask_agent, extract_ingredients_from_image
import base64
from backend.search import (
    load_canonical_index,
    resolve_ingredients,
    search_recipes,
    search_recipes_by_name,
)
from fastapi.middleware.cors import CORSMiddleware


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



app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        results = search_recipes_by_name(body.query.replace('recipe', ""), body.limit, body.fuzzy_threshold)
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
        results = search_recipes_by_name(q.replace("recipe", ""), limit, fuzzy_threshold)
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
    from backend.search import _parse_ingredients, _parse_directions, DB_URI
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
    
    
    
@app.post("/chat", tags=["Chat"])
async def chat(
    prompt: str = Form(""),
    thread_id: str = Form(...),
    image: UploadFile | None = File(None),
):
    """
    Send a message to the recipe agent.
    Optionally attach an image — ingredients will be extracted and prepended to the prompt.
    """
    final_prompt = prompt

    if image:
        image_bytes = await image.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        media_type = image.content_type  # e.g. "image/jpeg"
        if media_type is None:
            media_type = "png"

        detected = extract_ingredients_from_image(image_b64, media_type)

        if prompt.strip():
            final_prompt = f"{detected} Also, {prompt}"
        else:
            final_prompt = detected

    if not final_prompt.strip():
        raise HTTPException(status_code=400, detail="Provide a prompt or an image.")

    def stream():
        for chunk in ask_agent(final_prompt, thread_id=thread_id):
            print(chunk, end="")
            yield chunk

    return StreamingResponse(stream(), media_type="text/plain") # type:ignore