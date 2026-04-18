# Bioworld LinkedIn Automation

Weekly LinkedIn content automation for Bioworld Ventures — discovers portfolio company news, generates post drafts, routes through Ivan's approval, and publishes to the company LinkedIn page.

## Triggers
- "Scan Bioworld news" or "Run Bioworld LinkedIn scan" → `scan_news.py`
- "Generate Bioworld drafts" → `generate_drafts.py`
- "Notify Ivan for Bioworld approval" → `notify_approval.py`
- "Publish Bioworld LinkedIn" → `publish_approved.py`
- "Set up Bioworld dashboard" → `setup_dashboard.py`

## Weekly Workflow

```
Monday 8 AM HKT:
  1. scan_news.py     → searches 12 portfolio companies + industry trends
  2. generate_drafts.py → creates LinkedIn post drafts for top 3-5 articles
  3. notify_approval.py → posts drafts to #bioworld-linkedin for Ivan

Monday-Tuesday:
  4. Ivan reviews in Notion → Approved / Rejected

Tuesday 10 AM HKT:
  5. publish_approved.py → posts Approved articles to LinkedIn company page
```

## Architecture

```
.claude/skills/bioworld-linkedin/
├── SKILL.md
├── libraries/
│   ├── news_scanner.py          # Kimi web search per brand + industry
│   ├── article_ranker.py        # Ranking logic (used within news_scanner)
│   ├── draft_generator.py       # LinkedIn post draft generation
│   ├── notion_dashboard.py      # Notion CRUD for Content Pipeline + Brands DBs
│   └── linkedin_publisher.py    # LinkedIn API posting + token refresh
├── templates/
│   ├── brand-config.json        # 12 portfolio companies + search seeds
│   ├── content-strategy.md      # Bioworld voice and positioning
│   ├── post-system-prompt.md    # Draft generation system prompt
│   └── research-prompt.md       # News scanning system prompt
└── workflows/
    ├── setup_dashboard.py       # One-time Notion dashboard setup
    ├── scan_news.py             # Phase 1+2: discover + rank + shortlist
    ├── generate_drafts.py       # Phase 3: generate LinkedIn post drafts
    ├── notify_approval.py       # Slack notification for approval
    └── publish_approved.py      # Phase 4: post to LinkedIn API
```

## Notion Dashboard

**Content Pipeline** database tracks articles through:
`Discovered → Shortlisted → Draft Ready → Pending Approval → Approved → Published`

**Portfolio Brands** database tracks 12 companies:
CorVista Health, Senti Biosciences, Cardea Bio, Foundation Medicine, Arima Genomics, Vena Vitals, Hello Vigor, YOR Labs, Mii Care, Great Bay Bio, Endia Therapeutics, Rare Air Health

## Environment Variables

```bash
# Required (existing)
NOTION_KEY
MOONSHOT_API_KEY
SLACK_BOT_TOKEN

# Required (set after setup_dashboard.py)
BIOWORLD_CONTENT_DB_ID
BIOWORLD_BRANDS_DB_ID
BIOWORLD_SLACK_CHANNEL        # #bioworld-linkedin channel ID

# Optional (for auto-posting)
LINKEDIN_ACCESS_TOKEN
LINKEDIN_REFRESH_TOKEN
LINKEDIN_CLIENT_ID
LINKEDIN_CLIENT_SECRET
BIOWORLD_LINKEDIN_ORG_ID
```

## First-Time Setup

1. Pick a Notion page to host the dashboard
2. Run: `python3.11 .claude/skills/bioworld-linkedin/workflows/setup_dashboard.py --parent-id <PAGE_ID>`
3. Add printed DB IDs to `.env`
4. Create `#bioworld-linkedin` Slack channel, add bot, note channel ID
5. Add `BIOWORLD_SLACK_CHANNEL=<channel_id>` to `.env`
6. (Optional) Set up LinkedIn API credentials for auto-posting

## CLI Usage

```bash
# One-time setup
python3.11 .claude/skills/bioworld-linkedin/workflows/setup_dashboard.py --parent-id abc123

# Weekly scan (discovers + ranks + shortlists)
python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py
python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py --top 3
python3.11 .claude/skills/bioworld-linkedin/workflows/scan_news.py --company "CorVista Health"

# Generate drafts for shortlisted articles
python3.11 .claude/skills/bioworld-linkedin/workflows/generate_drafts.py

# Send drafts to Slack for Ivan's approval
python3.11 .claude/skills/bioworld-linkedin/workflows/notify_approval.py

# Publish approved posts to LinkedIn
python3.11 .claude/skills/bioworld-linkedin/workflows/publish_approved.py
python3.11 .claude/skills/bioworld-linkedin/workflows/publish_approved.py --dry-run
```

## Posting Tone

Professional, celebratory, forward-looking. Portfolio milestones framed as highlights. Uses emoji markers and 3-5 hashtags. See `templates/content-strategy.md` for full voice guide.

## Edge Cases

- **No news found**: Scanner logs "0 articles" — may happen for smaller portfolio companies. Industry searches provide fallback content.
- **Duplicate articles**: Deduplication by URL prevents re-adding known articles.
- **No approvals by Tuesday**: Publisher posts nothing, notifies Slack "No approved posts this week."
- **LinkedIn token expired**: Publisher attempts auto-refresh. If refresh fails, error posted to Slack.
- **Rate limits**: Notion API retries with exponential backoff (3 attempts). Kimi uses HTTP/2 with 600s timeout.
