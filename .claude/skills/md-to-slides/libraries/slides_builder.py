"""
Google Slides Builder

Core integration with the Google Slides API:
- Clone a template deck via Drive API
- Map layout display names to layout object IDs
- Delete placeholder slides from the cloned template
- Create new slides with the correct layout
- Populate placeholder text (title, body, speaker notes)
- Apply text styling (font, size, color, bold/italic)
- Apply paragraph styling (bullets, spacing)
- Handle two-column layouts and styled tables
"""

from __future__ import annotations

import uuid
from typing import Any

from .md_parser import SlideData, TextRun, parse_inline, strip_inline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> dict:
    """Convert '#rrggbb' to Slides API rgbColor dict."""
    h = hex_color.lstrip("#")
    return {
        "red": int(h[0:2], 16) / 255.0,
        "green": int(h[2:4], 16) / 255.0,
        "blue": int(h[4:6], 16) / 255.0,
    }


def _make_id() -> str:
    """Generate a unique object ID for a new slide."""
    return f"slide_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Template operations
# ---------------------------------------------------------------------------

def _resolve_folder(drive_service: Any, folder_name: str) -> str:
    """Find a Drive folder by name, or create it if it doesn't exist.

    Returns the folder ID.
    """
    query = (
        f"name='{folder_name}' and "
        "mimeType='application/vnd.google-apps.folder' and "
        "trashed=false"
    )
    resp = drive_service.files().list(
        q=query, fields="files(id, name)", pageSize=1
    ).execute()
    files = resp.get("files", [])
    if files:
        return files[0]["id"]

    # Create the folder
    folder = drive_service.files().create(
        body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    print(f"  Created Drive folder: {folder_name}")
    return folder["id"]


def clone_template(
    drive_service: Any, template_id: str, title: str,
    folder_name: str | None = None,
) -> str:
    """Clone the template presentation via Drive API.

    If folder_name is provided, places the clone in that folder
    (creating it if needed).

    Returns the new presentation ID.
    """
    body: dict[str, Any] = {"name": title}
    if folder_name:
        folder_id = _resolve_folder(drive_service, folder_name)
        body["parents"] = [folder_id]
    resp = drive_service.files().copy(fileId=template_id, body=body).execute()
    return resp["id"]


def get_layout_map(
    slides_service: Any, presentation_id: str, mapping: dict[str, str]
) -> dict[str, str]:
    """Build a map from logical layout names to layout objectIds."""
    pres = slides_service.presentations().get(
        presentationId=presentation_id
    ).execute()

    display_to_id = {}
    for layout in pres.get("layouts", []):
        name = layout.get("layoutProperties", {}).get("displayName", "")
        display_to_id[name] = layout["objectId"]

    result = {}
    for logical_name, display_name in mapping.items():
        if display_name in display_to_id:
            result[logical_name] = display_to_id[display_name]
        else:
            print(f"  Warning: layout '{display_name}' not found in template")

    return result


def get_existing_slide_ids(slides_service: Any, presentation_id: str) -> list[str]:
    """Get objectIds of all existing slides in the presentation."""
    pres = slides_service.presentations().get(
        presentationId=presentation_id
    ).execute()
    return [s["objectId"] for s in pres.get("slides", [])]


def build_delete_requests(slide_ids: list[str]) -> list[dict]:
    """Build deleteObject requests for existing placeholder slides."""
    return [{"deleteObject": {"objectId": sid}} for sid in slide_ids]


def build_create_slide_request(layout_id: str, slide_id: str) -> dict:
    """Build a createSlide request referencing a specific layout."""
    return {
        "createSlide": {
            "objectId": slide_id,
            "slideLayoutReference": {"layoutId": layout_id},
        }
    }


# ---------------------------------------------------------------------------
# Placeholder lookup
# ---------------------------------------------------------------------------

def _find_placeholder(slide: dict, ph_type: str) -> str | None:
    """Find a placeholder objectId by type on a slide."""
    for elem in slide.get("pageElements", []):
        shape = elem.get("shape", {})
        ph = shape.get("placeholder", {})
        if ph.get("type") == ph_type:
            return elem["objectId"]
    return None


def _find_body_placeholders(slide: dict) -> list[str]:
    """Find all BODY placeholder objectIds on a slide (for two-column)."""
    bodies = []
    for elem in slide.get("pageElements", []):
        shape = elem.get("shape", {})
        ph = shape.get("placeholder", {})
        if ph.get("type") == "BODY":
            bodies.append(elem["objectId"])
    return bodies


# ---------------------------------------------------------------------------
# Text insertion
# ---------------------------------------------------------------------------

def build_insert_text_requests(
    object_id: str, text: str, runs: list[TextRun] | None = None
) -> list[dict]:
    """Build insertText + inline bold/italic requests for a placeholder."""
    if not text:
        return []

    # Insert clean text (inline markers stripped); runs track bold/italic positions
    # within the stripped text — raw text would show ** literally in slides.
    insert_text = "".join(r.text for r in runs) if runs else text

    requests: list[dict] = [
        {
            "insertText": {
                "objectId": object_id,
                "text": insert_text,
                "insertionIndex": 0,
            }
        }
    ]

    if runs:
        offset = 0
        for run in runs:
            if not run.text:
                continue
            length = len(run.text)
            if run.bold or run.italic:
                style: dict[str, Any] = {}
                fields = []
                if run.bold:
                    style["bold"] = True
                    fields.append("bold")
                if run.italic:
                    style["italic"] = True
                    fields.append("italic")

                requests.append({
                    "updateTextStyle": {
                        "objectId": object_id,
                        "textRange": {
                            "type": "FIXED_RANGE",
                            "startIndex": offset,
                            "endIndex": offset + length,
                        },
                        "style": style,
                        "fields": ",".join(fields),
                    }
                })
            offset += length

    return requests


# ---------------------------------------------------------------------------
# Text styling (font, size, color)
# ---------------------------------------------------------------------------

def _build_base_style_requests(
    object_id: str, style_config: dict
) -> list[dict]:
    """Apply base text styling (font, size, color, bold) to all text in a placeholder."""
    if not style_config:
        return []

    style: dict[str, Any] = {}
    fields = []

    if "font_family" in style_config:
        style["fontFamily"] = style_config["font_family"]
        fields.append("fontFamily")
    if "font_size" in style_config:
        style["fontSize"] = {
            "magnitude": style_config["font_size"], "unit": "PT"
        }
        fields.append("fontSize")
    if "color" in style_config:
        style["foregroundColor"] = {
            "opaqueColor": {"rgbColor": _hex_to_rgb(style_config["color"])}
        }
        fields.append("foregroundColor")
    if style_config.get("bold"):
        style["bold"] = True
        fields.append("bold")

    if not fields:
        return []

    return [{
        "updateTextStyle": {
            "objectId": object_id,
            "textRange": {"type": "ALL"},
            "style": style,
            "fields": ",".join(fields),
        }
    }]


# ---------------------------------------------------------------------------
# Paragraph styling (spacing, bullets)
# ---------------------------------------------------------------------------

def _build_paragraph_style_requests(
    object_id: str,
    line_spacing: float | None = None,
    space_above: float | None = None,
    space_below: float | None = None,
) -> list[dict]:
    """Apply paragraph styling to all paragraphs in a placeholder."""
    style: dict[str, Any] = {}
    fields = []

    if line_spacing is not None:
        style["lineSpacing"] = line_spacing
        fields.append("lineSpacing")
    if space_above is not None:
        style["spaceAbove"] = {"magnitude": space_above, "unit": "PT"}
        fields.append("spaceAbove")
    if space_below is not None:
        style["spaceBelow"] = {"magnitude": space_below, "unit": "PT"}
        fields.append("spaceBelow")

    if not fields:
        return []

    return [{
        "updateParagraphStyle": {
            "objectId": object_id,
            "textRange": {"type": "ALL"},
            "style": style,
            "fields": ",".join(fields),
        }
    }]


def _build_bullet_requests(
    object_id: str,
    preset: str = "BULLET_DISC_CIRCLE_SQUARE",
) -> list[dict]:
    """Add bullet points to all paragraphs in a placeholder."""
    return [{
        "createParagraphBullets": {
            "objectId": object_id,
            "textRange": {"type": "ALL"},
            "bulletPreset": preset,
        }
    }]


# ---------------------------------------------------------------------------
# Speaker notes
# ---------------------------------------------------------------------------

def _build_notes_requests(slide_obj: dict, notes: str) -> list[dict]:
    """Build request to insert speaker notes."""
    if not notes:
        return []
    notes_page = slide_obj.get("slideProperties", {}).get("notesPage", {})
    for elem in notes_page.get("pageElements", []):
        shape = elem.get("shape", {})
        ph = shape.get("placeholder", {})
        if ph.get("type") == "BODY":
            return build_insert_text_requests(elem["objectId"], notes)
    return []


# ---------------------------------------------------------------------------
# Table (with header styling)
# ---------------------------------------------------------------------------

def _build_table_requests(
    slide_id: str, table: list[list[str]], styles: dict | None = None
) -> list[dict]:
    """Build requests to create a table, populate cells, and style header."""
    if not table or len(table) < 1:
        return []

    rows = len(table)
    cols = len(table[0]) if table[0] else 1
    table_id = f"{slide_id}_table"
    ts = styles or {}

    requests: list[dict] = [
        {
            "createTable": {
                "objectId": table_id,
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 600, "unit": "PT"},
                        "height": {"magnitude": 250, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1,
                        "scaleY": 1,
                        "translateX": 60,
                        "translateY": 120,
                        "unit": "PT",
                    },
                },
                "rows": rows,
                "columns": cols,
            }
        }
    ]

    # Insert text into each cell
    for r, row in enumerate(table):
        for c, cell in enumerate(row):
            if cell:
                requests.append({
                    "insertText": {
                        "objectId": table_id,
                        "cellLocation": {"rowIndex": r, "columnIndex": c},
                        "text": cell,
                        "insertionIndex": 0,
                    }
                })

    # Style all cells (font, size, color)
    for r, row in enumerate(table):
        for c, cell in enumerate(row):
            style: dict[str, Any] = {}
            fields = []

            if "font_family" in ts:
                style["fontFamily"] = ts["font_family"]
                fields.append("fontFamily")
            if "font_size" in ts:
                style["fontSize"] = {
                    "magnitude": ts["font_size"], "unit": "PT"
                }
                fields.append("fontSize")
            if "color" in ts:
                style["foregroundColor"] = {
                    "opaqueColor": {"rgbColor": _hex_to_rgb(ts["color"])}
                }
                fields.append("foregroundColor")
            # Header row: bold
            if r == 0 and ts.get("header_bold"):
                style["bold"] = True
                fields.append("bold")

            if fields and cell:
                requests.append({
                    "updateTextStyle": {
                        "objectId": table_id,
                        "cellLocation": {"rowIndex": r, "columnIndex": c},
                        "textRange": {"type": "ALL"},
                        "style": style,
                        "fields": ",".join(fields),
                    }
                })

    # Header row background
    if ts.get("header_background"):
        for c in range(cols):
            requests.append({
                "updateTableCellProperties": {
                    "objectId": table_id,
                    "tableRange": {
                        "location": {"rowIndex": 0, "columnIndex": c},
                        "rowSpan": 1,
                        "columnSpan": 1,
                    },
                    "tableCellProperties": {
                        "tableCellBackgroundFill": {
                            "solidFill": {
                                "color": {
                                    "rgbColor": _hex_to_rgb(
                                        ts["header_background"]
                                    )
                                }
                            }
                        }
                    },
                    "fields": "tableCellBackgroundFill",
                }
            })

    return requests


