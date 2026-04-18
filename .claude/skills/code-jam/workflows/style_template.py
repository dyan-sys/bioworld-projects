"""
Style the Code Jam Google Slides template to match OpenAlly / Ally OS aesthetics.

Design system extracted from openally.io:
  - Background:      #0D0D0D  (near-black)
  - Headline:        #FFFFFF  Instrument Serif, very large
  - Body text:       #999999  DM Sans
  - Accent warm:     #C4883A  amber/gold (section headers, highlights)
  - Accent cool:     #7BACC4  steel blue (content highlights)
  - Card bg:         #181818  slightly lighter than page
  - Border:          #2A2A2A  subtle dark
  - Section label:   small caps, letter-spaced pill shape

Run once to brand the template. All future jam decks inherit the styling.

Usage:
    python3 .claude/skills/code-jam/workflows/style_template.py
    python3 .claude/skills/code-jam/workflows/style_template.py --template-id <id>
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / ".claude/skills/md-to-slides/libraries"))
from slides_auth import get_slides_services

# ── Brand palette (r, g, b as 0–1 floats) ────────────────────────────────────
BG           = (0.051, 0.051, 0.051)    # #0D0D0D  page background
BG_SECTION   = (0.063, 0.063, 0.071)    # #101012  section slide bg (subtle blue tint)
BG_CARD      = (0.094, 0.094, 0.094)    # #181818  card backgrounds
WHITE        = (1.000, 1.000, 1.000)    # #FFFFFF  headlines
GRAY_BODY    = (0.600, 0.600, 0.600)    # #999999  body text
GRAY_DIM     = (0.380, 0.380, 0.380)    # #616161  captions / dimmer text
AMBER        = (0.769, 0.533, 0.227)    # #C4883A  warm accent (section titles)
STEEL_BLUE   = (0.482, 0.675, 0.769)    # #7BACC4  cool accent
BORDER       = (0.165, 0.165, 0.165)    # #2A2A2A  card borders

FONT_SERIF   = "Cormorant Garamond"
FONT_SANS    = "DM Sans"

# ── Slide dimensions (Google Slides default: 9144000 x 5143500 EMU) ──────────
SLIDE_W = 9144000
SLIDE_H = 5143500
PT      = 12700   # 1 pt in EMU


def rgb(r, g, b):
    return {"rgbColor": {"red": r, "green": g, "blue": b}}


def solid_fill(r, g, b):
    return {"solidFill": {"color": rgb(r, g, b)}}


def no_fill():
    return {"propertyState": "NOT_RENDERED"}


def text_style(font=None, size=None, bold=False, italic=False, color=None, small_caps=False):
    style, fields = {}, []
    if font:        style["fontFamily"] = font;                          fields.append("fontFamily")
    if size:        style["fontSize"] = {"magnitude": size, "unit": "PT"}; fields.append("fontSize")
    if bold:        style["bold"] = True;                                fields.append("bold")
    if italic:      style["italic"] = True;                              fields.append("italic")
    if color:       style["foregroundColor"] = {"opaqueColor": rgb(*color)}; fields.append("foregroundColor")
    if small_caps:  style["smallCaps"] = True;                           fields.append("smallCaps")
    return style, ",".join(fields)


def has_text_runs(el: dict) -> bool:
    """Return True only if the element has real non-whitespace text content."""
    elements = el.get("shape", {}).get("text", {}).get("textElements", [])
    return any(
        "textRun" in te and te["textRun"].get("content", "").strip()
        for te in elements
    )


def para_style(align=None, space_above=None, space_below=None, line_spacing=None):
    style, fields = {}, []
    if align:        style["alignment"] = align;                          fields.append("alignment")
    if space_above:  style["spaceAbove"] = {"magnitude": space_above, "unit": "PT"}; fields.append("spaceAbove")
    if space_below:  style["spaceBelow"] = {"magnitude": space_below, "unit": "PT"}; fields.append("spaceBelow")
    if line_spacing: style["lineSpacing"] = line_spacing;                 fields.append("lineSpacing")
    return style, ",".join(fields)


def build_style_requests(pres: dict) -> list:
    reqs = []

    # ── Masters ───────────────────────────────────────────────────────────────
    for master in pres.get("masters", []):
        reqs.append({
            "updatePageProperties": {
                "objectId": master["objectId"],
                "pageProperties": {"pageBackgroundFill": solid_fill(*BG)},
                "fields": "pageBackgroundFill",
            }
        })
        for el in master.get("pageElements", []):
            ph_type = el.get("shape", {}).get("placeholder", {}).get("type", "")
            oid = el["objectId"]
            if not has_text_runs(el):
                continue
            if ph_type in ("TITLE", "CENTERED_TITLE"):
                s, f = text_style(font=FONT_SERIF, size=52, color=WHITE)
                reqs.append({"updateTextStyle": {"objectId": oid, "style": s, "fields": f}})
            elif ph_type in ("BODY", "SUBTITLE"):
                s, f = text_style(font=FONT_SANS, size=18, color=GRAY_BODY)
                reqs.append({"updateTextStyle": {"objectId": oid, "style": s, "fields": f}})

    # ── Layouts ───────────────────────────────────────────────────────────────
    for layout in pres.get("layouts", []):
        name = layout.get("layoutProperties", {}).get("displayName", "").lower()
        is_title    = "title slide" in name
        is_section  = "section" in name
        is_two_col  = "two column" in name or "two_column" in name

        bg = BG_SECTION if is_section else BG

        reqs.append({
            "updatePageProperties": {
                "objectId": layout["objectId"],
                "pageProperties": {"pageBackgroundFill": solid_fill(*bg)},
                "fields": "pageBackgroundFill",
            }
        })

        for el in layout.get("pageElements", []):
            ph_type = el.get("shape", {}).get("placeholder", {}).get("type", "")
            oid = el["objectId"]
            if not has_text_runs(el):
                continue

            if ph_type in ("TITLE", "CENTERED_TITLE"):
                if is_section:
                    # Section headers: large serif, amber accent
                    s, f = text_style(font=FONT_SERIF, size=60, color=AMBER)
                elif is_title:
                    # Title slide: extra large, white serif
                    s, f = text_style(font=FONT_SERIF, size=64, color=WHITE, bold=False)
                else:
                    s, f = text_style(font=FONT_SERIF, size=48, color=WHITE)
                reqs.append({"updateTextStyle": {"objectId": oid, "style": s, "fields": f}})

            elif ph_type in ("BODY", "SUBTITLE"):
                if is_title:
                    s, f = text_style(font=FONT_SANS, size=22, color=GRAY_BODY)
                else:
                    s, f = text_style(font=FONT_SANS, size=18, color=GRAY_BODY)
                reqs.append({"updateTextStyle": {"objectId": oid, "style": s, "fields": f}})

    return reqs


def add_decorative_elements(slides_svc, pres_id: str, pres: dict):
    """
    Add OpenAlly signature design elements to each layout:
      - Thin amber horizontal rule near top (content layouts)
      - Thin amber vertical bar on section layouts (like the quote accent)
    """
    reqs = []
    counter = 0

    for layout in pres.get("layouts", []):
        name = layout.get("layoutProperties", {}).get("displayName", "").lower()
        oid  = layout["objectId"]
        is_section = "section" in name
        is_blank   = "blank" in name

        if is_blank:
            continue

        counter += 1

        if is_section:
            # Vertical amber bar on left side (like openally quote accent)
            bar_id = f"accent_bar_{uuid.uuid4().hex[:8]}"
            reqs.append({
                "createShape": {
                    "objectId": bar_id,
                    "shapeType": "RECTANGLE",
                    "elementProperties": {
                        "pageObjectId": oid,
                        "size": {
                            "width":  {"magnitude": 3 * PT,           "unit": "EMU"},
                            "height": {"magnitude": 40 * PT,           "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": 76 * PT,
                            "translateY": (SLIDE_H // 2) - (20 * PT),
                            "unit": "EMU",
                        },
                    },
                }
            })
            reqs.append({
                "updateShapeProperties": {
                    "objectId": bar_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": solid_fill(*AMBER),
                        "outline": {"propertyState": "NOT_RENDERED"},
                    },
                    "fields": "shapeBackgroundFill,outline",
                }
            })

        else:
            # Thin full-width amber rule at very top of slide
            line_id = f"accent_line_{uuid.uuid4().hex[:8]}"
            reqs.append({
                "createShape": {
                    "objectId": line_id,
                    "shapeType": "RECTANGLE",
                    "elementProperties": {
                        "pageObjectId": oid,
                        "size": {
                            "width":  {"magnitude": SLIDE_W,  "unit": "EMU"},
                            "height": {"magnitude": 2 * PT,   "unit": "EMU"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": 0, "translateY": 0,
                            "unit": "EMU",
                        },
                    },
                }
            })
            reqs.append({
                "updateShapeProperties": {
                    "objectId": line_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": solid_fill(*AMBER),
                        "outline": {"propertyState": "NOT_RENDERED"},
                    },
                    "fields": "shapeBackgroundFill,outline",
                }
            })

    if reqs:
        slides_svc.presentations().batchUpdate(
            presentationId=pres_id, body={"requests": reqs}
        ).execute()
        print(f"  Added decorative elements to {counter} layout(s)")


def get_template_id() -> str:
    config_path = PROJECT_ROOT / ".claude/skills/md-to-slides/templates/slide-config.json"
    with open(config_path) as f:
        return json.load(f)["templates"]["dark"]


def main():
    parser = argparse.ArgumentParser(description="Apply Ally/OpenAlly brand styling to the Code Jam template")
    parser.add_argument("--template-id", default=None, help="Override template presentation ID")
    args = parser.parse_args()

    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", str(PROJECT_ROOT / "credentials.json"))
    os.environ["GOOGLE_CREDENTIALS_PATH"] = creds_path

    template_id = args.template_id or get_template_id()
    print(f"Styling template: {template_id}")
    print(f"  Brand: #0D0D0D bg · Instrument Serif · DM Sans · Amber #{int(AMBER[0]*255):02X}{int(AMBER[1]*255):02X}{int(AMBER[2]*255):02X} accent")

    slides_svc, _ = get_slides_services()
    pres = slides_svc.presentations().get(presentationId=template_id).execute()
    print(f"  Found {len(pres.get('masters', []))} master(s), {len(pres.get('layouts', []))} layout(s)")

    reqs = build_style_requests(pres)
    print(f"  Applying {len(reqs)} style requests...")
    if reqs:
        slides_svc.presentations().batchUpdate(
            presentationId=template_id, body={"requests": reqs}
        ).execute()

    print("  Adding decorative elements...")
    add_decorative_elements(slides_svc, template_id, pres)

    print(f"\n✅ Template styled to Ally/OpenAlly aesthetics!")
    print(f"   Preview: https://docs.google.com/presentation/d/{template_id}/edit")
    print(f"\nNow regenerate the jam deck:")
    print(f"   python3 .claude/skills/code-jam/workflows/run_code_jam.py --jam 1")


if __name__ == "__main__":
    main()
