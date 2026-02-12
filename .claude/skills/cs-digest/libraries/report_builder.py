"""
Report Builder Library — CS Digest

Reads input files, formats them as a document block for the prompt,
and saves generated reports and receipts.
"""

import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "local-data" / "cs-digest" / "input"
REPORTS_DIR = PROJECT_ROOT / "local-data" / "cs-digest" / "reports"


def read_input_files(folder: Path = None) -> list[dict]:
    """
    Read all .txt and .md files from the input folder.

    Returns a list of dicts: [{"filename": str, "content": str}, ...]
    """
    input_dir = Path(folder) if folder else DEFAULT_INPUT_DIR

    if not input_dir.exists():
        raise FileNotFoundError(
            f"Input directory not found: {input_dir}\n"
            f"Create it and drop your text files there."
        )

    files = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in (".txt", ".md")
    )

    if not files:
        raise FileNotFoundError(
            f"No .txt or .md files found in: {input_dir}"
        )

    results = []
    for f in files:
        content = f.read_text(encoding="utf-8").strip()
        results.append({"filename": f.name, "content": content})
        print(f"  Read: {f.name} ({len(content)} chars)")

    return results


def format_documents_block(files: list[dict]) -> str:
    """
    Concatenate file contents with boundary markers for the prompt.
    """
    parts = []
    for f in files:
        parts.append(f"=== Document: {f['filename']} ===\n\n{f['content']}")
    return "\n\n".join(parts)


def save_receipt(raw_response: str, date_str: str, files: list[dict]) -> Path:
    """Save a JSON receipt with metadata and raw response."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    receipt = {
        "date": date_str,
        "generated_at": datetime.now().isoformat(),
        "input_files": [f["filename"] for f in files],
        "raw_response": raw_response,
    }

    receipt_path = REPORTS_DIR / f"{date_str}_receipt.json"
    with open(receipt_path, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return receipt_path


def save_report(text: str, date_str: str) -> Path:
    """Save the markdown digest report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    report_path = REPORTS_DIR / f"{date_str}_digest.md"
    report_path.write_text(text, encoding="utf-8")

    return report_path
