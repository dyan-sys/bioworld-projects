"""
Post-processor: apply OpenAlly-style accent colors to slide titles.

For every content slide title, the last meaningful word (or word group) is
colored amber #C4883A — matching the openally.io design pattern where the
key phrase at the end of a headline gets the accent color.

Section slide titles are already amber via style_config. Title slide subtitle
gets steel blue on the last word.

Usage (called automatically by run_code_jam.py):
    python3 .claude/skills/code-jam/workflows/post_process.py --pres-id <id>
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / ".claude/skills/md-to-slides/libraries"))
from slides_auth import get_slides_services

TITLE_TYPES = {"TITLE", "CENTERED_TITLE"}

# Gradient: amber #C4883A → steel blue #7BACC4
GRAD_START = (0.769, 0.533, 0.227)
GRAD_END   = (0.482, 0.675, 0.769)

# Number of words to accent at the end of a title.
SHORT_TITLE_THRESHOLD = 4  # ≤ this many words → accent 1 word; else 2


def lerp_color(t: float) -> dict:
    """Interpolate between GRAD_START and GRAD_END for t in [0, 1]."""
    r = GRAD_START[0] + (GRAD_END[0] - GRAD_START[0]) * t
    g = GRAD_START[1] + (GRAD_END[1] - GRAD_START[1]) * t
    b = GRAD_START[2] + (GRAD_END[2] - GRAD_START[2]) * t
    return {"red": r, "green": g, "blue": b}


def get_plain_text(text_obj: dict) -> str:
    """Concatenate all textRun content from a text object."""
    result = ""
    for te in text_obj.get("textElements", []):
        if "textRun" in te:
            result += te["textRun"].get("content", "")
    return result


def accent_last_words(text: str, n_words: int) -> tuple[int, int] | None:
    """
    Return (start_index, end_index) of the last n_words in text,
    excluding any trailing newline.
    """
    stripped = text.rstrip("\n")
    if not stripped:
        return None

    words = stripped.split()
    if not words:
        return None

    n = min(n_words, len(words))
    accent_phrase = " ".join(words[-n:])

    # Find the last occurrence of this phrase in the stripped text
    idx = stripped.rfind(accent_phrase)
    if idx == -1:
        return None

    return idx, idx + len(accent_phrase)


def gradient_requests(object_id: str, span: tuple[int, int]) -> list[dict]:
    """
    Return one updateTextStyle request per character in span,
    each with an interpolated color from GRAD_START → GRAD_END.
    This creates a fake gradient effect at character resolution.
    """
    start, end = span
    length = end - start
    if length <= 0:
        return []
    reqs = []
    for i in range(length):
        t = i / max(length - 1, 1)
        color = lerp_color(t)
        reqs.append({
            "updateTextStyle": {
                "objectId": object_id,
                "textRange": {
                    "type": "FIXED_RANGE",
                    "startIndex": start + i,
                    "endIndex": start + i + 1,
                },
                "style": {"foregroundColor": {"opaqueColor": {"rgbColor": color}}},
                "fields": "foregroundColor",
            }
        })
    return reqs


def build_accent_requests(slide: dict) -> list[dict]:
    reqs = []

    for el in slide.get("pageElements", []):
        shape = el.get("shape", {})
        ph = shape.get("placeholder", {})
        ph_type = ph.get("type", "")
        text_obj = shape.get("text", {})

        if not text_obj:
            continue

        plain = get_plain_text(text_obj)
        if not plain.strip():
            continue

        oid = el["objectId"]

        if ph_type in TITLE_TYPES:
            word_count = len(plain.split())
            n = 1 if word_count <= SHORT_TITLE_THRESHOLD else 2
            span = accent_last_words(plain, n)
            if span:
                reqs.extend(gradient_requests(oid, span))

        elif ph_type == "SUBTITLE":
            span = accent_last_words(plain, 1)
            if span:
                reqs.extend(gradient_requests(oid, span))

    return reqs


def run(pres_id: str):
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json"))
    os.environ["GOOGLE_CREDENTIALS_PATH"] = creds_path

    slides_svc, _ = get_slides_services()
    pres = slides_svc.presentations().get(presentationId=pres_id).execute()

    all_reqs = []
    for slide in pres.get("slides", []):
        all_reqs.extend(build_accent_requests(slide))

    if not all_reqs:
        print("  No titles found to accent.")
        return

    print(f"  Applying accent colors to {len(all_reqs)} title(s)...")
    slides_svc.presentations().batchUpdate(
        presentationId=pres_id, body={"requests": all_reqs}
    ).execute()
    print("  ✅ Accent colors applied.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pres-id", required=True)
    args = parser.parse_args()
    run(args.pres_id)


if __name__ == "__main__":
    main()
