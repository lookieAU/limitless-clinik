import numpy as np

from agent.repo import claims
from agent.vocab import claim_label, surface_forms
from shared.sqlite import many


def canonical_text(claim: dict) -> str:
    prefix = "NOT " if claim["polarity"] == "negative" else ""
    forms = " ".join(surface_forms(claim["subject"], claim["value"]))
    return f"{prefix}{claim['subject']}={claim['value']} (raw: '{claim['raw_text']}') {forms}"


def ensure_embeddings(ctx, rows: list[dict]) -> dict[str, np.ndarray]:
    embedder = ctx.embedder
    ids = [row["id"] for row in rows]
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    stored = many(ctx.conn, f"SELECT claim_id, model, vector FROM claim_embeddings WHERE claim_id IN ({marks})", tuple(ids))
    vectors = {item["claim_id"]: np.frombuffer(item["vector"], dtype=np.float32) for item in stored if item["model"] == embedder.name}
    missing = [row for row in rows if row["id"] not in vectors]
    if missing:
        fresh = embedder.embed([canonical_text(row) for row in missing])
        for row, vector in zip(missing, fresh, strict=True):
            ctx.conn.execute(
                "INSERT INTO claim_embeddings (claim_id, model, vector) VALUES (?, ?, ?) "
                "ON CONFLICT(claim_id) DO UPDATE SET model = excluded.model, vector = excluded.vector",
                (row["id"], embedder.name, vector.astype(np.float32).tobytes()),
            )
            vectors[row["id"]] = vector
    return vectors


def recall(ctx, user_id: str, query: str, k: int = 5, include_inactive: bool = False) -> list[dict]:
    rows = claims.all_for_user(ctx.conn, user_id, limit=500) if include_inactive else claims.live_for_user(ctx.conn, user_id)
    vectors = ensure_embeddings(ctx, rows)
    if not vectors:
        return []
    query_vector = ctx.embedder.embed([query])[0]
    scored = sorted(((float(vectors[row["id"]] @ query_vector), row) for row in rows), key=lambda item: item[0], reverse=True)
    return [
        {
            "claim_id": row["id"],
            "said": claim_label(row, "en"),
            "subject": row["subject"],
            "value": row["value"],
            "polarity": row["polarity"],
            "status": row["status"],
            "raw_text": row["raw_text"],
            "lang": row["lang"],
            "created_utc": row["created_utc"],
            "score": round(score, 3),
        }
        for score, row in scored[:k]
        if score > 0
    ]
