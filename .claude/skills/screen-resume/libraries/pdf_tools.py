"""Resume text extraction utilities for Ally OS workflows.

Supports PDF, DOCX, and DOC files.
"""

import re
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests
from pypdf import PdfReader


def convert_gdrive_url(url: str) -> str:
    """
    Convert a Google Drive sharing URL to a direct download URL.

    Handles formats like:
    - https://drive.google.com/file/d/{ID}/view
    - https://drive.google.com/open?id={ID}

    Returns the original URL if not a Google Drive link.
    """
    # Pattern for /file/d/{ID}/view format
    match = re.search(r"drive\.google\.com/file/d/([^/]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    # Pattern for open?id={ID} format
    match = re.search(r"drive\.google\.com/open\?id=([^&]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    # Not a Google Drive URL, return as-is
    return url


def _detect_format(url: str, content: bytes) -> str:
    """Detect file format from URL extension or content magic bytes."""
    # Check URL path for extension
    path = urlparse(url).path.lower()
    if path.endswith(".docx"):
        return "docx"
    if path.endswith(".doc"):
        return "doc"
    if path.endswith(".pdf"):
        return "pdf"

    # Check magic bytes
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:4] == b"PK\x03\x04":  # ZIP header (DOCX is a ZIP)
        return "docx"
    if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # OLE2 header (.doc)
        return "doc"

    # Default to PDF for backwards compatibility
    return "pdf"


def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF bytes."""
    reader = PdfReader(BytesIO(content))
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)


def _extract_docx(content: bytes) -> str:
    """Extract text from DOCX bytes."""
    from docx import Document

    doc = Document(BytesIO(content))
    text_parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    return "\n".join(text_parts)


def _extract_doc(content: bytes) -> str:
    """Extract text from DOC bytes using macOS textutil."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        doc_path = Path(tmp_dir) / "resume.doc"
        txt_path = Path(tmp_dir) / "resume.txt"
        doc_path.write_bytes(content)

        result = subprocess.run(
            ["textutil", "-convert", "txt", "-output", str(txt_path), str(doc_path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"textutil failed: {result.stderr.decode()}")

        return txt_path.read_text()


def extract_text_from_url(url: str, timeout: int = 60) -> str:
    """
    Download a resume from a URL and extract its text content.

    Supports PDF, DOCX, and DOC files. Format is auto-detected from
    URL extension or file magic bytes.

    The file is downloaded to memory only (DOC uses a temp file for
    textutil conversion). Automatically handles Google Drive sharing links.

    Args:
        url: The URL of the resume file (supports Google Drive links).
        timeout: Request timeout in seconds.

    Returns:
        Cleaned text extracted from the resume.

    Raises:
        requests.RequestException: If the download fails.
        ValueError: If the file format is not supported.
    """
    # Convert Google Drive URLs to direct download links
    download_url = convert_gdrive_url(url)

    # Use a session to handle redirects properly
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    })

    response = session.get(download_url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()

    # Check if we got HTML instead of file (Google Drive virus scan warning)
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type and "drive.google.com" in download_url:
        # Try to extract confirm token for large files
        confirm_match = re.search(r'confirm=([^&"]+)', response.text)
        if confirm_match:
            confirm_url = f"{download_url}&confirm={confirm_match.group(1)}"
            response = session.get(confirm_url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()

    content = response.content
    fmt = _detect_format(download_url, content)

    if fmt == "pdf":
        raw_text = _extract_pdf(content)
    elif fmt == "docx":
        raw_text = _extract_docx(content)
    elif fmt == "doc":
        raw_text = _extract_doc(content)
    else:
        raise ValueError(f"Unsupported file format: {fmt}")

    return _clean_text(raw_text)


def _clean_text(text: str) -> str:
    """
    Clean extracted text by normalizing whitespace.

    Args:
        text: Raw text from extraction.

    Returns:
        Text with excessive whitespace removed.
    """
    # Replace multiple spaces with single space
    text = re.sub(r"[ \t]+", " ", text)
    # Replace 3+ newlines with 2 newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Strip leading/trailing whitespace from the whole text
    text = text.strip()

    return text
