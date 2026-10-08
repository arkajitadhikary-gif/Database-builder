from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("judicore.groq_extractor")

SYSTEM_PROMPT = """You are a Principal Database Architect & Advanced Document Intelligence Engine.
Your mission is to perform an EXHAUSTIVE, FLAWLESS, DEVELOPER-GRADE extraction from ANY document
(e.g., Invoices, Financial Balance Sheets, Income Statements, Resumes/CVs, Academic Research Papers,
Medical Records, Technical Manuals, Legal Agreements, Product Catalogs, Price Lists, Bank Statements, Forms, or Government Notices).

You must analyze the document thoroughly and synthesize clean, professional, normalized Relational Database Tables.
CRITICAL REQUIREMENTS FOR DEVELOPER QUALITY:
1. EXHAUSTIVE EXTRACTION: Do NOT truncate, omit, or summarize away rows. If an invoice or catalog has 25 items, extract all 25 items.
2. MULTI-TABLE NORMALIZATION: If the document contains multiple distinct concepts (e.g., Header Metadata vs. Line Items vs. Taxes/Summary, or Candidate Info vs. Work Experience vs. Education), generate separate dedicated tables for each concept!
3. CLEAN SCHEMA DESIGN:
   - Column `key` MUST be clean lowercase snake_case (e.g. `item_description`, `unit_price`, `quantity`, `subtotal`, `tax_rate`, `net_amount`).
   - Column `label` MUST be clear human-readable title (e.g. "Item Description", "Unit Price", "Quantity").
   - Column `type` MUST be accurate: "string", "number", "date", or "boolean".
4. ACCURATE VALUES: Numbers must be clean numeric values (not formatted strings with currency symbols in numeric columns), dates in YYYY-MM-DD or standard format.

You must return ONLY a valid JSON object matching this schema:
{
  "document_category": "string (e.g. 'Invoice / Bill', 'Financial Statement', 'Academic Paper', 'Resume / CV', 'Contract / Agreement', 'Medical Report', 'Product Catalog', 'Technical Specification', 'Official Record', 'General Document')",
  "title": "string (Clear, descriptive title of the document)",
  "document_date": "string in YYYY-MM-DD format or null",
  "summary": "string (Concise executive summary of what this document records)",
  "key_entities": [
    {"name": "entity name", "type": "ORGANIZATION/PERSON/AMOUNT/IDENTIFIER", "value": "value"}
  ],
  "tables": [
    {
      "table_name": "string (Descriptive table name, e.g. 'Invoice Line Items', 'Financial Metrics', 'Work Experience', 'Key Findings')",
      "description": "string (Detailed description of this relational table)",
      "columns": [
        {"key": "snake_case_key", "label": "Human Readable Label", "type": "string|number|date|boolean"}
      ],
      "rows": [
        {
          "snake_case_key": "value",
          "source_page": 1
        }
      ]
    }
  ]
}

Ensure STRICT JSON format only. No markdown conversational chatter outside the JSON.
"""


@dataclass
class ExtractedTableResult:
    table_name: str
    table_slug: str
    description: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]


@dataclass
class UniversalAnalysisResult:
    document_category: str
    title: str
    document_date: str | None
    summary: str
    key_entities: list[dict[str, Any]]
    tables: list[ExtractedTableResult] = field(default_factory=list)
    model_used: str = "groq"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", value.lower()).strip()
    return re.sub(r"[-\s]+", "_", slug)[:64] or "table"


