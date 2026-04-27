import os
import json
import requests
from langchain.tools import tool

API_BASE = os.getenv("RECIPE_API_BASE", "http://localhost:8000")


@tool
def search_recipes_by_ingredients(ingredients: str, limit: int | str = 5) -> str:
    """
    Search for recipes based on ingredients the user has.
    Use this whenever the user mentions food ingredients they have at home.

    Args:
        ingredients: Comma separated list of ingredient names. No quantities,
                     units, or descriptors. E.g. "chicken,garlic,butter"
        limit: Number of recipes to return (default 5, max 50)

    Returns:
        A summary of matching recipes with coverage info.
    """
    print(ingredients, limit)
    if isinstance(limit, str):
        try:
            limit = int(limit)
        except ValueError:
            limit = 5
    ingredient_list = [i.strip() for i in ingredients.split(",") if i.strip()]
    if not ingredient_list:
        return "No ingredients provided. Please pass a comma-separated list of ingredients."

    try:
        response = requests.get(
            f"{API_BASE}/recipes/search",
            params=[("ingredients", ing) for ing in ingredient_list] + [("limit", limit)],
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        return "Could not connect to the recipe API. Make sure it is running."
    except requests.exceptions.HTTPError as e:
        return f"API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
    print("L45:",data)
    if data["count"] == 0:
        return f"No recipes found for ingredients: {', '.join(ingredient_list)}. Try fewer or different ingredients."

    # Show what was resolved (typo correction etc.)
    resolved = data.get("resolved", ingredient_list)
    if resolved != ingredient_list:
        lines = [f"(Interpreted as: {', '.join(resolved)})\n"]
    else:
        lines = []

    return json.dumps(data["results"], indent=2)


@tool
def search_recipes_by_name(query: str, limit: int | str = 5) -> str:
    """
    Search for recipes by name or title.
    Use this when the user asks for a specific dish by name,
    e.g. "find me a butter chicken recipe" or "show me carbonara recipes".

    Args:
        query: Recipe name or partial title to search for. E.g. "butter chicken"
        limit: Number of recipes to return (default 5, max 50)

    Returns:
        A list of matching recipes.
    """
    if isinstance(limit, str):
        try:
            limit = int(limit)
        except ValueError:
            limit = 5
    try:
        response = requests.get(
            f"{API_BASE}/recipes/search/name",
            params={"q": query, "limit": limit},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        return "Could not connect to the recipe API. Make sure it is running."
    except requests.exceptions.HTTPError as e:
        return f"API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"

    if data["count"] == 0:
        return f"No recipes found for '{query}'. Try a different name or spelling."

    lines = []
    for r in data["results"]:
        match_note = "exact match" if r["match_type"] == "fts" else f"fuzzy match ({r['rank']:.0%})"
        lines.append(
            f"- **{r['title']}** ({match_note})\n"
            f"  Link: {r.get('link', 'N/A')}"
        )

    return "\n".join(lines)


@tool
def get_recipe_details(recipe_id: int) -> str:
    """
    Get the full details of a recipe including ingredients with quantities
    and step-by-step directions.
    Use this when the user asks to see the full recipe or cooking instructions
    for a specific recipe.

    Args:
        recipe_id: The numeric ID of the recipe (from search results)

    Returns:
        Full recipe with ingredients and directions.
    """
    try:
        response = requests.get(
            f"{API_BASE}/recipes/{recipe_id}",
            timeout=10,
        )
        response.raise_for_status()
        r = response.json()
    except requests.exceptions.ConnectionError:
        return "Could not connect to the recipe API. Make sure it is running."
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"Recipe {recipe_id} not found."
        return f"API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"

    ingredients_text = "\n".join(f"  - {ing}" for ing in r["ingredients"])
    directions_text = "\n".join(f"  {i+1}. {step}" for i, step in enumerate(r["directions"]))

    return (
        f"# {r['title']}\n\n"
        f"**Ingredients:**\n{ingredients_text}\n\n"
        f"**Directions:**\n{directions_text}\n\n"
        f"Source: {r.get('link', 'N/A')}"
    )


@tool
def resolve_ingredients(ingredients: str) -> str:
    """
    Resolve messy or misspelled ingredient names to their canonical forms.
    Use this to check what the API understands before searching,
    or when the user types an unusual spelling.

    Args:
        ingredients: Comma separated ingredient names to resolve.
                     E.g. "zuchini,mozzerella,tomatos"

    Returns:
        A mapping of input → canonical name for each ingredient.
    """
    ingredient_list = [i.strip() for i in ingredients.split(",") if i.strip()]
    if not ingredient_list:
        return "No ingredients provided."

    try:
        response = requests.post(
            f"{API_BASE}/ingredients/resolve",
            json={"ingredients": ingredient_list},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        return "Could not connect to the recipe API. Make sure it is running."
    except requests.exceptions.HTTPError as e:
        return f"API error: {e.response.status_code} - {e.response.text}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"

    lines = [f"  {raw} → {canonical}" for raw, canonical in data["resolved"].items()]
    return "Resolved ingredients:\n" + "\n".join(lines)


# ── All tools as a list (pass directly to your agent) ────────────────────────

recipe_tools = [
    search_recipes_by_ingredients,
    search_recipes_by_name,
    get_recipe_details,
    resolve_ingredients,
]