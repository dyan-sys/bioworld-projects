"""
Google Slides Builder

Core integration with the Google Slides API:
- Clone a template deck via Drive API
- Map layout display names to layout object IDs
- Delete placeholder slides from the cloned template
- Create new slides with the correct layout
- Populate placeholder text (title, body, speaker notes)
- Handle two-column layouts and tables
"""

from __future__ import annotations

import uuid
from typing import Any

from .md_parser import SlideData, TextRun, parse_inline


def clone_template(drive_service: Any, template_id: str, title: str) -> str:
    """Clone the template presentation via Drive API.

    Returns the new presentation ID.
    """
    body = {"name": title}
    resp = drive_service.files().copy(fileId=template_id, body=body).execute()
    return resp["id"]


def get_layout_map(
    slides_service: Any, presentation_id: str, mapping: dict[str, str]
) -> dict[str, str]:
    """Build a map from logical layout names to layout objectIds.

    Args:
        slides_service: Google Slides API service.
        presentation_id: ID of the cloned presentation.
        mapping: Config mapping (e.g. {"title": "Title Slide", ...}).

    Returns:
        Dict mapping logical name → layout objectId.
    """
    pres = slides_service.presentations().get(
        presentationId=presentation_id
    ).execute()

    # Build reverse map: displayName → objectId
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


def _make_id() -> str:
    """Generate a unique object ID for a new slide."""
    return f"slide_{uuid.uuid4().hex[:12]}"


def build_create_slide_request(layout_id: str, slide_id: str) -> dict:
    """Build a createSlide request referencing a specific layout."""
    return {
        "createSlide": {
            "objectId": slide_id,
            "slideLayoutReference": {"layoutId": layout_id},
        }
    }


def _find_placeholder(slide: dict, ph_type: str) -> str | None:
    """Find a placeholder objectId by type on a slide.

    ph_type: "TITLE", "CENTERED_TITLE", "SUBTITLE", "BODY"
    """
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


def build_insert_text_requests(
    object_id: str, text: str, runs: list[TextRun] | None = None
) -> list[dict]:
    """Build insertText + updateTextStyle requests for a placeholder.

    Inserts text and applies bold/italic formatting based on TextRuns.
    """
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

    # Apply formatting from text runs
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


def build_speaker_notes_request(slide_id: str, notes: str) -> list[dict]:
    """Build request to insert speaker notes into a slide's notes page."""
    if not notes:
        return []
    return [
        {
            "insertText": {
                "objectId": f"{slide_id}_notes",
                "text": notes,
                "insertionIndex": 0,
            }
        }
    ]


def build_table_requests(
    slide_id: str, table: list[list[str]]
) -> list[dict]:
    """Build requests to create a table and populate cells."""
    if not table or len(table) < 1:
        return []

    rows = len(table)
    cols = len(table[0]) if table[0] else 1
    table_id = f"{slide_id}_table"

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
                        "cellLocation": {
                            "rowIndex": r,
                            "columnIndex": c,
                        },
                        "text": cell,
                        "insertionIndex": 0,
                    }
                })

    return requests


def _build_slide_requests(
    slide_data: SlideData,
    slide_obj: dict,
    slide_id: str,
) -> list[dict]:
    """Build all populate requests for a single slide."""
    requests: list[dict] = []

    # Title
    title_ph = _find_placeholder(slide_obj, "TITLE") or _find_placeholder(
        slide_obj, "CENTERED_TITLE"
    )
    if title_ph and slide_data.title:
        requests.extend(
            build_insert_text_requests(
                title_ph, slide_data.title, slide_data.title_runs
            )
        )

    # Subtitle (title layout only)
    if slide_data.layout == "title":
        subtitle_ph = _find_placeholder(slide_obj, "SUBTITLE")
        if subtitle_ph and slide_data.body:
            requests.extend(
                build_insert_text_requests(subtitle_ph, slide_data.body)
            )
    elif slide_data.layout == "two_column":
        # Two-column: find both BODY placeholders
        bodies = _find_body_placeholders(slide_obj)
        left_text = "\n".join(slide_data.left_body)
        right_text = "\n".join(slide_data.right_body)

        if len(bodies) >= 1 and left_text:
            left_runs = parse_inline(left_text)
            requests.extend(
                build_insert_text_requests(bodies[0], left_text, left_runs)
            )
        if len(bodies) >= 2 and right_text:
            right_runs = parse_inline(right_text)
            requests.extend(
                build_insert_text_requests(bodies[1], right_text, right_runs)
            )
    else:
        # Standard body
        body_ph = _find_placeholder(slide_obj, "BODY")
        if body_ph and slide_data.body:
            requests.extend(
                build_insert_text_requests(
                    body_ph, slide_data.body, slide_data.body_runs
                )
            )

    # Table (placed directly on slide, not in placeholder)
    if slide_data.table:
        requests.extend(build_table_requests(slide_id, slide_data.table))

    # Speaker notes — use the notes page's speaker notes shape
    if slide_data.notes:
        notes_page = slide_obj.get("slideProperties", {}).get("notesPage", {})
        notes_shape_id = None
        for elem in notes_page.get("pageElements", []):
            shape = elem.get("shape", {})
            ph = shape.get("placeholder", {})
            if ph.get("type") == "BODY":
                notes_shape_id = elem["objectId"]
                break
        if notes_shape_id:
            requests.extend(
                build_insert_text_requests(notes_shape_id, slide_data.notes)
            )

    return requests


def generate_presentation(
    slides_service: Any,
    drive_service: Any,
    template_id: str,
    layout_mapping: dict[str, str],
    default_layout: str,
    slides_data: list[SlideData],
    title: str,
) -> str:
    """Generate a full Google Slides presentation.

    Orchestrator flow:
    1. Clone template via Drive API
    2. Map layout display names to objectIds
    3. Delete existing placeholder slides
    4. Create new slides with correct layouts
    5. Read back created slides to get placeholder objectIds
    6. Populate text into placeholders
    7. Return presentation URL

    Returns:
        URL of the created presentation.
    """
    print(f"Cloning template {template_id}...")
    pres_id = clone_template(drive_service, template_id, title)
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

    # Populate each slide
    populate_requests: list[dict] = []
    for slide_id, slide_data in zip(slide_ids, slides_data):
        slide_obj = slide_objects.get(slide_id)
        if not slide_obj:
            print(f"  Warning: slide {slide_id} not found after creation")
            continue
        populate_requests.extend(
            _build_slide_requests(slide_data, slide_obj, slide_id)
        )

    if populate_requests:
        print(f"  Populating {len(populate_requests)} text elements...")
        slides_service.presentations().batchUpdate(
            presentationId=pres_id,
            body={"requests": populate_requests},
        ).execute()

    url = f"https://docs.google.com/presentation/d/{pres_id}/edit"
    print(f"  Done! {url}")
    return url