def _clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _build_document_prompt(pages: list[Any], filename: str) -> str:
    total_pages = len(pages)
    text_samples: list[str] = []

    # If small document (up to 12 pages), include every page
    # If larger document, include first 8 pages, plus middle, plus last 2 pages
    pages_to_include: list[int] = []
    if total_pages <= 12:
        pages_to_include = list(range(total_pages))
    else:
        first_part = list(range(min(8, total_pages)))
        mid_idx = total_pages // 2
        last_part = [total_pages - 2, total_pages - 1]
        pages_to_include = sorted(set(first_part + [mid_idx] + last_part))

    for idx in pages_to_include:
        if idx >= total_pages:
            continue
        page = pages[idx]
        page_num = getattr(page, "page_number", idx + 1)
        raw = getattr(page, "normalized_text", "") or getattr(page, "raw_text", "")
        # Compact extra blank lines and repetitive whitespace
        compacted = re.sub(r"\n{3,}", "\n\n", raw.strip())
        compacted = re.sub(r"[ \t]{3,}", "  ", compacted)[:2000]
        if compacted:
            text_samples.append(f"--- [PAGE {page_num} of {total_pages}] ---\n{compacted}")

    joined_text = "\n\n".join(text_samples)
    if len(joined_text) > 12000:
        joined_text = joined_text[:12000] + "\n\n[... End of document extract ...]"

    return (
        f"Filename: {filename}\n"
        f"Total Pages in PDF: {total_pages}\n\n"
        f"Extracted Document Content:\n{joined_text}\n\n"
        "Design professional normalized relational database tables for this document. "
        "Extract every row and transaction exhaustively. Return STRICT JSON."
    )


async def extract_with_groq(
    pages: list[Any],
    filename: str,
    api_key: str | None = None,
    model: str | None = None,
) -> UniversalAnalysisResult:
    settings = get_settings()
    key = api_key or settings.groq_api_key
    selected_model = model or settings.groq_model or "qwen/qwen3.8-27b"
    base_url = settings.groq_base_url.rstrip("/")

    if not key:
        logger.warning("GROQ_API_KEY is not configured; using heuristic fallback extractor")
        return _fallback_heuristic_extraction(pages, filename)

    prompt = _build_document_prompt(pages, filename)

    models_to_try = [selected_model]
    if "qwen" in selected_model:
        models_to_try.extend(["openai/gpt-oss-120b", "openai/gpt-oss-20b"])
    elif "120b" in selected_model:
        models_to_try.extend(["qwen/qwen3.8-27b", "openai/gpt-oss-20b"])
    else:
        models_to_try.extend(["qwen/qwen3.8-27b", "openai/gpt-oss-120b"])

    last_error: Exception | None = None

    for candidate_model in dict.fromkeys(models_to_try):
        try:
            logger.info("Extracting document '%s' with Groq model '%s'", filename, candidate_model)
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": candidate_model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "Groq call failed with status %d: %s",
                        response.status_code,
                        response.text[:300],
                    )
                    continue

                payload = response.json()
                content = payload["choices"][0]["message"]["content"]
                raw_json = _clean_json_text(content)
                parsed = json.loads(raw_json)
                return _parse_groq_json(parsed, candidate_model, filename)
        except Exception as exc:
            logger.warning("Error using Groq model %s: %s", candidate_model, exc)
            last_error = exc

    logger.warning("All Groq models failed (%s); falling back to heuristic extraction", last_error)
    return _fallback_heuristic_extraction(pages, filename)


def _parse_groq_json(data: dict[str, Any], model_name: str, filename: str) -> UniversalAnalysisResult:
    category = str(data.get("document_category") or "General Document").strip()
    title = str(data.get("title") or filename).strip()
    date_str = data.get("document_date")
    if date_str and not isinstance(date_str, str):
        date_str = str(date_str)
    summary = str(data.get("summary") or "").strip()
    entities = data.get("key_entities") if isinstance(data.get("key_entities"), list) else []

    raw_tables = data.get("tables") or []
    if not isinstance(raw_tables, list):
        raw_tables = []

    table_results: list[ExtractedTableResult] = []
    for idx, t in enumerate(raw_tables):
        if not isinstance(t, dict):
            continue
        name = str(t.get("table_name") or f"Table {idx + 1}").strip()
        slug = _slugify(name)
        description = str(t.get("description") or f"Extracted from {filename}").strip()
        columns = t.get("columns") or []
        if not isinstance(columns, list) or not columns:
            continue

        valid_columns: list[dict[str, Any]] = []
        for col in columns:
            if isinstance(col, dict) and "key" in col:
                valid_columns.append(
                    {
                        "key": str(col["key"]),
                        "label": str(col.get("label") or col["key"]),
                        "type": str(col.get("type") or "string"),
                    }
                )

        if not valid_columns:
            continue

        raw_rows = t.get("rows") or []
        if not isinstance(raw_rows, list):
            raw_rows = []

        valid_rows: list[dict[str, Any]] = []
        col_keys = [c["key"] for c in valid_columns]

        for r_idx, row in enumerate(raw_rows, start=1):
            if isinstance(row, dict):
                clean_row: dict[str, Any] = {}
                for k in col_keys:
                    clean_row[k] = row.get(k, "")
                clean_row["source_page"] = row.get("source_page", 1)
                valid_rows.append(clean_row)

        table_results.append(
            ExtractedTableResult(
                table_name=name,
                table_slug=slug,
                description=description,
                columns=valid_columns,
                rows=valid_rows,
            )
        )

    # Filter out empty tables (0 rows) if other non-empty tables exist
    non_empty = [t for t in table_results if len(t.rows) > 0]
    if non_empty:
        table_results = non_empty

    # If no tables were extracted, synthesize an Overview Table
    if not table_results:
        table_results.append(_synthesize_overview_table(data, filename))

    return UniversalAnalysisResult(
        document_category=category,
        title=title,
        document_date=date_str,
        summary=summary,
        key_entities=entities,
        tables=table_results,
        model_used=f"{model_name} (Groq)",
    )