# ---------------------------------------------------------------------------
# Agenda layout (boxes with icons)
# ---------------------------------------------------------------------------

def _build_agenda_requests(
    slide_id: str,
    title: str,
    items: list[str],
    agenda_styles: dict | None = None,
) -> list[dict]:
    """Build requests for an agenda slide with icon boxes.

    Creates a title text box and a row of rounded rectangles,
    each containing an emoji icon and a short label.
    Uses theme colors so it adapts to any template.

    agenda_styles can include:
        title_font: font family for the slide title (default: template default)
        label_font: font family for box labels (default: template default)
    """
    ag = agenda_styles or {}
    requests: list[dict] = []

    # --- Title text box ---
    title_id = f"{slide_id}_agenda_title"
    requests.append({
        "createShape": {
            "objectId": title_id,
            "shapeType": "TEXT_BOX",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": 648, "unit": "PT"},
                    "height": {"magnitude": 50, "unit": "PT"},
                },
                "transform": {
                    "scaleX": 1, "scaleY": 1,
                    "translateX": 36, "translateY": 40,
                    "unit": "PT",
                },
            },
        }
    })
    if title:
        requests.append({
            "insertText": {
                "objectId": title_id, "text": title, "insertionIndex": 0,
            }
        })
        title_style: dict[str, Any] = {
            "fontSize": {"magnitude": 28, "unit": "PT"},
            "bold": True,
            "foregroundColor": {
                "opaqueColor": {"themeColor": "LIGHT1"}
            },
        }
        title_fields = ["fontSize", "bold", "foregroundColor"]
        if ag.get("title_font"):
            title_style["fontFamily"] = ag["title_font"]
            title_fields.append("fontFamily")

        requests.append({
            "updateTextStyle": {
                "objectId": title_id,
                "textRange": {"type": "ALL"},
                "style": title_style,
                "fields": ",".join(title_fields),
            }
        })
        requests.append({
            "updateParagraphStyle": {
                "objectId": title_id,
                "textRange": {"type": "ALL"},
                "style": {"alignment": "CENTER"},
                "fields": "alignment",
            }
        })

    # --- Agenda boxes ---
    n = len(items)
    if n == 0:
        return requests

    # Layout math (720 x 405pt page)
    gap = 12
    max_box_w = 130
    total_w = n * max_box_w + (n - 1) * gap
    # Scale down if too wide
    if total_w > 660:
        max_box_w = (660 - (n - 1) * gap) // n
        total_w = n * max_box_w + (n - 1) * gap

    box_h = 100
    left_offset = (720 - total_w) / 2
    top_offset = 170  # below title

    for i, item in enumerate(items):
        box_id = f"{slide_id}_agenda_{i}"
        x = left_offset + i * (max_box_w + gap)

        # Split item into emoji icon and label
        # Expect format like "👋 About You" or just "About You"
        parts = item.strip()
        icon = ""
        label = parts
        # Check if first character(s) are emoji (non-ASCII start)
        words = parts.split(" ", 1)
        if words and len(words) > 1 and not words[0][0].isascii():
            icon = words[0]
            label = words[1]

        # Create rounded rectangle
        requests.append({
            "createShape": {
                "objectId": box_id,
                "shapeType": "ROUND_RECTANGLE",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": max_box_w, "unit": "PT"},
                        "height": {"magnitude": box_h, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": x, "translateY": top_offset,
                        "unit": "PT",
                    },
                },
            }
        })

        # Style the box — theme-adaptive fill
        requests.append({
            "updateShapeProperties": {
                "objectId": box_id,
                "shapeProperties": {
                    "shapeBackgroundFill": {
                        "solidFill": {
                            "color": {"themeColor": "LIGHT1"},
                            "alpha": 0.1,
                        },
                    },
                    "outline": {
                        "weight": {"magnitude": 1, "unit": "PT"},
                        "outlineFill": {
                            "solidFill": {
                                "color": {"themeColor": "LIGHT1"},
                                "alpha": 0.25,
                            }
                        },
                    },
                },
                "fields": "shapeBackgroundFill,outline",
            }
        })

        # Insert text (icon + newline + label)
        text = f"{icon}\n{label}" if icon else label
        requests.append({
            "insertText": {
                "objectId": box_id, "text": text, "insertionIndex": 0,
            }
        })

        # Center text and set style
        requests.append({
            "updateParagraphStyle": {
                "objectId": box_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "alignment": "CENTER",
                    "lineSpacing": 115,
                    "spaceAbove": {"magnitude": 4, "unit": "PT"},
                },
                "fields": "alignment,lineSpacing,spaceAbove",
            }
        })

        # UTF-16 length (Slides API uses UTF-16 offsets, not Python len)
        def _utf16_len(s: str) -> int:
            return len(s.encode("utf-16-le")) // 2

        # Style: icon line larger, label smaller
        if icon:
            icon_u16 = _utf16_len(icon)
            label_start = icon_u16 + 1  # +1 for \n
            label_u16 = _utf16_len(label)

            # Icon style — use Noto Color Emoji font, large size
            requests.append({
                "updateTextStyle": {
                    "objectId": box_id,
                    "textRange": {
                        "type": "FIXED_RANGE",
                        "startIndex": 0,
                        "endIndex": icon_u16,
                    },
                    "style": {
                        "fontFamily": "Noto Color Emoji",
                        "fontSize": {"magnitude": 28, "unit": "PT"},
                    },
                    "fields": "fontFamily,fontSize",
                }
            })
            # Label style
            label_style: dict[str, Any] = {
                "fontSize": {"magnitude": 12, "unit": "PT"},
                "bold": True,
                "foregroundColor": {
                    "opaqueColor": {"themeColor": "LIGHT1"}
                },
            }
            label_fields = ["fontSize", "bold", "foregroundColor"]
            if ag.get("label_font"):
                label_style["fontFamily"] = ag["label_font"]
                label_fields.append("fontFamily")

            requests.append({
                "updateTextStyle": {
                    "objectId": box_id,
                    "textRange": {
                        "type": "FIXED_RANGE",
                        "startIndex": label_start,
                        "endIndex": label_start + label_u16,
                    },
                    "style": label_style,
                    "fields": ",".join(label_fields),
                }
            })
        else:
            no_icon_style: dict[str, Any] = {
                "fontSize": {"magnitude": 13, "unit": "PT"},
                "bold": True,
                "foregroundColor": {
                    "opaqueColor": {"themeColor": "LIGHT1"}
                },
            }
            no_icon_fields = ["fontSize", "bold", "foregroundColor"]
            if ag.get("label_font"):
                no_icon_style["fontFamily"] = ag["label_font"]
                no_icon_fields.append("fontFamily")

            requests.append({
                "updateTextStyle": {
                    "objectId": box_id,
                    "textRange": {"type": "ALL"},
                    "style": no_icon_style,
                    "fields": ",".join(no_icon_fields),
                }
            })

        # Vertically center text in the box
        requests.append({
            "updateShapeProperties": {
                "objectId": box_id,
                "shapeProperties": {
                    "contentAlignment": "MIDDLE",
                },
                "fields": "contentAlignment",
            }
        })

    return requests


