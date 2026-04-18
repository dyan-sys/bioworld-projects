"""
Notion Dashboard Library for Bioworld LinkedIn Automation.

Handles CRUD operations for two databases:
  1. Content Pipeline — articles progressing through discovery → publish
  2. Portfolio Brands — tracked companies with LinkedIn URLs and search config

Reuses retry/header patterns from update-job-posts/libraries/notion_helpers.py.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15]

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectionError,
)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request_with_retry(method: str, url: str, headers: dict,
                        timeout: int = REQUEST_TIMEOUT, **kwargs) -> requests.Response:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.request(method, url, headers=headers,
                                        timeout=timeout, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt - 1]
                    print(f"    [RETRY] HTTP {response.status_code}, waiting {wait}s "
                          f"(attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                    continue
            response.raise_for_status()
            return response
        except RETRYABLE_EXCEPTIONS as exc:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt - 1]
                print(f"    [RETRY] {type(exc).__name__}, waiting {wait}s "
                      f"(attempt {attempt}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exhausted retries")


def notion_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Page creation
# ---------------------------------------------------------------------------

def create_parent_page(api_key: str, parent_page_id: str) -> dict:
    """Create the 'Bioworld LinkedIn — Content Hub' parent page."""
    url = f"{NOTION_API_BASE}/pages"
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "\U0001f4e1"},
        "properties": {
            "title": {
                "title": [
                    {"type": "text", "text": {"content": "Bioworld LinkedIn \u2014 Content Hub"}}
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "icon": {"type": "emoji", "emoji": "\u2139\ufe0f"},
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": (
                                    "This dashboard is managed by the Bioworld LinkedIn automation. "
                                    "Create filtered views (tabs) for: This Week, Pending Approval, "
                                    "Published, All Articles."
                                )
                            },
                        }
                    ],
                },
            }
        ],
    }
    hdrs = notion_headers(api_key)
    resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
    return resp.json()


# ---------------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------------

def create_content_db(api_key: str, parent_page_id: str) -> dict:
    """Create the Content Pipeline database."""
    url = f"{NOTION_API_BASE}/databases"
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "\U0001f4f0"},
        "title": [
            {"type": "text", "text": {"content": "Content Pipeline"}}
        ],
        "properties": {
            "Title": {"title": {}},
            "Status": {
                "status": {
                    "options": [
                        {"name": "Discovered", "color": "default"},
                        {"name": "Shortlisted", "color": "blue"},
                        {"name": "Draft Ready", "color": "purple"},
                        {"name": "Pending Approval", "color": "yellow"},
                        {"name": "Approved", "color": "green"},
                        {"name": "Published", "color": "green"},
                        {"name": "Rejected", "color": "red"},
                    ],
                    "groups": [
                        {
                            "name": "Pipeline",
                            "color": "blue",
                            "option_ids": [],
                        },
                        {
                            "name": "Done",
                            "color": "green",
                            "option_ids": [],
                        },
                    ],
                }
            },
            "Portfolio Company": {
                "select": {
                    "options": [
                        {"name": "CorVista Health", "color": "blue"},
                        {"name": "Senti Biosciences", "color": "purple"},
                        {"name": "Cardea Bio", "color": "pink"},
                        {"name": "Foundation Medicine", "color": "red"},
                        {"name": "Arima Genomics", "color": "orange"},
                        {"name": "Vena Vitals", "color": "yellow"},
                        {"name": "Hello Vigor", "color": "green"},
                        {"name": "YOR Labs", "color": "blue"},
                        {"name": "Mii Care", "color": "purple"},
                        {"name": "Great Bay Bio", "color": "pink"},
                        {"name": "Endia Therapeutics", "color": "red"},
                        {"name": "Rare Air Health", "color": "orange"},
                        {"name": "Industry News", "color": "default"},
                    ]
                }
            },
            "Source URL": {"url": {}},
            "Source Type": {
                "select": {
                    "options": [
                        {"name": "News", "color": "default"},
                        {"name": "LinkedIn Repost", "color": "blue"},
                        {"name": "Press Release", "color": "purple"},
                        {"name": "Funding", "color": "green"},
                        {"name": "Regulatory", "color": "yellow"},
                        {"name": "Partnership", "color": "orange"},
                    ]
                }
            },
            "Relevance Score": {"number": {"format": "number"}},
            "AI Summary": {"rich_text": {}},
            "Draft Post": {"rich_text": {}},
            "Week": {"rich_text": {}},
            "Discovered Date": {"date": {}},
            "Approved By": {"rich_text": {}},
            "Notes": {"rich_text": {}},
        },
    }
    hdrs = notion_headers(api_key)
    resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
    return resp.json()


def create_brands_db(api_key: str, parent_page_id: str) -> dict:
    """Create the Portfolio Brands database."""
    url = f"{NOTION_API_BASE}/databases"
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "icon": {"type": "emoji", "emoji": "\U0001f3e2"},
        "title": [
            {"type": "text", "text": {"content": "Portfolio Brands"}}
        ],
        "properties": {
            "Company Name": {"title": {}},
            "LinkedIn URL": {"url": {}},
            "Website": {"url": {}},
            "Focus Area": {
                "select": {
                    "options": [
                        {"name": "Biopharma", "color": "purple"},
                        {"name": "MedTech", "color": "blue"},
                        {"name": "Digital Health", "color": "green"},
                        {"name": "Life Science Tools", "color": "orange"},
                        {"name": "Diagnostics", "color": "yellow"},
                    ]
                }
            },
            "Search Keywords": {"rich_text": {}},
            "Active": {"checkbox": {}},
            "Last Scanned": {"date": {}},
        },
    }
    hdrs = notion_headers(api_key)
    resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
    return resp.json()


# ---------------------------------------------------------------------------
# Seed brands
# ---------------------------------------------------------------------------

def seed_brands(api_key: str, brands_db_id: str) -> list[dict]:
    """Populate Portfolio Brands DB from brand-config.json."""
    config_path = TEMPLATE_DIR / "brand-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    hdrs = notion_headers(api_key)
    results = []

    for company in config["companies"]:
        payload = {
            "parent": {"database_id": brands_db_id},
            "properties": {
                "Company Name": {
                    "title": [
                        {"type": "text", "text": {"content": company["name"]}}
                    ]
                },
                "Website": {"url": company["website"]},
                "Focus Area": {"select": {"name": company["focus_area"]}},
                "Search Keywords": {
                    "rich_text": [
                        {"type": "text", "text": {"content": company["search_keywords"]}}
                    ]
                },
                "Active": {"checkbox": True},
            },
        }
        if company.get("linkedin_url"):
            payload["properties"]["LinkedIn URL"] = {"url": company["linkedin_url"]}

        url = f"{NOTION_API_BASE}/pages"
        resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
        results.append(resp.json())
        print(f"  + {company['name']}")

    return results


# ---------------------------------------------------------------------------
# Content Pipeline CRUD
# ---------------------------------------------------------------------------

def add_article(api_key: str, db_id: str, article: dict) -> dict:
    """
    Insert a new article into the Content Pipeline.

    article dict keys:
        title, source_url, portfolio_company, source_type,
        relevance_score, ai_summary, week, discovered_date
    """
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/pages"

    properties = {
        "Title": {
            "title": [
                {"type": "text", "text": {"content": article["title"][:2000]}}
            ]
        },
        "Status": {"status": {"name": "Discovered"}},
        "Source URL": {"url": article.get("source_url", "")},
        "Portfolio Company": {"select": {"name": article.get("portfolio_company", "Industry News")}},
        "Source Type": {"select": {"name": article.get("source_type", "News")}},
        "Relevance Score": {"number": article.get("relevance_score", 5)},
        "AI Summary": {
            "rich_text": [
                {"type": "text", "text": {"content": article.get("ai_summary", "")[:2000]}}
            ]
        },
        "Week": {
            "rich_text": [
                {"type": "text", "text": {"content": article.get("week", "")}}
            ]
        },
        "Discovered Date": {"date": {"start": article.get("discovered_date", datetime.now().isoformat()[:10])}},
    }

    payload = {"parent": {"database_id": db_id}, "properties": properties}
    resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
    return resp.json()


def get_articles_by_status(api_key: str, db_id: str, status: str,
                           week: str | None = None) -> list[dict]:
    """Query Content Pipeline for articles with a given status."""
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"

    filters = [{"property": "Status", "status": {"equals": status}}]
    if week:
        filters.append({
            "property": "Week",
            "rich_text": {"equals": week},
        })

    payload = {
        "filter": {"and": filters} if len(filters) > 1 else filters[0],
        "sorts": [{"property": "Relevance Score", "direction": "descending"}],
        "page_size": 100,
    }

    results = []
    has_more = True
    start_cursor = None

    while has_more:
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
        data = resp.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return results


def update_article_status(api_key: str, page_id: str, status: str,
                          extra_props: dict | None = None) -> dict:
    """Update an article's status and optionally other properties."""
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/pages/{page_id}"

    properties = {"Status": {"status": {"name": status}}}
    if extra_props:
        properties.update(extra_props)

    payload = {"properties": properties}
    resp = _request_with_retry("PATCH", url, headers=hdrs, json=payload)
    return resp.json()


