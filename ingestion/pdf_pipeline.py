"""
PDF ingestion pipeline.

Usage:
  python -m ingestion.pdf_pipeline --file /path/to/RELIANCE_AR_FY25.pdf \
         --ticker RELIANCE --report-type annual_report --fiscal-year 2025

Pipeline:
  PDF → pdfplumber (text + tables) → chunk (300 tokens child / 2000 parent) → Qdrant upsert
"""
import argparse
import os
import sys
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pdfplumber
from mcp_servers.fundamental_data.qdrant_store import QdrantStore

# Rough token estimate: 1 token ≈ 4 chars
CHILD_CHUNK_CHARS = 1200   # ~300 tokens
PARENT_CHUNK_CHARS = 8000  # ~2000 tokens


def _extract_text_from_pdf(pdf_path: str) -> list[dict]:
    """
    Extract text and tables page-by-page using pdfplumber.
    Returns list of dicts: {page, text, has_table}.
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tables = page.extract_tables()
            table_md = ""
            for table in (tables or []):
                if not table:
                    continue
                rows = [" | ".join(str(c or "") for c in row) for row in table]
                table_md += "\n" + "\n".join(rows) + "\n"
            combined = text + table_md
            pages.append({"page": i, "text": combined.strip(), "has_table": bool(tables)})
    return pages


def _make_chunks(pages: list[dict], chunk_size: int = CHILD_CHUNK_CHARS) -> list[dict]:
    """
    Sliding window chunker over concatenated page text.
    Returns list of {chunk_id, text, start_page, end_page}.
    """
    chunks = []
    buffer = ""
    start_page = 1
    current_page = 1

    for page_data in pages:
        page_text = page_data["text"]
        current_page = page_data["page"]
        buffer += f"\n[Page {current_page}]\n{page_text}"

        while len(buffer) >= chunk_size:
            chunk_text = buffer[:chunk_size]
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "text": chunk_text.strip(),
                "start_page": start_page,
                "end_page": current_page,
            })
            # 20% overlap
            buffer = buffer[int(chunk_size * 0.8):]
            start_page = current_page

    if buffer.strip():
        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "text": buffer.strip(),
            "start_page": start_page,
            "end_page": current_page,
        })
    return chunks


def ingest_pdf(
    pdf_path: str,
    ticker: str,
    report_type: str = "annual_report",
    fiscal_year: int | None = None,
    verbose: bool = True,
) -> int:
    """
    Full pipeline: PDF → text + tables → chunks → Qdrant.
    Returns number of chunks indexed.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    source_file = os.path.basename(pdf_path)
    store = QdrantStore()

    if verbose:
        print(f"[ingest] Reading {source_file} ...")
    pages = _extract_text_from_pdf(pdf_path)

    if verbose:
        print(f"[ingest] Extracted {len(pages)} pages → chunking ...")
    chunks = _make_chunks(pages)

    metadata_base = {
        "ticker": ticker.upper(),
        "report_type": report_type,
        "fiscal_year": fiscal_year,
        "source_file": source_file,
    }

    success = 0
    for i, chunk in enumerate(chunks):
        meta = {**metadata_base, "page": chunk["start_page"]}
        ok = store.upsert_chunk(
            chunk_id=chunk["chunk_id"],
            text=chunk["text"],
            metadata=meta,
        )
        if ok:
            success += 1
        if verbose and (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(chunks)} chunks indexed ...")

    if verbose:
        print(f"[ingest] Done — {success}/{len(chunks)} chunks indexed for {ticker.upper()}")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest a PDF into the Qdrant financial reports store")
    parser.add_argument("--file", required=True, help="Path to PDF file")
    parser.add_argument("--ticker", required=True, help="NSE ticker e.g. RELIANCE")
    parser.add_argument("--report-type", default="annual_report",
                        choices=["annual_report", "earnings_call", "drhp", "quarterly_results"],
                        help="Report type")
    parser.add_argument("--fiscal-year", type=int, default=None, help="Fiscal year e.g. 2025")
    args = parser.parse_args()

    ingest_pdf(
        pdf_path=args.file,
        ticker=args.ticker,
        report_type=args.report_type,
        fiscal_year=args.fiscal_year,
    )
