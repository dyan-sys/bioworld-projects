"""
Bioworld LinkedIn — Content Hub Dashboard
------------------------------------------
Flask web app for managing the Bioworld LinkedIn content pipeline.

Workflow:
  Dashboard (local workspace) → scan, preview, generate drafts, select
  Notion (clean DB) → only selected/approved/published posts
  Slack → Ivan reviews with interactive approve/revise/reject buttons

Search engines: Kimi (Moonshot), Serper (Google+Claude), Tavily
"""

import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for,
)

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

INACTIVITY_TIMEOUT = 30 * 60
HKT = timezone(timedelta(hours=8))

# ── Config ────────────────────────────────────────────────────────────────────
NOTION_KEY = os.getenv("NOTION_KEY", "")
CONTENT_DB_ID = os.getenv("BIOWORLD_CONTENT_DB_ID", "")
BRANDS_DB_ID = os.getenv("BIOWORLD_BRANDS_DB_ID", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN") or os.getenv("ALLY_BOT_TOKEN", "")
SLACK_CHANNEL = os.getenv("BIOWORLD_SLACK_CHANNEL", "")

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
REQUEST_TIMEOUT = 30

SKILL_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(__file__).resolve().parents[4] / "local-data" / "bioworld-linkedin"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Google OAuth
GOOGLE_CLIENT_ID = ""
_creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
if _creds_json:
    try:
        GOOGLE_CLIENT_ID = json.loads(_creds_json).get("web", {}).get("client_id", "")
    except (json.JSONDecodeError, KeyError):
        pass

STATUS_COLORS = {
    "Discovered": "gray", "Shortlisted": "blue", "Draft Ready": "purple",
    "Pending Approval": "yellow", "Approved": "green",
    "Published": "emerald", "Rejected": "red",
}

# ── Team / Partners (sourced from bioworld-ventures website) ─────────────────
TEAM = [
    {"name": "Aaron Berez, MD", "title": "Chair — Tech & Business Council", "linkedin": "#", "expertise": ["Physician-Entrepreneur", "Stanford Faculty"]},
    {"name": "Adrian Cheong, MD", "title": "Chair — Medical Council", "linkedin": "#", "expertise": ["Interventional Cardiologist", "KOL"]},
    {"name": "Adrian Lam, CFA", "title": "Managing Partner", "linkedin": "#", "expertise": ["R&D", "Business Development", "Capital Markets"]},
    {"name": "Raymond Law, MBA", "title": "Partner", "linkedin": "#", "expertise": ["Strategy", "Business Development", "Commercialisation"]},
    {"name": "Jihong Qu, PhD MBA", "title": "Partner", "linkedin": "#", "expertise": ["Medical Affairs", "Regulatory Affairs", "Clinical Affairs"]},
    {"name": "Irwan Moideen, PhD", "title": "Partner", "linkedin": "#", "expertise": ["R&D", "Quality Management", "Medical Affairs"]},
    {"name": "Ivan Li", "title": "Partner", "linkedin": "#", "expertise": ["Strategy", "Start-ups 0-to-1", "COO function", "Diagnostics"]},
    {"name": "Kelvin Lam", "title": "Executive-in-Residence", "linkedin": "#", "expertise": ["Commercialization", "Pharma", "Marketing"]},
    {"name": "Gary Wong", "title": "Executive-in-Residence", "linkedin": "#", "expertise": ["Public & Private Equity Investing", "Investor Relations"]},
    {"name": "Evan Zhang, MD MBA EMBA", "title": "Executive-in-Residence", "linkedin": "#", "expertise": ["CEO Function", "Commercialization", "Neurovascular"]},
    {"name": "Jennifer Xu", "title": "Executive-in-Residence", "linkedin": "#", "expertise": ["Digital Health", "Strategy"]},
    {"name": "Frank Zhen", "title": "Executive-in-Residence", "linkedin": "#", "expertise": ["Commercialization", "Medical Aesthetics", "Business Development"]},
]

# In-memory workspace (scan results + drafts before pushing to Notion)
workspace = {
    "articles": [],       # list of article dicts from latest scan
    "drafts": {},         # article_id -> draft_text
    "scan_engine": "",    # which engine was used
    "scan_time": "",      # when last scanned
}

workflow_status = {}


# ── Local workspace persistence ──────────────────────────────────────────────

WORKSPACE_FILE = DATA_DIR / "workspace.json"


def save_workspace():
    WORKSPACE_FILE.write_text(json.dumps(workspace, indent=2, default=str), encoding="utf-8")


def load_workspace():
    global workspace
    if WORKSPACE_FILE.exists():
        try:
            workspace = json.loads(WORKSPACE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass


load_workspace()


# ── Notion helpers ────────────────────────────────────────────────────────────

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_query(db_id, payload=None):
    url = f"{NOTION_API_BASE}/databases/{db_id}/query"
    results = []
    has_more = True
    start_cursor = None
    while has_more:
        body = payload.copy() if payload else {}
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = requests.post(url, headers=notion_headers(), json=body, timeout=REQUEST_TIMEOUT)
        if not resp.ok:
            return []
        data = resp.json()
        results.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")
    return results


def notion_update_page(page_id, properties):
    url = f"{NOTION_API_BASE}/pages/{page_id}"
    resp = requests.patch(url, headers=notion_headers(), json={"properties": properties}, timeout=REQUEST_TIMEOUT)
    return resp.ok


def notion_create_page(db_id, properties):
    url = f"{NOTION_API_BASE}/pages"
    payload = {"parent": {"database_id": db_id}, "properties": properties}
    resp = requests.post(url, headers=notion_headers(), json=payload, timeout=REQUEST_TIMEOUT)
    return resp.json() if resp.ok else None


def extract_article(page):
    props = page.get("properties", {})

    def get_title(p): parts = p.get("title", []); return parts[0]["plain_text"] if parts else ""
    def get_rt(p): parts = p.get("rich_text", []); return parts[0]["plain_text"] if parts else ""
    def get_sel(p): s = p.get("select"); return s["name"] if s else ""
    def get_st(p): s = p.get("status"); return s["name"] if s else ""
    def get_num(p): return p.get("number") or 0
    def get_url(p): return p.get("url") or ""
    def get_date(p): d = p.get("date"); return d["start"] if d else ""

    return {
        "id": page["id"], "title": get_title(props.get("Title", {})),
        "status": get_st(props.get("Status", {})),
        "company": get_sel(props.get("Portfolio Company", {})),
        "source_url": get_url(props.get("Source URL", {})),
        "source_type": get_sel(props.get("Source Type", {})),
        "score": get_num(props.get("Relevance Score", {})),
        "summary": get_rt(props.get("AI Summary", {})),
        "draft": get_rt(props.get("Draft Post", {})),
        "week": get_rt(props.get("Week", {})),
        "date": get_date(props.get("Discovered Date", {})),
        "approved_by": get_rt(props.get("Approved By", {})),
        "notes": get_rt(props.get("Notes", {})),
        "notion_url": page.get("url", ""),
    }


def extract_brand(page):
    props = page.get("properties", {})

    def get_title(p): parts = p.get("title", []); return parts[0]["plain_text"] if parts else ""
    def get_rt(p): parts = p.get("rich_text", []); return parts[0]["plain_text"] if parts else ""
    def get_sel(p): s = p.get("select"); return s["name"] if s else ""
    def get_url(p): return p.get("url") or ""
    def get_cb(p): return p.get("checkbox", False)
    def get_date(p): d = p.get("date"); return d["start"] if d else ""

    return {
        "id": page["id"], "name": get_title(props.get("Company Name", {})),
        "linkedin_url": get_url(props.get("LinkedIn URL", {})),
        "website": get_url(props.get("Website", {})),
        "focus_area": get_sel(props.get("Focus Area", {})),
        "keywords": get_rt(props.get("Search Keywords", {})),
        "active": get_cb(props.get("Active", {})),
        "last_scanned": get_date(props.get("Last Scanned", {})),
    }


def current_week():
    now = datetime.now(HKT)
    return f"{now.year}-W{now.isocalendar()[1]:02d}"


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.before_request
def check_inactivity():
    if request.endpoint in ("login_page", "auth_callback", "static"):
        return
    # Allow unauthenticated access in local dev (no GOOGLE_CREDENTIALS_JSON)
    if not GOOGLE_CLIENT_ID:
        session.setdefault("user_email", "dev@withally.com")
        session.setdefault("user_name", "Dev")
        session["last_active"] = datetime.now().timestamp()
        return
    if "user_email" not in session:
        return redirect(url_for("login_page"))
    last = session.get("last_active")
    now = datetime.now().timestamp()
    if last and (now - last) > INACTIVITY_TIMEOUT:
        session.clear()
        return redirect(url_for("login_page"))
    session["last_active"] = now


@app.route("/login")
def login_page():
    if not GOOGLE_CLIENT_ID:
        return redirect(url_for("dashboard"))
    return render_template("login.html", client_id=GOOGLE_CLIENT_ID, error=request.args.get("error", ""))


@app.route("/auth/callback", methods=["POST"])
def auth_callback():
    token = request.form.get("credential", "")
    if not token:
        return redirect(url_for("login_page", error="No credential received"))
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport.requests import Request
        idinfo = google_id_token.verify_oauth2_token(token, Request(), GOOGLE_CLIENT_ID)
        email = idinfo.get("email", "")
        if email.split("@")[-1] != "withally.com":
            return redirect(url_for("login_page", error="Only @withally.com accounts allowed"))
        session["user_email"] = email
        session["user_name"] = idinfo.get("name", email.split("@")[0])
        session["user_picture"] = idinfo.get("picture", "")
        session["last_active"] = datetime.now().timestamp()
        return redirect(url_for("dashboard"))
    except Exception as e:
        return redirect(url_for("login_page", error=str(e)))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ── Page Routes ───────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    # Notion articles (clean pipeline)
    notion_articles = []
    if CONTENT_DB_ID:
        pages = notion_query(CONTENT_DB_ID)
        notion_articles = [extract_article(a) for a in pages]

    notion_stats = {}
    for status in STATUS_COLORS:
        notion_stats[status] = len([a for a in notion_articles if a["status"] == status])

    # Overview shows posts that are going out (Approved, Published)
    overview_posts = [a for a in notion_articles
                      if a["status"] in ("Approved", "Published")]
    overview_posts.sort(key=lambda a: (
        {"Approved": 0, "Published": 1}.get(a["status"], 2),
        a.get("date", ""),
    ))

    # Pending review — for Ivan's approval queue
    pending_review = [a for a in notion_articles
                      if a["status"] in ("Pending Approval", "Draft Ready")]
    pending_review.sort(key=lambda a: a.get("score", 0), reverse=True)

    # Workspace articles (local scan results)
    ws_count = len(workspace.get("articles", []))
    ws_drafts = len(workspace.get("drafts", {}))

    now = datetime.now(HKT)
    days_until_tuesday = (1 - now.weekday()) % 7
    if days_until_tuesday == 0 and now.hour >= 10:
        days_until_tuesday = 7
    next_publish = (now + timedelta(days=days_until_tuesday)).strftime("%A, %B %d")

    return render_template(
        "dashboard.html",
        notion_stats=notion_stats, status_colors=STATUS_COLORS,
        overview_posts=overview_posts,
        pending_review=pending_review,
        ws_count=ws_count, ws_drafts=ws_drafts,
        scan_engine=workspace.get("scan_engine", ""),
        scan_time=workspace.get("scan_time", ""),
        next_publish=next_publish,
        workflow_status=workflow_status,
    )


@app.route("/feed")
def feed_page():
    """Feed — two sections: portfolio reposts + industry insights."""
    articles = workspace.get("articles", [])

    # Split into portfolio vs industry
    portfolio_articles = [a for a in articles if a.get("company", "") != "Industry News"]
    industry_articles = [a for a in articles if a.get("company", "") == "Industry News"]

    # Group portfolio by brand
    brands_map = {}
    for a in portfolio_articles:
        company = a.get("company", "Other")
        brands_map.setdefault(company, []).append(a)
    for company in brands_map:
        brands_map[company].sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    sorted_brands = sorted(brands_map.keys())

    # Sort industry by relevance
    industry_articles.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    return render_template(
        "feed.html",
        brands_map=brands_map,
        sorted_brands=sorted_brands,
        industry_articles=industry_articles,
        portfolio_count=len(portfolio_articles),
        industry_count=len(industry_articles),
        total=len(articles),
        scan_engine=workspace.get("scan_engine", ""),
        scan_time=workspace.get("scan_time", ""),
    )


@app.route("/articles")
def articles_page():
    """Articles — workspace scan results, falling back to Notion Discovered articles."""
    articles = workspace.get("articles", [])
    drafts = workspace.get("drafts", {})

    # If workspace is empty, load Discovered articles from Notion
    if not articles and CONTENT_DB_ID:
        pages = notion_query(CONTENT_DB_ID, {
            "filter": {"property": "Status", "status": {"equals": "Discovered"}}
        })
        for page in pages:
            a = extract_article(page)
            articles.append({
                "id": a["id"],
                "title": a["title"],
                "company": a["company"],
                "url": a["source_url"],
                "source_url": a["source_url"],
                "source_type": a["source_type"],
                "key_insight": a["summary"],
                "relevance_score": a["score"],
                "date": a["date"],
                "notion_id": a["id"],
            })
            if a["draft"]:
                drafts[a["id"]] = a["draft"]

    # Attach draft text to articles
    for a in articles:
        a["draft"] = drafts.get(a["id"], "")

    return render_template(
        "articles.html", articles=articles, drafts=drafts,
        scan_engine=workspace.get("scan_engine", ""),
        scan_time=workspace.get("scan_time", ""),
        status_colors=STATUS_COLORS,
    )


@app.route("/drafts")
def drafts_page():
    """Pipeline — all articles from Notion with full status detail."""
    notion_articles = []
    if CONTENT_DB_ID:
        pages = notion_query(CONTENT_DB_ID)
        notion_articles = [extract_article(a) for a in pages]

    # Show all statuses except Discovered (those stay in Feed)
    pipeline = [a for a in notion_articles
                if a["status"] in ("Shortlisted", "Draft Ready", "Pending Approval", "Approved", "Published", "Rejected")]

    # Group by status for the template
    status_order = ["Pending Approval", "Approved", "Draft Ready", "Shortlisted", "Published", "Rejected"]
    pipeline.sort(key=lambda a: (
        status_order.index(a["status"]) if a["status"] in status_order else 99,
        -a.get("score", 0),
    ))

    # Stats for pipeline header
    pipeline_stats = {}
    for s in status_order:
        pipeline_stats[s] = len([a for a in pipeline if a["status"] == s])

    return render_template("drafts.html", drafts=pipeline, pipeline_stats=pipeline_stats, status_colors=STATUS_COLORS)


@app.route("/brands")
def brands_page():
    brands = []
    if BRANDS_DB_ID:
        pages = notion_query(BRANDS_DB_ID)
        brands = [extract_brand(b) for b in pages]
        brands.sort(key=lambda b: b["name"])
    return render_template("brands.html", brands=brands, team=TEAM)


# ── API: Workspace operations ─────────────────────────────────────────────────

@app.route("/api/scan/<engine>", methods=["POST"])
def api_scan(engine):
    """Trigger a news scan using the specified engine. Results go to local workspace."""
    valid = ["serper", "tavily"]
    if engine not in valid:
        return jsonify({"error": f"Invalid engine. Use: {valid}"}), 400

    if workflow_status.get("scan", {}).get("running"):
        return jsonify({"error": "Scan already running"}), 409

    workflow_status["scan"] = {
        "running": True, "engine": engine,
        "started": datetime.now(HKT).strftime("%H:%M HKT"),
        "status": f"Scanning with {engine}...", "log": "",
    }

    thread = threading.Thread(target=_run_scan, args=(engine,), daemon=True)
    thread.start()
    return jsonify({"success": True, "engine": engine})


@app.route("/api/generate-draft/<article_id>", methods=["POST"])
def api_generate_draft(article_id):
    """Generate a LinkedIn draft for a workspace or Notion article. Accepts optional feedback for regeneration."""
    article = next((a for a in workspace["articles"] if a["id"] == article_id), None)

    # If not in workspace, try loading from Notion
    if not article and CONTENT_DB_ID:
        try:
            page = requests.get(
                f"{NOTION_API_BASE}/pages/{article_id}",
                headers=notion_headers(), timeout=REQUEST_TIMEOUT
            ).json()
            if page.get("id"):
                a = extract_article(page)
                article = {
                    "id": a["id"],
                    "title": a["title"],
                    "company": a["company"],
                    "url": a["source_url"],
                    "source_url": a["source_url"],
                    "source_type": a["source_type"],
                    "key_insight": a["summary"],
                    "relevance_score": a["score"],
                }
                # Add to workspace so subsequent calls find it
                workspace["articles"].append(article)
        except Exception:
            pass

    if not article:
        return jsonify({"error": "Article not found"}), 404

    if workflow_status.get("draft_" + article_id, {}).get("running"):
        return jsonify({"error": "Already generating"}), 409

    # Get optional feedback and previous draft for regeneration
    data = request.get_json(silent=True) or {}
    feedback = data.get("feedback", "")
    previous_draft = workspace.get("drafts", {}).get(article_id, "")

    workflow_status["draft_" + article_id] = {"running": True, "status": "Generating..."}

    thread = threading.Thread(
        target=_run_single_draft,
        args=(article_id, article, feedback, previous_draft),
        daemon=True,
    )
    thread.start()
    return jsonify({"success": True})


@app.route("/api/send-to-notion", methods=["POST"])
def api_send_to_notion():
    """Push selected workspace articles (with drafts) to the clean Notion DB."""
    data = request.get_json()
    article_ids = data.get("article_ids", [])

    if not article_ids:
        return jsonify({"error": "No articles selected"}), 400

    sent = 0
    for aid in article_ids:
        article = next((a for a in workspace["articles"] if a["id"] == aid), None)
        if not article:
            continue

        draft = workspace["drafts"].get(aid, "")
        date_str = datetime.now(HKT).strftime("%Y-%m-%d")

        properties = {
            "Title": {"title": [{"type": "text", "text": {"content": article["title"][:2000]}}]},
            "Status": {"status": {"name": "Shortlisted"}},
            "Source URL": {"url": article.get("source_url") or None},
            "Portfolio Company": {"select": {"name": article.get("company", "Industry News")}},
            "Source Type": {"select": {"name": article.get("source_type", "News")}},
            "Relevance Score": {"number": article.get("relevance_score", 5)},
            "AI Summary": {"rich_text": [{"type": "text", "text": {"content": article.get("key_insight", "")[:2000]}}]},
            "Week": {"rich_text": [{"type": "text", "text": {"content": current_week()}}]},
            "Discovered Date": {"date": {"start": date_str}},
        }

        if draft:
            properties["Draft Post"] = {"rich_text": [{"type": "text", "text": {"content": draft[:2000]}}]}
            properties["Status"] = {"status": {"name": "Draft Ready"}}

        result = notion_create_page(CONTENT_DB_ID, properties)
        if result:
            sent += 1

    return jsonify({"success": True, "sent": sent})


@app.route("/api/send-for-approval", methods=["POST"])
def api_send_for_approval():
    """Send Draft Ready articles from Notion to Slack for Ivan's review."""
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL:
        return jsonify({"error": "Slack not configured"}), 400

    pages = notion_query(CONTENT_DB_ID, {
        "filter": {"property": "Status", "status": {"equals": "Draft Ready"}}
    })

    sent = 0
    for page in pages:
        article = extract_article(page)
        if _send_slack_approval(article):
            notion_update_page(article["id"], {"Status": {"status": {"name": "Pending Approval"}}})
            sent += 1

    return jsonify({"success": True, "sent": sent})


@app.route("/api/article/<page_id>/status", methods=["POST"])
def update_status(page_id):
    data = request.get_json()
    new_status = data.get("status", "")
    if new_status not in STATUS_COLORS:
        return jsonify({"error": "Invalid status"}), 400
    props = {"Status": {"status": {"name": new_status}}}
    if new_status == "Approved":
        props["Approved By"] = {"rich_text": [{"type": "text", "text": {"content": session.get("user_name", "Unknown")}}]}
    ok = notion_update_page(page_id, props)
    return jsonify({"success": ok})


@app.route("/api/article/<page_id>/notes", methods=["POST"])
def update_notes(page_id):
    data = request.get_json()
    props = {"Notes": {"rich_text": [{"type": "text", "text": {"content": data.get("notes", "")[:2000]}}]}}
    ok = notion_update_page(page_id, props)
    return jsonify({"success": ok})


@app.route("/api/brand/<page_id>/update", methods=["POST"])
def update_brand(page_id):
    data = request.get_json()
    props = {}
    if "linkedin_url" in data:
        val = data["linkedin_url"].strip()
        props["LinkedIn URL"] = {"url": val if val else None}
    if "keywords" in data:
        props["Search Keywords"] = {"rich_text": [{"type": "text", "text": {"content": data["keywords"][:2000]}}]}
    if "active" in data:
        props["Active"] = {"checkbox": bool(data["active"])}
    if props:
        ok = notion_update_page(page_id, props)
        return jsonify({"success": ok})
    return jsonify({"success": True})


@app.route("/api/workspace/draft/<article_id>")
def get_draft(article_id):
    """Get draft text for a workspace article."""
    draft = workspace.get("drafts", {}).get(article_id, "")
    running = workflow_status.get("draft_" + article_id, {}).get("running", False)
    return jsonify({"draft": draft, "running": running})


@app.route("/api/workflow-status")
def get_workflow_status():
    return jsonify(workflow_status)


# ── Slack approval cards ──────────────────────────────────────────────────────

def _send_slack_approval(article):
    """Send interactive approval card to Slack."""
    draft = article.get("draft", "No draft available")
    title = article.get("title", "Untitled")
    company = article.get("company", "Unknown")
    source_url = article.get("source_url", "")
    notion_url = article.get("notion_url", "")
    page_id = article.get("id", "")

    draft_preview = draft[:1500] if len(draft) > 1500 else draft

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Draft for Review: {title[:100]}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Company:*\n{company}"},
            {"type": "mrkdwn", "text": f"*Source:*\n<{source_url}|Article>"},
        ]},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*LinkedIn Draft:*\n```{draft_preview}```"}},
        {"type": "divider"},
        {"type": "actions", "block_id": f"approval_{page_id}", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Approve"}, "style": "primary",
             "action_id": "bioworld_approve", "value": page_id},
            {"type": "button", "text": {"type": "plain_text", "text": "Revise"},
             "action_id": "bioworld_revise", "value": page_id},
            {"type": "button", "text": {"type": "plain_text", "text": "Reject"}, "style": "danger",
             "action_id": "bioworld_reject", "value": page_id},
        ]},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"<{notion_url}|Open in Notion> | Score: {article.get('score', 0)}/10"},
        ]},
    ]

    try:
        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
            json={"channel": SLACK_CHANNEL, "text": f"Draft for review: {title}", "blocks": blocks},
            timeout=15,
        )
        return resp.ok and resp.json().get("ok", False)
    except Exception:
        return False