def update_article_draft(api_key: str, page_id: str, draft_text: str) -> dict:
    """Set the Draft Post text on an article."""
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/pages/{page_id}"

    payload = {
        "properties": {
            "Draft Post": {
                "rich_text": [
                    {"type": "text", "text": {"content": draft_text[:2000]}}
                ]
            },
            "Status": {"status": {"name": "Draft Ready"}},
        }
    }
    resp = _request_with_retry("PATCH", url, headers=hdrs, json=payload)
    return resp.json()


def check_duplicate(api_key: str, db_id: str, source_url: str) -> bool:
    """Check if an article with this URL already exists in the pipeline."""
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"

    payload = {
        "filter": {
            "property": "Source URL",
            "url": {"equals": source_url},
        },
        "page_size": 1,
    }
    resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
    data = resp.json()
    return len(data.get("results", [])) > 0


# ---------------------------------------------------------------------------
# Portfolio Brands read
# ---------------------------------------------------------------------------

def get_active_brands(api_key: str, brands_db_id: str) -> list[dict]:
    """Get all active brands from the Portfolio Brands DB."""
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/databases/{brands_db_id}/query"

    payload = {
        "filter": {
            "property": "Active",
            "checkbox": {"equals": True},
        },
        "page_size": 100,
    }
    resp = _request_with_retry("POST", url, headers=hdrs, json=payload)
    data = resp.json()

    brands = []
    for page in data.get("results", []):
        props = page["properties"]
        name_parts = props.get("Company Name", {}).get("title", [])
        name = name_parts[0]["plain_text"] if name_parts else "Unknown"

        keywords_parts = props.get("Search Keywords", {}).get("rich_text", [])
        keywords = keywords_parts[0]["plain_text"] if keywords_parts else ""

        website = props.get("Website", {}).get("url", "")
        linkedin = props.get("LinkedIn URL", {}).get("url", "")

        focus_area_prop = props.get("Focus Area", {}).get("select")
        focus_area = focus_area_prop["name"] if focus_area_prop else ""

        brands.append({
            "page_id": page["id"],
            "name": name,
            "keywords": keywords,
            "website": website,
            "linkedin_url": linkedin,
            "focus_area": focus_area,
        })

    return brands