# ---------------------------------------------------------------------------
# Quote layout (large italic quote + attribution)
# ---------------------------------------------------------------------------

def _build_quote_requests(
    slide_id: str,
    title: str,
    items: list[str],
    quote_styles: dict | None = None,
) -> list[dict]:
    """Build requests for a quote slide.

    Renders a large italic quote with a smaller attribution line below.
    Body items are joined as the quote text. Lines starting with '—' or '--'
    are treated as attribution.

    quote_styles can include:
        quote_font: font family for the quote (default: Instrument Serif)
        attribution_font: font family for attribution (default: DM Sans)
        quote_color: hex color for quote text
        attribution_color: hex color for attribution
    """
    qs = quote_styles or {}
    quote_font = qs.get("quote_font", "Instrument Serif")
    attr_font = qs.get("attribution_font", "DM Sans")
    quote_color = qs.get("quote_color", "#FFCAFF")  # pink from template
    attr_color = qs.get("attribution_color", "#BBBBBB")

    requests: list[dict] = []

    # Group items into quote blocks: each block = (quote_text, attribution)
    blocks: list[tuple[str, str]] = []
    current_quote = []
    for item in items:
        stripped = item.strip()
        if stripped.startswith(("—", "--", "- —")):
            # Attribution line — closes current quote block
            attr = stripped.lstrip("-—– ").strip()
            blocks.append(("\n".join(current_quote), attr))
            current_quote = []
        else:
            current_quote.append(stripped)
    # Any remaining quote lines without attribution
    if current_quote:
        blocks.append(("\n".join(current_quote), ""))

    # --- Optional title (small, above quotes) ---
    if title:
        title_id = f"{slide_id}_quote_title"
        requests.append({
            "createShape": {
                "objectId": title_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 600, "unit": "PT"},
                        "height": {"magnitude": 36, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": 60, "translateY": 24,
                        "unit": "PT",
                    },
                },
            }
        })
        requests.append({
            "insertText": {
                "objectId": title_id, "text": title, "insertionIndex": 0,
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": title_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "fontFamily": attr_font,
                    "fontSize": {"magnitude": 14, "unit": "PT"},
                    "foregroundColor": {
                        "opaqueColor": {"rgbColor": _hex_to_rgb(attr_color)}
                    },
                    "smallCaps": True,
                },
                "fields": "fontFamily,fontSize,foregroundColor,smallCaps",
            }
        })
        requests.append({
            "updateParagraphStyle": {
                "objectId": title_id,
                "textRange": {"type": "ALL"},
                "style": {"alignment": "CENTER"},
                "fields": "alignment",
            }
        })

    # --- Render each quote block ---
    n_blocks = len(blocks)
    if n_blocks == 1:
        # Single quote: centered vertically
        quote_top = 75 if title else 60
        quote_h = 200
        attr_top = 300
    else:
        # Multiple quotes: divide vertical space
        start_y = 65 if title else 45
        usable_h = 340 if title else 360
        block_h = usable_h // n_blocks

    # Alternate colors for multiple quotes
    quote_colors = [quote_color, "#FFFFFF"]

    for i, (q_text, a_text) in enumerate(blocks):
        if n_blocks == 1:
            y = quote_top
            h = quote_h
            ay = attr_top
        else:
            y = start_y + i * block_h
            h = int(block_h * 0.6)
            ay = y + h + 2

        # Adjust font size based on number of blocks
        q_font_size = 28 if n_blocks == 1 else 22

        # Quote text
        q_id = f"{slide_id}_quote_{i}"
        requests.append({
            "createShape": {
                "objectId": q_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 560, "unit": "PT"},
                        "height": {"magnitude": h, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": 80, "translateY": y,
                        "unit": "PT",
                    },
                },
            }
        })
        if q_text:
            color = quote_colors[i % len(quote_colors)]
            requests.append({
                "insertText": {
                    "objectId": q_id, "text": q_text, "insertionIndex": 0,
                }
            })
            requests.append({
                "updateTextStyle": {
                    "objectId": q_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "fontFamily": quote_font,
                        "fontSize": {"magnitude": q_font_size, "unit": "PT"},
                        "italic": True,
                        "foregroundColor": {
                            "opaqueColor": {"rgbColor": _hex_to_rgb(color)}
                        },
                    },
                    "fields": "fontFamily,fontSize,italic,foregroundColor",
                }
            })
            requests.append({
                "updateParagraphStyle": {
                    "objectId": q_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "alignment": "CENTER",
                        "lineSpacing": 135,
                        "spaceAbove": {"magnitude": 4, "unit": "PT"},
                    },
                    "fields": "alignment,lineSpacing,spaceAbove",
                }
            })

        # Attribution
        if a_text:
            a_id = f"{slide_id}_attr_{i}"
            requests.append({
                "createShape": {
                    "objectId": a_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "width": {"magnitude": 560, "unit": "PT"},
                            "height": {"magnitude": 30, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1, "scaleY": 1,
                            "translateX": 80, "translateY": ay,
                            "unit": "PT",
                        },
                    },
                }
            })
            requests.append({
                "insertText": {
                    "objectId": a_id, "text": f"— {a_text}", "insertionIndex": 0,
                }
            })
            requests.append({
                "updateTextStyle": {
                    "objectId": a_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "fontFamily": attr_font,
                        "fontSize": {"magnitude": 14, "unit": "PT"},
                        "foregroundColor": {
                            "opaqueColor": {"rgbColor": _hex_to_rgb(attr_color)}
                        },
                    },
                    "fields": "fontFamily,fontSize,foregroundColor",
                }
            })
            requests.append({
                "updateParagraphStyle": {
                    "objectId": a_id,
                    "textRange": {"type": "ALL"},
                    "style": {"alignment": "CENTER"},
                    "fields": "alignment",
                }
            })

    return requests