def _synthesize_overview_table(data: dict[str, Any], filename: str) -> ExtractedTableResult:
    columns = [
        {"key": "property", "label": "Property", "type": "string"},
        {"key": "value", "label": "Value", "type": "string"},
    ]
    rows = [
        {"property": "Document Title", "value": data.get("title") or filename, "source_page": 1},
        {"property": "Category", "value": data.get("document_category") or "General Document", "source_page": 1},
        {"property": "Date", "value": str(data.get("document_date") or "N/A"), "source_page": 1},
        {"property": "Summary", "value": data.get("summary") or "Extracted document", "source_page": 1},
    ]
    return ExtractedTableResult(
        table_name="Document Metadata & Overview",
        table_slug="document_overview",
        description="Core metadata and properties of the document",
        columns=columns,
        rows=rows,
    )


def _fallback_heuristic_extraction(pages: list[Any], filename: str) -> UniversalAnalysisResult:
    """Heuristic fallback extractor when Groq is unavailable."""
    sample_text = "\n".join(
        getattr(p, "normalized_text", "") for p in pages[:5]
    ).strip()

    title = filename.replace("_", " ").replace("-", " ")
    if title.lower().endswith(".pdf"):
        title = title[:-4]

    category = "General Document"
    sample_lower = sample_text.lower()
    if any(k in sample_lower for k in ["invoice", "tax invoice", "bill to", "amount due", "gstin"]):
        category = "Invoice / Bill"
    elif any(k in sample_lower for k in ["balance sheet", "income statement", "cash flow", "financial report"]):
        category = "Financial Statement"
    elif any(k in sample_lower for k in ["abstract", "introduction", "methodology", "references", "doi:"]):
        category = "Academic Paper"
    elif any(k in sample_lower for k in ["curriculum vitae", "resume", "work experience", "skills", "education"]):
        category = "Resume / CV"
    elif any(k in sample_lower for k in ["agreement", "terms and conditions", "party of the first part", "whereas"]):
        category = "Contract / Agreement"
    elif any(k in sample_lower for k in ["act", "supreme court", "high court", "judgment", "section"]):
        category = "Legal Document"

    # Extract pages summary table
    columns = [
        {"key": "page_number", "label": "Page #", "type": "number"},
        {"key": "word_count", "label": "Word Count", "type": "number"},
        {"key": "preview", "label": "Text Preview", "type": "string"},
    ]
    rows: list[dict[str, Any]] = []
    for p in pages:
        p_num = getattr(p, "page_number", 1)
        p_text = getattr(p, "normalized_text", "") or ""
        words = len(p_text.split())
        preview = (p_text[:120] + "...") if len(p_text) > 120 else p_text
        rows.append(
            {
                "page_number": p_num,
                "word_count": words,
                "preview": preview.replace("\n", " "),
                "source_page": p_num,
            }
        )

    table = ExtractedTableResult(
        table_name=f"{title} - Page Breakdown",
        table_slug="page_breakdown",
        description="Page by page structural text records",
        columns=columns,
        rows=rows,
    )

    return UniversalAnalysisResult(
        document_category=category,
        title=title,
        document_date=None,
        summary=f"Processed document containing {len(pages)} pages under category '{category}'.",
        key_entities=[],
        tables=[table],
        model_used="deterministic-heuristic",
    )
