# Ingestion Pipelines

Unstructured financial data (PDFs, news) must be indexed into Qdrant before the Fundamental Analyst can use RAG-powered retrieval. The ingestion pipelines are standalone CLI scripts.

> **Note:** Qdrant indexing is optional. The system works without it — the Fundamental Analyst will use only yfinance metrics when no documents are indexed.

---

## PDF Pipeline

**File:** `ingestion/pdf_pipeline.py`

Indexes annual reports, earnings call transcripts, DRHP, and quarterly result PDFs into Qdrant.

### Pipeline steps

```
PDF file
  │
  ├─ pdfplumber    → extracts text + tables page-by-page
  │                  Tables are converted to pipe-separated markdown
  │
  ├─ Chunker       → sliding window (1200 chars / ~300 tokens)
  │                  20% overlap between consecutive chunks
  │
  └─ Qdrant        → upsert with metadata:
                       ticker, report_type, fiscal_year,
                       source_file, page_number
```

### Usage

```bash
# Annual report
python -m ingestion.pdf_pipeline \
  --file /path/to/RELIANCE_AR_FY25.pdf \
  --ticker RELIANCE \
  --report-type annual_report \
  --fiscal-year 2025

# Quarterly results
python -m ingestion.pdf_pipeline \
  --file /path/to/INFY_Q3FY25_Results.pdf \
  --ticker INFY \
  --report-type quarterly_results \
  --fiscal-year 2025

# DRHP
python -m ingestion.pdf_pipeline \
  --file /path/to/COMPANY_DRHP.pdf \
  --ticker COMPANY \
  --report-type drhp
```

### Parameters

| Parameter | Required | Options |
|---|---|---|
| `--file` | ✅ | Path to PDF |
| `--ticker` | ✅ | NSE symbol e.g. `RELIANCE` |
| `--report-type` | ❌ | `annual_report`, `earnings_call`, `drhp`, `quarterly_results` |
| `--fiscal-year` | ❌ | Integer e.g. `2025` |

### Programmatic usage (Python)

```python
from ingestion.pdf_pipeline import ingest_pdf

chunks_indexed = ingest_pdf(
    pdf_path="/path/to/report.pdf",
    ticker="RELIANCE",
    report_type="annual_report",
    fiscal_year=2025,
    verbose=True,
)
print(f"Indexed {chunks_indexed} chunks")
```

### PDF recommendations

| Report type | Where to find |
|---|---|
| Annual reports | NSE filing portal, company investor relations page |
| Quarterly results | NSE/BSE announcements |
| Earnings call transcripts | Company IR page, Motilal Oswal, Edelweiss |
| DRHP | SEBI EFTS (`efts.sebi.gov.in`) |

---

## News Pipeline

**File:** `ingestion/news_pipeline.py`

Polls MoneyControl and Economic Times RSS feeds and indexes recent articles into Qdrant. Designed to run on a schedule (cron/Celery).

### Usage

```bash
# Index news for multiple tickers (last 6 hours)
python -m ingestion.news_pipeline \
  --tickers RELIANCE INFY TATAMOTORS HDFCBANK \
  --hours 6

# Wider net for end-of-day sweep
python -m ingestion.news_pipeline \
  --tickers RELIANCE INFY WIPRO TATAMOTORS HDFCBANK ICICIBANK \
  --hours 24
```

### Cron example

```cron
# Run every hour during market hours (Mon-Fri, 9am-4pm IST)
0 9-16 * * 1-5 /path/to/venv/bin/python -m ingestion.news_pipeline \
  --tickers RELIANCE INFY TATAMOTORS HDFCBANK NIFTY --hours 2
```

### Programmatic usage

```python
from ingestion.news_pipeline import ingest_news

total = ingest_news(
    tickers=["RELIANCE", "INFY"],
    hours_back=6,
    verbose=True,
)
```

---

## Qdrant Store API

Both pipelines write through `mcp_servers/fundamental_data/qdrant_store.py`:

```python
from mcp_servers.fundamental_data.qdrant_store import QdrantStore

store = QdrantStore()

# Write
store.upsert_chunk(
    chunk_id="unique-id",
    text="Revenue grew 18% YoY to ₹2.3L crore in FY25.",
    metadata={
        "ticker": "RELIANCE",
        "fiscal_year": 2025,
        "report_type": "annual_report",
        "source_file": "RELIANCE_AR_FY25.pdf",
        "page": 42,
    },
)

# Search
results = store.search("RELIANCE", "revenue growth", fiscal_year=2025, limit=5)

# List indexed reports
reports = store.list_reports("RELIANCE")
```

### Embeddings

When `sentence-transformers` is installed, chunks are embedded using `all-MiniLM-L6-v2` (384 dimensions) for semantic search. Without it, a hash-based deterministic fallback is used (structural correctness, no semantic quality).

```bash
pip install sentence-transformers  # ~90MB, optional but recommended
```
