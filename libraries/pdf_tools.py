"""PDF text extraction utilities for Ally OS workflows."""

import re
from io import BytesIO

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


def extract_text_from_url(url: str, timeout: int = 60) -> str:
    """
    Download a PDF from a URL and extract its text content.

    The PDF is downloaded to memory only - no file is saved to disk.
    Automatically handles Google Drive sharing links.

    Args:
        url: The URL of the PDF file to download (supports Google Drive links).
        timeout: Request timeout in seconds.

    Returns:
        Cleaned text extracted from the PDF.

    Raises:
        requests.RequestException: If the download fails.
        pypdf.errors.PdfReadError: If the PDF cannot be parsed.
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

    # Check if we got HTML instead of PDF (Google Drive virus scan warning)
    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type and "drive.google.com" in download_url:
        # Try to extract confirm token for large files
        confirm_match = re.search(r'confirm=([^&"]+)', response.text)
        if confirm_match:
            confirm_url = f"{download_url}&confirm={confirm_match.group(1)}"
            response = session.get(confirm_url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()

    pdf_bytes = BytesIO(response.content)
    reader = PdfReader(pdf_bytes)

    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)

    raw_text = "\n".join(text_parts)
    cleaned_text = _clean_text(raw_text)

    return cleaned_text


def _clean_text(text: str) -> str:
    """
    Clean extracted PDF text by normalizing whitespace.

    Args:
        text: Raw text from PDF extraction.

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