# ---------------------------------------------------------------------------
# Callout layout (single big centered statement)
# ---------------------------------------------------------------------------

def _build_callout_requests(
    slide_id: str,
    title: str,
    items: list[str],
    callout_styles: dict | None = None,
) -> list[dict]:
    """Build requests for a callout slide.

    Large centered text — for single impactful statements.
    Title becomes the main text. Body items become a smaller subtitle below.

    callout_styles can include:
        main_font: font family for main text (default: Instrument Serif)
        sub_font: font family for subtitle (default: DM Sans)
        main_color: hex color for main text
        sub_color: hex color for subtitle
    """
    cs = callout_styles or {}
    main_font = cs.get("main_font", "Instrument Serif")
    sub_font = cs.get("sub_font", "DM Sans")
    main_color = cs.get("main_color", "#FFFFFF")
    sub_color = cs.get("sub_color", "#BBBBBB")

    requests: list[dict] = []

    # --- Main text (title) ---
    if title:
        main_id = f"{slide_id}_callout_main"
        requests.append({
            "createShape": {
                "objectId": main_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 600, "unit": "PT"},
                        "height": {"magnitude": 160, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": 60, "translateY": 80,
                        "unit": "PT",
                    },
                },
            }
        })
        requests.append({
            "insertText": {
                "objectId": main_id, "text": title, "insertionIndex": 0,
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": main_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "fontFamily": main_font,
                    "fontSize": {"magnitude": 40, "unit": "PT"},
                    "foregroundColor": {
                        "opaqueColor": {"rgbColor": _hex_to_rgb(main_color)}
                    },
                },
                "fields": "fontFamily,fontSize,foregroundColor",
            }
        })
        requests.append({
            "updateParagraphStyle": {
                "objectId": main_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "alignment": "CENTER",
                    "lineSpacing": 130,
                },
                "fields": "alignment,lineSpacing",
            }
        })
        # Vertically center
        requests.append({
            "updateShapeProperties": {
                "objectId": main_id,
                "shapeProperties": {"contentAlignment": "MIDDLE"},
                "fields": "contentAlignment",
            }
        })

    # --- Subtitle (body items) ---
    if items:
        sub_id = f"{slide_id}_callout_sub"
        sub_text = "\n".join(items)

        requests.append({
            "createShape": {
                "objectId": sub_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {
                        "width": {"magnitude": 560, "unit": "PT"},
                        "height": {"magnitude": 80, "unit": "PT"},
                    },
                    "transform": {
                        "scaleX": 1, "scaleY": 1,
                        "translateX": 80, "translateY": 280,
                        "unit": "PT",
                    },
                },
            }
        })
        requests.append({
            "insertText": {
                "objectId": sub_id, "text": sub_text, "insertionIndex": 0,
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": sub_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "fontFamily": sub_font,
                    "fontSize": {"magnitude": 18, "unit": "PT"},
                    "foregroundColor": {
                        "opaqueColor": {"rgbColor": _hex_to_rgb(sub_color)}
                    },
                },
                "fields": "fontFamily,fontSize,foregroundColor",
            }
        })
        requests.append({
            "updateParagraphStyle": {
                "objectId": sub_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "alignment": "CENTER",
                    "lineSpacing": 130,
                },
                "fields": "alignment,lineSpacing",
            }
        })

    return requests


