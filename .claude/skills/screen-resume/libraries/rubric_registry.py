"""
Rubric Registry - Centralized mapping of job openings to scoring rubrics.

This module manages the mapping between Opening IDs (e.g., "251003-EP")
and their corresponding resume scoring rubric files.
"""

from pathlib import Path
from typing import Optional, Tuple
import json
import warnings

# Get the skill root directory
SKILL_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = SKILL_ROOT / "templates"

# Load job type mapping
JOB_TYPE_MAPPING_PATH = TEMPLATES_DIR / "job-type-mapping.json"

def load_job_type_mapping() -> dict:
    """Load the job type mapping from JSON file."""
    with open(JOB_TYPE_MAPPING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# Load mappings at module level
_MAPPING_DATA = load_job_type_mapping()
JOB_TYPE_MAPPINGS = _MAPPING_DATA.get("mappings", {})
DEFAULT_MAPPING = _MAPPING_DATA.get("default", {
    "title": "Executive Partner (Default)",
    "rubric": "resume-scorer-v4.md"
})


def extract_job_type_from_opening_id(opening_id: Optional[str]) -> Optional[str]:
    """
    Extract job type code from Opening ID.

    Args:
        opening_id: Opening ID like "251003-EP" or "251003-EPP"

    Returns:
        Job type code (e.g., "EP", "EPP") or None if not extractable

    Examples:
        >>> extract_job_type_from_opening_id("251003-EP")
        'EP'
        >>> extract_job_type_from_opening_id("251003-EPP")
        'EPP'
        >>> extract_job_type_from_opening_id("EP")
        'EP'
    """
    if not opening_id:
        return None

    opening_id = opening_id.strip()
    if not opening_id:
        return None

    # If it contains a dash, extract everything after the last dash
    if "-" in opening_id:
        return opening_id.split("-")[-1].upper()

    # Otherwise, assume the whole string is the job type code
    return opening_id.upper()


def get_rubric_path(opening_id: Optional[str] = None) -> Tuple[Path, str]:
    """
    Resolve Opening ID to rubric file path.

    Args:
        opening_id: Opening ID from Notion Post (e.g., "251003-EP", "251003-EPP")

    Returns:
        Tuple of (rubric_file_path, job_title)

    Raises:
        FileNotFoundError: If the resolved rubric file doesn't exist

    Examples:
        >>> path, title = get_rubric_path("251003-EP")
        >>> path.name
        'resume-scorer-v4.md'
        >>> title
        'Executive Partner'
    """
    # Extract job type code from Opening ID
    job_type = extract_job_type_from_opening_id(opening_id)

    # Look up mapping
    if job_type and job_type in JOB_TYPE_MAPPINGS:
        mapping = JOB_TYPE_MAPPINGS[job_type]
        rubric_filename = mapping["rubric"]
        job_title = mapping["title"]
    else:
        # Fall back to default
        mapping = DEFAULT_MAPPING
        rubric_filename = mapping["rubric"]
        job_title = mapping["title"]

        # Warn if unknown job type was provided
        if job_type:
            warnings.warn(
                f"Unknown job type '{job_type}' (from Opening ID '{opening_id}') - "
                f"falling back to default rubric. Add '{job_type}' to job-type-mapping.json",
                UserWarning
            )

    # Build full path to rubric file
    rubric_path = TEMPLATES_DIR / rubric_filename

    # Verify file exists
    if not rubric_path.exists():
        raise FileNotFoundError(
            f"Rubric file not found: {rubric_path}\n"
            f"Opening ID: {opening_id or 'None (using default)'}\n"
            f"Job type: {job_type or 'None'}\n"
            f"Expected file: {rubric_filename}"
        )

    return rubric_path, job_title


def list_available_job_types() -> dict:
    """
    List all registered job types and their mappings.

    Returns:
        Dictionary mapping job type codes to their config
    """
    return JOB_TYPE_MAPPINGS.copy()


if __name__ == "__main__":
    # Self-test
    print("=== Rubric Registry Self-Test ===\n")

    print("Available job type mappings:")
    for job_type, mapping in list_available_job_types().items():
        print(f"  {job_type} → {mapping['title']} → {mapping['rubric']}")

    print(f"\nDefault mapping: {DEFAULT_MAPPING['title']} → {DEFAULT_MAPPING['rubric']}\n")

    # Test cases
    test_cases = [
        "251003-EP",
        "251003-EPP",
        "EP",
        "EPP",
        "epp",
        "251003-UNKNOWN",
        None,
        "",
        "  EP  ",
    ]

    print("Test cases:")
    for test_input in test_cases:
        try:
            path, job_title = get_rubric_path(test_input)
            job_type = extract_job_type_from_opening_id(test_input)
            print(f"  '{test_input}' → job_type={job_type} → {job_title} → {path.name}")
        except Exception as e:
            print(f"  '{test_input}' → ERROR: {e}")
