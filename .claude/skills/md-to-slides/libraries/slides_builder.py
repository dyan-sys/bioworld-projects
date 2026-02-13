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

from .md_parser import SlideData, TextRun, parse_inline


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

    requests: list[dict] = [
        {
            "insertText": {
                "objectId": object_id,
                "text": text,
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

            if fields:
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
# Per-slide request builder
# ---------------------------------------------------------------------------

def _apply_body_style(
    object_id: str, body_style: dict
) -> list[dict]:
    """Apply base style, paragraph spacing, and bullets to a body placeholder."""
    requests: list[dict] = []
    requests.extend(_build_base_style_requests(object_id, body_style))
    requests.extend(_build_paragraph_style_requests(
        object_id,
        line_spacing=body_style.get("line_spacing"),
        space_above=body_style.get("space_above"),
    ))
    if body_style.get("bullet_preset"):
        requests.extend(
            _build_bullet_requests(object_id, body_style["bullet_preset"])
        )
    return requests


def _build_slide_requests(
    slide_data: SlideData,
    slide_obj: dict,
    slide_id: str,
    styles: dict | None = None,
) -> list[dict]:
    """Build all populate + style requests for a single slide."""
    requests: list[dict] = []
    s = styles or {}

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
        left_text = "\n".join(slide_data.left_body)
        right_text = "\n".join(slide_data.right_body)

        for i, text in enumerate([left_text, right_text]):
            if i < len(bodies) and text:
                runs = parse_inline(text)
                requests.extend(
                    build_insert_text_requests(bodies[i], text, runs)
                )
                requests.extend(_apply_body_style(bodies[i], body_style))

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
) -> str:
    """Generate a full Google Slides presentation.

    Orchestrator flow:
    1. Clone template via Drive API (into drive_folder if specified)
    2. Map layout display names to objectIds
    3. Delete existing placeholder slides
    4. Create new slides with correct layouts
    5. Read back created slides to get placeholder objectIds
    6. Populate text and apply styling
    7. Return presentation URL
    """
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