# ---------------------------------------------------------------------------
# Per-slide request builder
# ---------------------------------------------------------------------------

def _set_top_alignment(object_id: str) -> dict:
    """Pin text to top of placeholder (override Google Slides' default MIDDLE)."""
    return {
        "updateShapeProperties": {
            "objectId": object_id,
            "shapeProperties": {"contentAlignment": "TOP"},
            "fields": "contentAlignment",
        }
    }


def _apply_body_style(
    object_id: str, body_style: dict
) -> list[dict]:
    """Apply base style, paragraph spacing, and top alignment to a body placeholder."""
    requests: list[dict] = []
    requests.append(_set_top_alignment(object_id))
    requests.extend(_build_base_style_requests(object_id, body_style))
    requests.extend(_build_paragraph_style_requests(
        object_id,
        line_spacing=body_style.get("line_spacing"),
        space_above=body_style.get("space_above"),
        space_below=body_style.get("space_below"),
    ))
    return requests


def _build_selective_bullet_requests(
    object_id: str,
    items: list[str],
    types: list[str],
    preset: str,
) -> list[dict]:
    """Clear inherited template bullets, then re-apply only to bullet-type items.

    Always starts with deleteParagraphBullets: ALL so layout/template defaults
    (which bullet every paragraph by default) don't bleed through.
    """
    # Always clear first — layout placeholders inherit default bullets
    reqs: list[dict] = [{
        "deleteParagraphBullets": {
            "objectId": object_id,
            "textRange": {"type": "ALL"},
        }
    }]

    if not items or not preset:
        return reqs

    offset = 0
    for item, item_type in zip(items, types or []):
        clean_len = len(strip_inline(item))
        if item_type == "bullet" and clean_len > 0:
            reqs.append({
                "createParagraphBullets": {
                    "objectId": object_id,
                    "textRange": {
                        "type": "FIXED_RANGE",
                        "startIndex": offset,
                        "endIndex": offset + clean_len,
                    },
                    "bulletPreset": preset,
                }
            })
        offset += clean_len + 1  # +1 for the \n separator
    return reqs