# ── Background workflows ──────────────────────────────────────────────────────

def _run_scan(engine):
    """Scan news and store results in local workspace."""
    import sys
    sys.path.insert(0, str(SKILL_ROOT / "libraries"))

    try:
        # Get brands from Notion
        brands = []
        if BRANDS_DB_ID:
            pages = notion_query(BRANDS_DB_ID, {
                "filter": {"property": "Active", "checkbox": {"equals": True}}
            })
            for page in pages:
                b = extract_brand(page)
                brands.append(b)

        all_articles = []

        if engine == "serper":
            from serper_scanner import search_company_news_serper, search_industry_news_serper
            serper_key = os.getenv("SERPER_API_KEY", "")
            for brand in brands:
                result = search_company_news_serper(brand["name"], brand["keywords"], serper_key)
                for s in result.get("sources", []):
                    s["company"] = brand["name"]
                    s["id"] = str(uuid.uuid4())[:8]
                    all_articles.append(s)
            result = search_industry_news_serper(serper_key)
            for s in result.get("sources", []):
                s["company"] = "Industry News"
                s["id"] = str(uuid.uuid4())[:8]
                all_articles.append(s)

        elif engine == "tavily":
            from tavily_scanner import search_company_news_tavily, search_industry_news_tavily
            tavily_key = os.getenv("TAVILY_API_KEY", "")
            for brand in brands:
                result = search_company_news_tavily(brand["name"], brand["keywords"], tavily_key)
                for s in result.get("sources", []):
                    s["company"] = brand["name"]
                    s["id"] = str(uuid.uuid4())[:8]
                    all_articles.append(s)
            result = search_industry_news_tavily(tavily_key)
            for s in result.get("sources", []):
                s["company"] = "Industry News"
                s["id"] = str(uuid.uuid4())[:8]
                all_articles.append(s)

        # Sort by relevance
        all_articles.sort(key=lambda a: a.get("relevance_score", 0), reverse=True)

        # Store in workspace
        workspace["articles"] = all_articles
        workspace["drafts"] = {}
        workspace["scan_engine"] = engine
        workspace["scan_time"] = datetime.now(HKT).strftime("%Y-%m-%d %H:%M HKT")
        save_workspace()

        # Auto-save discovered articles to Notion so they persist
        saved = 0
        if CONTENT_DB_ID:
            date_str = datetime.now(HKT).strftime("%Y-%m-%d")
            for article in all_articles:
                properties = {
                    "Title": {"title": [{"type": "text", "text": {"content": (article.get("title") or "")[:2000]}}]},
                    "Status": {"status": {"name": "Discovered"}},
                    "Source URL": {"url": article.get("url") or None},
                    "Portfolio Company": {"select": {"name": article.get("company", "Other")}},
                    "Source Type": {"select": {"name": article.get("source_type", "News")}},
                    "Relevance Score": {"number": article.get("relevance_score", 0)},
                    "AI Summary": {"rich_text": [{"type": "text", "text": {"content": (article.get("key_insight") or "")[:2000]}}]},
                    "Discovered Date": {"date": {"start": date_str}},
                    "Week": {"rich_text": [{"type": "text", "text": {"content": current_week()}}]},
                }
                if notion_create_page(CONTENT_DB_ID, properties):
                    saved += 1

        workflow_status["scan"]["status"] = "Complete"
        workflow_status["scan"]["log"] = f"Found {len(all_articles)} articles from {len(brands)} brands, saved {saved} to Notion"

    except Exception as e:
        workflow_status["scan"]["status"] = f"Error: {str(e)}"
    finally:
        workflow_status["scan"]["running"] = False
        workflow_status["scan"]["finished"] = datetime.now(HKT).strftime("%H:%M HKT")