def update_brand_last_scanned(api_key: str, page_id: str, date_str: str) -> dict:
    """Update the Last Scanned date on a brand."""
    hdrs = notion_headers(api_key)
    url = f"{NOTION_API_BASE}/pages/{page_id}"

    payload = {
        "properties": {
            "Last Scanned": {"date": {"start": date_str}},
        }
    }
    resp = _request_with_retry("PATCH", url, headers=hdrs, json=payload)
    return resp.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_article_data(page: dict) -> dict:
    """Extract article fields from a Notion page object."""
    props = page["properties"]

    title_parts = props.get("Title", {}).get("title", [])
    title = title_parts[0]["plain_text"] if title_parts else ""

    summary_parts = props.get("AI Summary", {}).get("rich_text", [])
    summary = summary_parts[0]["plain_text"] if summary_parts else ""

    draft_parts = props.get("Draft Post", {}).get("rich_text", [])
    draft = draft_parts[0]["plain_text"] if draft_parts else ""

    source_url = props.get("Source URL", {}).get("url", "")

    company_prop = props.get("Portfolio Company", {}).get("select")
    company = company_prop["name"] if company_prop else ""

    source_type_prop = props.get("Source Type", {}).get("select")
    source_type = source_type_prop["name"] if source_type_prop else ""

    score = props.get("Relevance Score", {}).get("number", 0)

    status_prop = props.get("Status", {}).get("status")
    status = status_prop["name"] if status_prop else ""

    return {
        "page_id": page["id"],
        "title": title,
        "summary": summary,
        "draft": draft,
        "source_url": source_url,
        "company": company,
        "source_type": source_type,
        "score": score,
        "status": status,
        "notion_url": page.get("url", ""),
    }