def _build_slide_requests(
    slide_data: SlideData,
    slide_obj: dict,
    slide_id: str,
    styles: dict | None = None,
) -> list[dict]:
    """Build all populate + style requests for a single slide."""
    requests: list[dict] = []
    s = styles or {}

    # --- Agenda layout (custom shapes, not placeholders) ---
    if slide_data.layout == "agenda":
        requests.extend(
            _build_agenda_requests(
                slide_id, slide_data.title, slide_data.body_items,
                agenda_styles=s.get("agenda"),
            )
        )
        if slide_data.notes:
            requests.extend(_build_notes_requests(slide_obj, slide_data.notes))
        return requests

    # --- Quote layout (custom shapes) ---
    if slide_data.layout == "quote":
        requests.extend(
            _build_quote_requests(
                slide_id, slide_data.title, slide_data.body_items,
                quote_styles=s.get("quote"),
            )
        )
        if slide_data.notes:
            requests.extend(_build_notes_requests(slide_obj, slide_data.notes))
        return requests

    # --- Callout layout (custom shapes) ---
    if slide_data.layout == "callout":
        requests.extend(
            _build_callout_requests(
                slide_id, slide_data.title, slide_data.body_items,
                callout_styles=s.get("callout"),
            )
        )
        if slide_data.notes:
            requests.extend(_build_notes_requests(slide_obj, slide_data.notes))
        return requests

    # Pick style configs based on layout
    if slide_data.layout == "title":
        title_style = s.get("title", {})
    elif slide_data.layout == "section":
        title_style = s.get("section_title", {})
    else:
        title_style = s.get("content_title", {})

    subtitle_style = s.get("subtitle", {})
    body_style = s.get("body", {})
    table_style = s.get("table", {})

    # --- Title ---
    title_ph = _find_placeholder(slide_obj, "TITLE") or _find_placeholder(
        slide_obj, "CENTERED_TITLE"
    )
    if title_ph and slide_data.title:
        requests.extend(
            build_insert_text_requests(
                title_ph, slide_data.title, slide_data.title_runs
            )
        )
        requests.extend(_build_base_style_requests(title_ph, title_style))

    # --- Subtitle (title layout) ---
    if slide_data.layout == "title":
        subtitle_ph = _find_placeholder(slide_obj, "SUBTITLE")
        if subtitle_ph and slide_data.body:
            requests.extend(
                build_insert_text_requests(subtitle_ph, slide_data.body)
            )
            requests.extend(
                _build_base_style_requests(subtitle_ph, subtitle_style)
            )
            requests.extend(_build_paragraph_style_requests(
                subtitle_ph,
                line_spacing=subtitle_style.get("line_spacing"),
            ))

    # --- Two-column body ---
    elif slide_data.layout == "two_column":
        bodies = _find_body_placeholders(slide_obj)
        col_items = [slide_data.left_body, slide_data.right_body]
        col_types = [slide_data.left_body_types, slide_data.right_body_types]

        for i, (items, types) in enumerate(zip(col_items, col_types)):
            text = "\n".join(items)
            if i < len(bodies) and text:
                runs = parse_inline(text)
                requests.extend(build_insert_text_requests(bodies[i], text, runs))
                requests.extend(_apply_body_style(bodies[i], body_style))
                requests.extend(
                    _build_selective_bullet_requests(
                        bodies[i], items, types,
                        body_style.get("bullet_preset", "BULLET_DISC_CIRCLE_SQUARE"),
                    )
                )

    # --- Standard body ---
    else:
        body_ph = _find_placeholder(slide_obj, "BODY")
        if body_ph and slide_data.body:
            requests.extend(
                build_insert_text_requests(
                    body_ph, slide_data.body, slide_data.body_runs
                )
            )
            requests.extend(_apply_body_style(body_ph, body_style))
            requests.extend(
                _build_selective_bullet_requests(
                    body_ph, slide_data.body_items, slide_data.body_item_types,
                    body_style.get("bullet_preset", "BULLET_DISC_CIRCLE_SQUARE"),
                )
            )

    # --- Table ---
    if slide_data.table:
        requests.extend(
            _build_table_requests(slide_id, slide_data.table, table_style)
        )

    # --- Speaker notes ---
    if slide_data.notes:
        requests.extend(_build_notes_requests(slide_obj, slide_data.notes))

    return requests


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_presentation(
    slides_service: Any,
    drive_service: Any,
    template_id: str,
    layout_mapping: dict[str, str],
    default_layout: str,
    slides_data: list[SlideData],
    title: str,
    styles: dict | None = None,
    drive_folder: str | None = None,
    update_id: str | None = None,
) -> str:
    """Generate a full Google Slides presentation.

    If update_id is provided, updates the existing presentation in-place
    (deletes all slides and rebuilds). Otherwise clones from template.

    Returns the presentation URL.
    """
    if update_id:
        pres_id = update_id
        print(f"Updating existing presentation {pres_id}...")
        # Rename the presentation
        drive_service.files().update(
            fileId=pres_id, body={"name": title}
        ).execute()
    else:
        print(f"Cloning template {template_id}...")
        pres_id = clone_template(drive_service, template_id, title, drive_folder)
        print(f"  Created presentation: {pres_id}")

    # Map layouts
    layout_map = get_layout_map(slides_service, pres_id, layout_mapping)
    print(f"  Mapped {len(layout_map)} layouts: {list(layout_map.keys())}")

    # Delete existing placeholder slides
    existing_ids = get_existing_slide_ids(slides_service, pres_id)
    if existing_ids:
        print(f"  Deleting {len(existing_ids)} placeholder slides...")
        slides_service.presentations().batchUpdate(
            presentationId=pres_id,
            body={"requests": build_delete_requests(existing_ids)},
        ).execute()

    # Create all slides with correct layouts
    create_requests = []
    slide_ids = []
    for slide_data in slides_data:
        layout_key = slide_data.layout or default_layout
        layout_id = layout_map.get(layout_key, layout_map.get(default_layout))
        if not layout_id:
            print(f"  Warning: no layout for '{layout_key}', skipping slide")
            continue

        slide_id = _make_id()
        slide_ids.append(slide_id)
        create_requests.append(build_create_slide_request(layout_id, slide_id))

    if create_requests:
        print(f"  Creating {len(create_requests)} slides...")
        slides_service.presentations().batchUpdate(
            presentationId=pres_id,
            body={"requests": create_requests},
        ).execute()

    # Read back the full presentation to get placeholder objectIds
    pres = slides_service.presentations().get(
        presentationId=pres_id
    ).execute()

    slide_objects = {s["objectId"]: s for s in pres.get("slides", [])}

    # Populate and style each slide
    populate_requests: list[dict] = []
    for slide_id, slide_data in zip(slide_ids, slides_data):
        slide_obj = slide_objects.get(slide_id)
        if not slide_obj:
            print(f"  Warning: slide {slide_id} not found after creation")
            continue
        populate_requests.extend(
            _build_slide_requests(slide_data, slide_obj, slide_id, styles)
        )

    if populate_requests:
        print(f"  Populating and styling {len(populate_requests)} elements...")
        slides_service.presentations().batchUpdate(
            presentationId=pres_id,
            body={"requests": populate_requests},
        ).execute()

    url = f"https://docs.google.com/presentation/d/{pres_id}/edit"
    print(f"  Done! {url}")
    return url