def _run_single_draft(article_id, article, feedback="", previous_draft=""):
    """Generate a draft for a single article and store in workspace."""
    import sys
    sys.path.insert(0, str(SKILL_ROOT / "libraries"))

    try:
        from draft_generator import generate_draft

        # Build article dict in the format draft_generator expects
        article_data = {
            "title": article.get("title", ""),
            "summary": article.get("key_insight", ""),
            "source_url": article.get("url", ""),
            "company": article.get("company", ""),
            "source_type": article.get("source_type", "News"),
        }

        # If feedback provided, add regeneration context
        if feedback and previous_draft:
            article_data["regeneration_context"] = (
                f"PREVIOUS DRAFT (needs improvement):\n{previous_draft}\n\n"
                f"FEEDBACK FROM REVIEWER:\n{feedback}\n\n"
                f"Please generate an improved version addressing the feedback above."
            )

        draft_text = generate_draft(article_data)

        if draft_text:
            workspace["drafts"][article_id] = draft_text
            save_workspace()

            # If this is a Notion article (UUID format), save draft back to Notion
            if len(article_id) > 10 and "-" in article_id and CONTENT_DB_ID:
                notion_update_page(article_id, {
                    "Draft Post": {"rich_text": [{"type": "text", "text": {"content": draft_text[:2000]}}]},
                    "Status": {"status": {"name": "Draft Ready"}},
                })

        workflow_status["draft_" + article_id] = {"running": False, "status": "Complete"}

    except Exception as e:
        workflow_status["draft_" + article_id] = {"running": False, "status": f"Error: {str(e)}"}


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5001)
