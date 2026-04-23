"""
Bioworld LinkedIn — Content Hub Dashboard
------------------------------------------
Read-only pipeline viewer for the Bioworld LinkedIn content pipeline.
All data comes from Notion. Scanning and draft generation happen locally
via Claude Code.

Ivan can approve/reject articles and add notes from the dashboard.
"""

import json
import os
import secrets
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
    notion_articles = []
    if CONTENT_DB_ID:
        pages = notion_query(CONTENT_DB_ID)
        notion_articles = [extract_article(a) for a in pages]

    notion_stats = {}
    for status in STATUS_COLORS:
        notion_stats[status] = len([a for a in notion_articles if a["status"] == status])

    # Items needing review
    needs_review = notion_stats.get("Pending Approval", 0) + notion_stats.get("Draft Ready", 0)

    # Recently published (last 5)
    recently_published = [a for a in notion_articles if a["status"] == "Published"]
    recently_published.sort(key=lambda a: a.get("date", ""), reverse=True)
    recently_published = recently_published[:5]

    now = datetime.now(HKT)
    days_until_tuesday = (1 - now.weekday()) % 7
    if days_until_tuesday == 0 and now.hour >= 10:
        days_until_tuesday = 7
    next_publish = (now + timedelta(days=days_until_tuesday)).strftime("%A, %B %d")

    return render_template(
        "dashboard.html",
        notion_stats=notion_stats, status_colors=STATUS_COLORS,
        needs_review=needs_review,
        recently_published=recently_published,
        next_publish=next_publish,
    )


@app.route("/review")
def review_page():
    """Review — articles waiting for Ivan's approval."""
    notion_articles = []
    if CONTENT_DB_ID:
        pages = notion_query(CONTENT_DB_ID)
        notion_articles = [extract_article(a) for a in pages]

    # Show articles needing review: Pending Approval, Draft Ready, Shortlisted
    pipeline = [a for a in notion_articles
                if a["status"] in ("Pending Approval", "Draft Ready", "Shortlisted")]

    status_order = ["Pending Approval", "Draft Ready", "Shortlisted"]
    pipeline.sort(key=lambda a: (
        status_order.index(a["status"]) if a["status"] in status_order else 99,
        -a.get("score", 0),
    ))

    # Stats for filter pills
    pipeline_stats = {}
    for s in status_order:
        pipeline_stats[s] = len([a for a in pipeline if a["status"] == s])

    return render_template("review.html", drafts=pipeline, pipeline_stats=pipeline_stats, status_colors=STATUS_COLORS)


@app.route("/published")
def published_page():
    """Published — archive of approved and published articles."""
    notion_articles = []
    if CONTENT_DB_ID:
        pages = notion_query(CONTENT_DB_ID)
        notion_articles = [extract_article(a) for a in pages]

    # Show Published + Approved articles
    archive = [a for a in notion_articles
               if a["status"] in ("Approved", "Published")]

    # Published first, then Approved; within each group sort by date descending
    archive.sort(key=lambda a: (
        0 if a["status"] == "Published" else 1,
        a.get("date", "") or "",
    ), reverse=False)
    archive.sort(key=lambda a: a.get("date", "") or "", reverse=True)

    return render_template("published.html", articles=archive, status_colors=STATUS_COLORS)


@app.route("/brands")
def brands_page():
    brands = []
    if BRANDS_DB_ID:
        pages = notion_query(BRANDS_DB_ID)
        brands = [extract_brand(b) for b in pages]
        brands.sort(key=lambda b: b["name"])
    return render_template("brands.html", brands=brands, team=TEAM)


# ── API: Status & Notes ─────────────────────────────────────────────────────

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


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5001)
