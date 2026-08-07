"""
Document Parsers — extract plain text from various file types.

Supported:
  - PDF          → PyMuPDF (fitz)
  - DOCX         → python-docx
  - HTML/webpage → httpx + BeautifulSoup
  - TXT / MD     → direct UTF-8 decode

All parsers return a plain text string.
"""
from __future__ import annotations

import io
from typing import Optional


def parse_pdf(content: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is required for PDF parsing. "
            "Run: pip install pymupdf"
        )

    text_parts: list[str] = []
    with fitz.open(stream=io.BytesIO(content), filetype="pdf") as doc:
        for page in doc:
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def parse_docx(content: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError(
            "python-docx is required for DOCX parsing. "
            "Run: pip install python-docx"
        )

    doc = Document(io.BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def parse_html(content: bytes) -> str:
    """Extract readable text from HTML bytes using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError(
            "beautifulsoup4 is required for HTML parsing. "
            "Run: pip install beautifulsoup4"
        )

    soup = BeautifulSoup(content, "html.parser")

    # Remove script, style, nav, header, footer noise
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()

    # Prefer main content areas
    main = soup.find("main") or soup.find("article") or soup.find("body") or soup
    text = main.get_text(separator="\n")

    # Collapse excessive blank lines
    lines = [line.strip() for line in text.splitlines()]
    clean_lines = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                clean_lines.append("")
            prev_blank = True
        else:
            clean_lines.append(line)
            prev_blank = False

    return "\n".join(clean_lines).strip()


def parse_text(content: bytes, encoding: str = "utf-8") -> str:
    """Decode plain text / markdown bytes."""
    try:
        return content.decode(encoding)
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


async def _fetch_wikipedia(url: str, timeout: int) -> tuple[bytes, str]:
    """
    Use Wikipedia's official REST API for clean plain-text extraction.
    Avoids the 403 that Wikipedia returns to all HTTP scrapers.
    Supports any language subdomain (en, de, fr, etc.)
    """
    import re
    import httpx

    lang_match = re.search(r"https?://([a-z]+)\.wikipedia\.org", url)
    title_match = re.search(r"/wiki/([^#?]+)", url)
    if not lang_match or not title_match:
        raise ValueError(f"Cannot parse Wikipedia URL: {url}")

    lang = lang_match.group(1)
    title = title_match.group(1)

    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",   # returns clean text, no HTML
        "titles": title,
        "format": "json",
        "redirects": "1",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        resp = await client.get(api_url, params=params)
        resp.raise_for_status()
        data = resp.json()

    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()))
    text = page.get("extract", "")
    if not text:
        raise ValueError(f"Wikipedia returned no content for: {title}")

    # Prepend title as heading
    full_text = f"# {page.get('title', title)}\n\n{text}"
    return full_text.encode("utf-8"), "text/plain"


async def fetch_url(url: str, timeout: int = 30) -> tuple[bytes, str]:
    """
    Fetch a URL and return (bytes, mime_type).

    Special cases:
      - wikipedia.org  → uses the official /w/api.php for clean plain text
      - everything else → httpx with browser-like headers
    """
    try:
        import httpx
    except ImportError:
        raise RuntimeError(
            "httpx is required for URL fetching. "
            "Run: pip install httpx"
        )

    # ── Wikipedia special-case ────────────────────────────────────────────────
    if "wikipedia.org/wiki/" in url:
        return await _fetch_wikipedia(url, timeout)

    # ── Generic browser-like fetch ────────────────────────────────────────────
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers=_HEADERS,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "text/html").split(";")[0].strip()
        return response.content, content_type


def parse_csv(content: bytes) -> str:
    """
    Parses CSV bytes row-by-row into self-contained semantic records so headers are preserved per row.
    """
    import csv

    raw_text = parse_text(content)
    lines = raw_text.splitlines()
    if not lines:
        return ""

    reader = csv.reader(lines)
    rows = list(reader)
    if not rows:
        return ""

    headers = [h.strip() for h in rows[0]]
    formatted_records = []

    for idx, row in enumerate(rows[1:], start=1):
        if not any(cell.strip() for cell in row if isinstance(cell, str)):
            continue
        record_lines = [f"--- CSV ROW #{idx} ---"]
        for header, val in zip(headers, row):
            val_str = str(val).strip()
            if val_str:
                record_lines.append(f"{header}: {val_str}")
        formatted_records.append("\n".join(record_lines))

    return "\n\n".join(formatted_records)


def parse_excel(content: bytes) -> str:
    """
    Extracts text from Excel (.xlsx) files worksheet-by-worksheet, row-by-row.
    """
    try:
        import openpyxl
    except ImportError:
        # Fallback to plain text if openpyxl is missing
        return parse_text(content)

    wb = openpyxl.load_workbook(filename=io.BytesIO(content), data_only=True)
    sheets_output = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
        formatted_records = [f"=== SHEET: {sheet_name} ({len(rows)-1} rows) ==="]

        for idx, row in enumerate(rows[1:], start=1):
            if not any(val is not None and str(val).strip() for val in row):
                continue
            record_lines = [f"--- [{sheet_name}] ROW #{idx} ---"]
            for header, val in zip(headers, row):
                if val is not None and str(val).strip():
                    record_lines.append(f"{header}: {str(val).strip()}")
            formatted_records.append("\n".join(record_lines))

        sheets_output.append("\n\n".join(formatted_records))

    return "\n\n".join(sheets_output)


def parse_by_mime(content: bytes, mime_type: Optional[str]) -> str:
    """Dispatch to the right parser based on MIME type."""
    mime = (mime_type or "text/plain").lower()

    if "pdf" in mime:
        return parse_pdf(content)
    elif "wordprocessingml" in mime or mime.endswith(".docx"):
        return parse_docx(content)
    elif "spreadsheetml" in mime or "excel" in mime or mime.endswith(".xlsx") or mime.endswith(".xls"):
        return parse_excel(content)
    elif "csv" in mime or mime.endswith(".csv"):
        return parse_csv(content)
    elif "html" in mime:
        return parse_html(content)
    else:
        # TXT, MD, and unknown types — treat as plain text
        return parse_text(content)

