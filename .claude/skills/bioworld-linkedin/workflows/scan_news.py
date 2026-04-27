"""
Bioworld LinkedIn — Scan News Workflow

Phase 1+2: Discover articles from portfolio companies + industry,
rank them, and shortlist top 3-5 to Notion.

Supports two search engines:
  --engine kimi    (default) Uses Moonshot/Kimi with built-in web search
  --engine serper  Uses Serper.dev (Google Search) + Claude analysis

Usage:
    python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py
    python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py --engine serper
    python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py --top 5
    python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py --company "CorVista Health"
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

SKILL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[4]

sys.path.insert(0, str(SKILL_ROOT / "libraries"))
from news_scanner import (
    generate_search_queries,
    search_company_news,
    search_industry_news,
    rank_articles,
)
from serper_scanner import (
    search_company_news_serper,
    search_industry_news_serper,
)
from notion_dashboard import (
    get_active_brands,
    update_brand_last_scanned,
    add_article,
    check_duplicate,
    get_articles_by_status,
    update_article_status,
)

load_dotenv(PROJECT_ROOT / ".env")

HKT = timezone(timedelta(hours=8))
TEMPLATE_DIR = SKILL_ROOT / "templates"


def current_week() -> str:
    """Return ISO week string like '2026-W16'."""
    now = datetime.now(HKT)
    return f"{now.year}-W{now.isocalendar()[1]:02d}"


def main():
    parser = argparse.ArgumentParser(description="Scan news for Bioworld LinkedIn")
    parser.add_argument("--top", type=int, default=5, help="Number of articles to shortlist (default: 5)")
    parser.add_argument("--company", type=str, default=None, help="Scan a single company only")
    parser.add_argument("--skip-industry", action="store_true", help="Skip industry-wide searches")
    parser.add_argument("--engine", type=str, default="kimi", choices=["kimi", "serper"],
                        help="Search engine: 'kimi' (Moonshot) or 'serper' (Google+Claude)")
    args = parser.parse_args()

    # Check env
    notion_key = os.environ.get("BIOWORLD_NOTION_KEY") or os.environ.get("NOTION_KEY")
    content_db_id = os.environ.get("BIOWORLD_CONTENT_DB_ID")
    brands_db_id = os.environ.get("BIOWORLD_BRANDS_DB_ID")

    missing = []
    if not notion_key:
        missing.append("NOTION_KEY")
    if not content_db_id:
        missing.append("BIOWORLD_CONTENT_DB_ID")
    if not brands_db_id:
        missing.append("BIOWORLD_BRANDS_DB_ID")

    # Engine-specific checks
    if args.engine == "kimi":
        moonshot_key = os.environ.get("MOONSHOT_API_KEY")
        if not moonshot_key:
            missing.append("MOONSHOT_API_KEY")
    else:
        serper_key = os.environ.get("SERPER_API_KEY")
        if not serper_key:
            missing.append("SERPER_API_KEY")

    if missing:
        print(f"Error: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    date_str = datetime.now(HKT).strftime("%Y-%m-%d")
    week_str = current_week()
    engine = args.engine

    print("=" * 60)
    print("BIOWORLD LINKEDIN — NEWS SCANNER")
    print("=" * 60)
    print(f"  Date:   {date_str}")
    print(f"  Week:   {week_str}")
    print(f"  Engine: {engine.upper()}")
    print(f"  Top:    {args.top}")

    # Get active brands
    print("\nFetching active brands from Notion...")
    brands = get_active_brands(notion_key, brands_db_id)

    if args.company:
        brands = [b for b in brands if b["name"].lower() == args.company.lower()]
        if not brands:
            print(f"  Company '{args.company}' not found in active brands.")
            sys.exit(1)

    print(f"  Found {len(brands)} active brands")

    # Phase 1: Scan each brand
    all_articles = []

    for brand in brands:
        name = brand["name"]
        keywords = brand["keywords"]

        print(f"\n--- Scanning: {name} ---")

        if engine == "kimi":
            queries = generate_search_queries(name, keywords, moonshot_key)
            print(f"  Queries: {queries}")
            result = search_company_news(name, queries, moonshot_key)
        else:
            result = search_company_news_serper(name, keywords, serper_key, linkedin_url=brand.get("linkedin_url", ""))

        sources = result.get("sources", [])
        print(f"  Found {len(sources)} articles")

        for source in sources:
            source["portfolio_company"] = name
            all_articles.append(source)

        # Update last scanned
        update_brand_last_scanned(notion_key, brand["page_id"], date_str)

    # Phase 1b: Industry searches
    if not args.skip_industry:
        print(f"\n--- Scanning: Industry News ---")

        if engine == "kimi":
            config_path = TEMPLATE_DIR / "brand-config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            industry_queries = config.get("industry_searches", [])
            if industry_queries:
                result = search_industry_news(industry_queries, moonshot_key)
        else:
            result = search_industry_news_serper(serper_key)

        sources = result.get("sources", [])
        print(f"  Found {len(sources)} industry articles")

        for source in sources:
            source["portfolio_company"] = "Industry News"
            all_articles.append(source)

    print(f"\n{'=' * 60}")
    print(f"Total articles found: {len(all_articles)}")

    # Phase 2: Deduplicate and insert into Notion
    print("\nDeduplicating and inserting into Notion...")
    inserted = 0
    skipped = 0

    for article in all_articles:
        url = article.get("url", "")
        if not url:
            skipped += 1
            continue

        if check_duplicate(notion_key, content_db_id, url):
            print(f"  [SKIP] Already exists: {article.get('title', '')[:60]}")
            skipped += 1
            continue

        # Use published_date from article if available, otherwise today
        article_date = article.get("published_date", "") or date_str

        notion_article = {
            "title": article.get("title", "Untitled"),
            "source_url": url,
            "portfolio_company": article.get("portfolio_company", "Industry News"),
            "source_type": article.get("source_type", "News"),
            "relevance_score": article.get("relevance_score", 5),
            "ai_summary": article.get("key_insight", ""),
            "week": week_str,
            "discovered_date": article_date,
        }

        add_article(notion_key, content_db_id, notion_article)
        inserted += 1
        print(f"  [+] {article.get('title', '')[:60]}")

    print(f"\n  Inserted: {inserted}")
    print(f"  Skipped (duplicates/no URL): {skipped}")

    # Phase 2b: Rank and shortlist
    print(f"\nRanking articles for shortlisting (top {args.top})...")
    discovered = get_articles_by_status(notion_key, content_db_id, "Discovered", week=week_str)
    print(f"  Discovered articles this week: {len(discovered)}")

    # Sort by relevance score and shortlist top N
    scored = []
    for page in discovered:
        props = page["properties"]
        score = props.get("Relevance Score", {}).get("number", 0) or 0
        title_parts = props.get("Title", {}).get("title", [])
        title = title_parts[0]["plain_text"] if title_parts else "Untitled"
        scored.append((score, title, page["id"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    shortlisted = scored[:args.top]

    for score, title, page_id in shortlisted:
        update_article_status(notion_key, page_id, "Shortlisted")
        print(f"  [*] Score {score}: {title[:60]}")

    print(f"\n  Shortlisted: {len(shortlisted)}")

    # Summary
    print("\n" + "=" * 60)
    print("SCAN COMPLETE")
    print("=" * 60)
    print(f"  Articles found:      {len(all_articles)}")
    print(f"  New articles added:  {inserted}")
    print(f"  Shortlisted:         {len(shortlisted)}")
    print(f"\nNext: Run generate_drafts.py to create LinkedIn post drafts.")


if __name__ == "__main__":
    main()
