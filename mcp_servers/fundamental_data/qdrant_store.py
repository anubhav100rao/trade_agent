"""
Qdrant vector store wrapper for financial reports.
Uses in-memory Qdrant when QDRANT_URL is not set (good for dev/testing).
Ships with a simple TF-IDF-style keyword fallback when Qdrant is unavailable.
"""
import os
import hashlib
from typing import Optional

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        VectorParams, Distance, PointStruct,
        Filter, FieldCondition, MatchValue
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

COLLECTION = "financial_reports"
VECTOR_SIZE = 384   # sentence-transformers/all-MiniLM-L6-v2 dimension


def _get_embedding(text: str) -> list[float]:
    """
    Return a dense embedding vector.
    Uses sentence-transformers when available, falls back to a
    deterministic pseudo-embedding for testing.
    """
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        return _model.encode(text, normalize_embeddings=True).tolist()
    except Exception:
        # Deterministic fallback: hash-based mock vector (no ML inference)
        h = hashlib.sha256(text.encode()).digest()
        vec = [(b / 255.0) for b in h[:VECTOR_SIZE]]
        # Normalize
        magnitude = sum(x**2 for x in vec) ** 0.5
        return [x / magnitude for x in vec] if magnitude else vec


class QdrantStore:
    """
    Wrapper around Qdrant client for financial report chunks.

    Gracefully degrades:
      - QDRANT_URL set + Qdrant running → full vector search
      - QDRANT_URL not set             → in-memory Qdrant
      - qdrant-client not installed    → in-memory list fallback
    """

    def __init__(self):
        self._fallback: list[dict] = []   # in-process fallback storage
        self._client = None

        # Only connect to Qdrant when URL is explicitly configured.
        # Avoids in-memory Qdrant mutex deadlock on macOS / Python 3.13.
        if not QDRANT_AVAILABLE:
            return

        url = os.getenv("QDRANT_URL", "").strip()
        if not url:
            return  # use _fallback list

        try:
            self._client = QdrantClient(url=url, timeout=5)
            existing = [c.name for c in self._client.get_collections().collections]
            if COLLECTION not in existing:
                self._client.create_collection(
                    collection_name=COLLECTION,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
                )
        except Exception as e:
            print(f"[qdrant] connect failed ({e}) — using list fallback")
            self._client = None

    # ── Write ────────────────────────────────────────────────────

    def upsert_chunk(self, chunk_id: str, text: str, metadata: dict) -> bool:
        """Index a text chunk with metadata into Qdrant."""
        if self._client is None:
            self._fallback.append({"id": chunk_id, "text": text, **metadata})
            return True
        try:
            vec = _get_embedding(text)
            self._client.upsert(
                collection_name=COLLECTION,
                points=[PointStruct(
                    id=abs(hash(chunk_id)) % (2**63),
                    vector=vec,
                    payload={"text": text, "chunk_id": chunk_id, **metadata},
                )],
            )
            return True
        except Exception as e:
            print(f"[qdrant] upsert error: {e}")
            return False

    # ── Read ─────────────────────────────────────────────────────

    def search(
        self,
        ticker: str,
        query: str,
        fiscal_year: Optional[int] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Semantic search filtered by ticker (and optionally fiscal_year)."""
        if self._client is None:
            return self._fallback_search(ticker, query, limit)
        try:
            must = [FieldCondition(key="ticker", match=MatchValue(value=ticker.upper()))]
            if fiscal_year:
                must.append(FieldCondition(key="fiscal_year", match=MatchValue(value=fiscal_year)))

            vec = _get_embedding(query)
            results = self._client.query_points(
                collection_name=COLLECTION,
                query=vec,
                query_filter=Filter(must=must),
                limit=limit,
            ).points

            return [
                {
                    "text": r.payload.get("text", ""),
                    "score": r.score,
                    "ticker": r.payload.get("ticker"),
                    "report_type": r.payload.get("report_type"),
                    "fiscal_year": r.payload.get("fiscal_year"),
                    "page": r.payload.get("page"),
                    "source_file": r.payload.get("source_file"),
                }
                for r in results
            ]
        except Exception as e:
            print(f"[qdrant] search error: {e}")
            return []

    def list_reports(self, ticker: str) -> list[dict]:
        """List unique source documents indexed for a ticker."""
        if self._client is None:
            seen, out = set(), []
            for c in self._fallback:
                if c.get("ticker", "").upper() == ticker.upper():
                    key = c.get("source_file", "unknown")
                    if key not in seen:
                        seen.add(key)
                        out.append({"source_file": key, "fiscal_year": c.get("fiscal_year")})
            return out
        try:
            results = self._client.scroll(
                collection_name=COLLECTION,
                scroll_filter=Filter(
                    must=[FieldCondition(key="ticker", match=MatchValue(value=ticker.upper()))]
                ),
                limit=200,
                with_payload=True,
            )[0]
            seen, out = set(), []
            for r in results:
                key = r.payload.get("source_file", "unknown")
                if key not in seen:
                    seen.add(key)
                    out.append({
                        "source_file": key,
                        "report_type": r.payload.get("report_type"),
                        "fiscal_year": r.payload.get("fiscal_year"),
                    })
            return out
        except Exception:
            return []

    def _fallback_search(self, ticker: str, query: str, limit: int) -> list[dict]:
        """Simple keyword search over in-process fallback."""
        query_words = set(query.lower().split())
        scored = []
        for item in self._fallback:
            if item.get("ticker", "").upper() != ticker.upper():
                continue
            text_words = set(item.get("text", "").lower().split())
            score = len(query_words & text_words) / max(len(query_words), 1)
            if score > 0:
                scored.append((score, item))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [
            {"text": i["text"], "score": s, "ticker": i.get("ticker")}
            for s, i in scored[:limit]
        ]
