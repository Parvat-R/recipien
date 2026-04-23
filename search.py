import os
import json
from dotenv import load_dotenv
import psycopg
from rapidfuzz.process import extractOne

load_dotenv("/.env")
DB_URI = os.getenv("DB_URI", "postgresql://postgres:root@localhost:5432/postgres")

# ── Canonical index (loaded once at startup) ──────────────────────────────────

_canonical_terms: list[str] = []
_raw_to_canonical: dict[str, str] = {}


def load_canonical_index():
    """Load the ingredient_canonical table into memory for fast lookup."""
    global _canonical_terms, _raw_to_canonical
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT raw, canonical FROM ingredient_canonical")
            rows = cur.fetchall()
    _raw_to_canonical = {raw: canon for raw, canon in rows}
    _canonical_terms = sorted(set(_raw_to_canonical.values()))
    print(f"Loaded {len(_raw_to_canonical):,} raw → canonical mappings "
          f"({len(_canonical_terms):,} canonical terms)")


def resolve_ingredient(user_input: str) -> str:
    """
    Resolve a user-typed ingredient to its canonical form.
    1. Exact match in lookup table
    2. Fuzzy match against canonical list (fallback)
    """
    cleaned = user_input.strip().lower()

    # Exact match
    if cleaned in _raw_to_canonical:
        return _raw_to_canonical[cleaned]

    # Fuzzy match — returns canonical term even for typos
    if _canonical_terms:
        match, score, _ = extractOne(cleaned, _canonical_terms)
        if score >= 80:
            return match

    # No match — return cleaned input as-is
    return cleaned


def resolve_ingredients(user_inputs: list[str]) -> dict[str, str]:
    """Resolve a list of ingredients, returning {original: canonical} mapping."""
    return {ing: resolve_ingredient(ing) for ing in user_inputs}


# ── Recipe search by ingredients ──────────────────────────────────────────────

def search_recipes(
    user_ingredients: list[str],
    limit: int = 5,
    fuzzy_threshold: float = 0.4,
) -> list[dict]:
    # Resolve each ingredient to its canonical form before searching
    resolved = [resolve_ingredient(ing) for ing in user_ingredients]

    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:

            # Phase 1: exact match via GIN index
            cur.execute("""
                SELECT
                    i.id,
                    i.ingredients,
                    cardinality(ARRAY(
                        SELECT unnest(i.ingredients)
                        INTERSECT
                        SELECT unnest(%(resolved)s::text[])
                    )) AS exact_count,
                    array_length(i.ingredients, 1) AS total_ingredients
                FROM ingredients i
                WHERE i.ingredients && %(resolved)s::text[]
                ORDER BY exact_count DESC,
                         cardinality(ARRAY(
                             SELECT unnest(i.ingredients)
                             INTERSECT
                             SELECT unnest(%(resolved)s::text[])
                         ))::float / NULLIF(array_length(i.ingredients, 1), 0) DESC
                LIMIT %(limit)s
            """, {"resolved": resolved, "limit": limit})

            exact_rows = cur.fetchall()
            exact_ids = {row[0] for row in exact_rows}

            # Phase 2: fuzzy fallback
            fuzzy_rows = []
            remaining = limit - len(exact_rows)
            if remaining > 0:
                cur.execute("""
                    SELECT
                        i.id,
                        i.ingredients,
                        0 AS exact_count,
                        array_length(i.ingredients, 1) AS total_ingredients
                    FROM ingredients i
                    WHERE
                        i.id != ALL(%(exclude_ids)s::int[])
                        AND similarity(
                            ingredients_to_text(i.ingredients),
                            %(search_text)s
                        ) > %(threshold)s
                    ORDER BY similarity(
                        ingredients_to_text(i.ingredients),
                        %(search_text)s
                    ) DESC
                    LIMIT %(remaining)s
                """, {
                    "exclude_ids": list(exact_ids) or [None],
                    "search_text": " ".join(resolved),
                    "threshold": fuzzy_threshold,
                    "remaining": remaining,
                })
                fuzzy_rows = cur.fetchall()

            all_ids = [row[0] for row in exact_rows + fuzzy_rows]
            all_meta = {row[0]: row for row in exact_rows + fuzzy_rows}

            if not all_ids:
                return []

            # Phase 3: fetch full recipe data
            cur.execute("""
                SELECT id, title, ingredients, directions, link, source
                FROM recipe
                WHERE id = ANY(%(ids)s::int[])
            """, {"ids": all_ids})

            recipe_rows = cur.fetchall()
            recipe_cols = [desc[0] for desc in cur.description]
            recipe_map = {row[0]: dict(zip(recipe_cols, row)) for row in recipe_rows}

            results = []
            for rid in all_ids:
                if rid not in recipe_map:
                    continue
                meta = all_meta[rid]
                result = recipe_map[rid]
                result["ingredients"] = _parse_ingredients(result["ingredients"])
                result["directions"] = _parse_directions(result["directions"])
                result["exact_count"] = meta[2]
                result["total_ingredients"] = meta[3]
                result["coverage"] = round(meta[2] / meta[3], 2) if meta[3] else 0
                results.append(result)

            return results


# ── Recipe search by name ─────────────────────────────────────────────────────

def search_recipes_by_name(
    query: str,
    limit: int = 5,
    fuzzy_threshold: float = 0.3,
) -> list[dict]:
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:

            # Phase 1: full-text search
            cur.execute("""
                SELECT
                    id, title, ingredients, directions, link, source,
                    'fts'::text AS match_type,
                    ts_rank_cd(
                        to_tsvector('english', title),
                        plainto_tsquery('english', %(query)s)
                    ) AS rank
                FROM recipe
                WHERE to_tsvector('english', title) @@ plainto_tsquery('english', %(query)s)
                ORDER BY rank DESC
                LIMIT %(limit)s
            """, {"query": query, "limit": limit})

            fts_rows = cur.fetchall()
            fts_ids = {row[0] for row in fts_rows}

            # Phase 2: trigram fallback
            fuzzy_rows = []
            remaining = limit - len(fts_rows)
            if remaining > 0:
                cur.execute("""
                    SELECT
                        id, title, ingredients, directions, link, source,
                        'fuzzy'::text AS match_type,
                        similarity(title, %(query)s) AS rank
                    FROM recipe
                    WHERE
                        id != ALL(%(exclude_ids)s::int[])
                        AND similarity(title, %(query)s) > %(threshold)s
                    ORDER BY rank DESC
                    LIMIT %(remaining)s
                """, {
                    "query": query,
                    "exclude_ids": list(fts_ids) or [None],
                    "threshold": fuzzy_threshold,
                    "remaining": remaining,
                })
                fuzzy_rows = cur.fetchall()

            cols = ["id", "title", "ingredients", "directions", "link", "source", "match_type", "rank"]
            results = []
            for row in fts_rows + fuzzy_rows:
                r = dict(zip(cols, row))
                r["ingredients"] = _parse_ingredients(r["ingredients"])
                r["directions"] = _parse_directions(r["directions"])
                results.append(r)
            return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_ingredients(value) -> list[str]:
    """recipe.ingredients is stored as a JSON string; parse it to a list."""
    import json
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []

def _parse_directions(value) -> list[str]:
    """recipe.directions is stored as a JSON string; parse it to a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [value]
        except (json.JSONDecodeError, ValueError):
            return [value]
    return []