import psycopg
import json


def _parse_ingredients(value) -> list[str]:
    """recipe.ingredients is stored as a JSON string; parse it to a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []

DB_URI = "postgresql://postgres:root@localhost:5432/postgres"

def search_recipes_by_name(
    query: str,
    limit: int = 5,
    fuzzy_threshold: float = 0.3,
) -> list[dict]:
    """
    Two-phase name search:
      Phase 1 — tsvector full-text search (fast, ranked by ts_rank_cd).
                 Uses a GIN index on to_tsvector('english', title).
      Phase 2 — trigram similarity fallback via pg_trgm (already installed).
                 Kicks in only when FTS returns fewer results than `limit`.

    Required one-time migration (run once in your DB):
        CREATE INDEX IF NOT EXISTS idx_recipe_title_fts
            ON recipe USING GIN (to_tsvector('english', title));

        CREATE INDEX IF NOT EXISTS idx_recipe_title_trgm
            ON recipe USING GIN (title gin_trgm_ops);
    """
    with psycopg.connect(DB_URI) as conn:
        with conn.cursor() as cur:

            # ── Phase 1: full-text search ────────────────────────────────────
            # plainto_tsquery turns "butter chicken" → 'butter' & 'chicken'
            # ts_rank_cd scores by cover density (position-aware)
            cur.execute("""
                SELECT
                    id,
                    title,
                    ingredients,
                    directions,
                    link,
                    source,
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

            # ── Phase 2: trigram fallback ────────────────────────────────────
            fuzzy_rows = []
            remaining = limit - len(fts_rows)
            if remaining > 0:
                cur.execute("""
                    SELECT
                        id,
                        title,
                        ingredients,
                        directions,
                        link,
                        source,
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
                results.append(r)
            return results


def search_recipes(
    user_ingredients: list[str],
    limit: int = 5,
    fuzzy_threshold: float = 0.4,
) -> list[dict]:
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
                        SELECT unnest(%(user_ingredients)s::text[])
                    )) AS exact_count,
                    array_length(i.ingredients, 1) AS total_ingredients
                FROM ingredients i
                WHERE i.ingredients && %(user_ingredients)s::text[]
                ORDER BY exact_count DESC,
                         cardinality(ARRAY(
                             SELECT unnest(i.ingredients)
                             INTERSECT
                             SELECT unnest(%(user_ingredients)s::text[])
                         ))::float / NULLIF(array_length(i.ingredients, 1), 0) DESC
                LIMIT %(limit)s
            """, {"user_ingredients": user_ingredients, "limit": limit})

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
                    "search_text": " ".join(user_ingredients),
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
                result["exact_count"] = meta[2]
                result["total_ingredients"] = meta[3]
                result["coverage"] = round(meta[2] / meta[3], 2) if meta[3] else 0
                results.append(result)

            return results