# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ally OS is an automation platform for talent operations. The repository is organized by skills:

- `.claude/skills/` - Automation skills (each skill contains its own libraries, templates, and workflows)
- `local-data/` - Output artifacts (not committed to git)

Each skill has a `SKILL.md` with full documentation (workflows, templates, edge cases). Read the relevant SKILL.md when working on a specific skill.

## Development Setup

```bash
# Python Requirements
# Always use python3.11 (not python3) — dependencies are installed under 3.11
python3.11 --version  # Should show Python 3.11.x with OpenSSL 3.x

# Install dependencies
pip install -r requirements.txt

# Environment variables (create .env file)
NOTION_KEY=secret_xxx        # Notion integration token
NOTION_DB_ID=xxx             # Notion database ID
MOONSHOT_API_KEY=xxx         # Moonshot AI API key (for Kimi screener)
MOONSHOT_API_KEY_EP=xxx      # Separate Moonshot key for EP channel review (optional, falls back to MOONSHOT_API_KEY)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...        # Slack Incoming Webhook (optional, for daily report)
SLACK_WEBHOOK_URL_JARVIS=https://hooks.slack.com/services/... # Slack webhook for #ally-jarvis (service status)
SLACK_BOT_TOKEN=xoxb-xxx                                     # Slack Bot Token (channels:history, users:read)
GEMINI_API_KEY=xxx                                            # Google AI Studio API key (Gemini, for background check)
NOTION_SPEND_DB_ID=xxx                                        # Notion database ID for AI Spend tracking
```

## Skills

| Skill | Location | What it does |
|-------|----------|--------------|
| Resume Screening | `.claude/skills/screen-resume/` | Scores candidates via Kimi AI or Claude CLI against job-specific rubrics. Kimi recommended (most accurate). |
| Update Resume Screener | `.claude/skills/update-resume-screener/` | Process docs for adding new job-specific scoring rubrics. No code — just templates + config. |
| Update Job Posts | `.claude/skills/update-job-posts/` | Creates Notion job post pages per channel (OLJ, Jobstreet, Facebook, Internal) with platform templates. |
| Check Recruit Status | `.claude/skills/check-recruit-status/` | Queries Candidates DB, generates pipeline report (7 sections), optionally posts to Slack. |
| Invite Candidates | `.claude/skills/invite-candidates/` | Creates Gmail DRAFT emails for R1 invitations. Routes by Screener status. Never sends — drafts only. |
| Track Recruitment Events | `.claude/skills/track-recruitment-events/` | Tracks async completions (Hireflix/HireTruffle) and Calendly bookings. Matches candidates in Notion, creates Interactions or updates 1R status. |
| Flag EP Issues | `.claude/skills/flag-ep-issues/` | Reviews EP Slack channels daily via Kimi AI, flags missed items / stalled progress to #ally-jarvis. |
| Check Service Status | `.claude/skills/check-service-status/` | Monitors scheduled jobs (ran? exit code? artifacts?), posts health summary to Slack. |
| Slack Mentions | `.claude/skills/slack-mentions/` | Scans Slack for unactioned @mentions, DMs a summary with deep links. Runs 3x daily. |
| LinkedIn Content | `.claude/skills/linkedin-content/` | Generates LinkedIn post drafts via Kimi research + synthesis. Drafts to local files for human review. |
| Recruit Consulting | `.claude/skills/recruit-consulting/` | AI-assisted review of client JDs and interview templates for CS roles. Interactive process, no Python workflows. |
| Adapt Client JD | `.claude/skills/adapt-client-jd/` | Adapts client JDs for specific job platforms (OLJ, Jobstreet) with format rules. |
| Background Check | `.claude/skills/background-check/` | Screens candidates' online presence via Gemini + Google Search grounding. Checks LinkedIn consistency, news/legal, social media. On-demand only. |
| Track AI Spend | `.claude/skills/track-ai-spend/` | Parses billing emails from Gmail, extracts AUD amounts, upserts monthly rows to Notion "AI Spend" DB. Runs monthly. |

## Data Architecture

```
local-data/
├── logs/                         # Scheduling logs (launchd output)
├── service-status/               # Job status JSONs from run-job.sh
│   ├── {job-id}_{timestamp}.json
│   └── reports/                  # Service check report snapshots
├── slack-mentions/               # Mention monitor state
│   └── state.json
├── linkedin/                     # LinkedIn content engine artifacts
│   ├── research/
│   └── drafts/
├── ai-spend/                     # AI spend tracking receipts
└── talent/
    ├── resume_raw_txt/           # Extracted resume text
    ├── resume_receipts/          # Full scoring JSON (Claude + Kimi)
    ├── pipeline_reports/         # Daily pipeline report snapshots
    ├── ep_reviews/               # EP channel review artifacts
    ├── async_completions/        # Recruitment event tracking receipts
    └── invite_emails/            # R1 invite draft receipts
```

## Scheduling

Scheduled jobs run via macOS `launchd`. All jobs use `scheduling/run-job.sh` which handles network readiness, logging, and status tracking.

```bash
scheduling/run-job.sh <job-id> <python-script>
```

Status values: `success` (exit 0), `failed` (exit non-zero), `network_unavailable`

| Job | Schedule (SGT) | Plist |
|-----|----------------|-------|
| Daily Pipeline Report | 08:00 daily | `com.ally.pipeline-report.plist` |
| EP Channel Issue Flagging | 08:00 daily | `com.ally.ep-issues.plist` |
| Scheduled Job Posts | 08:00 Mon + Thu | `com.ally.job-posts.plist` |
| Resume Screener (Kimi) | 08:00, 12:00, 16:00, 20:00 | `com.ally.resume-screener.plist` |
| Slack Mention Monitor | 09:00, 13:00, 17:00 | `com.ally.slack-mentions.plist` |
| Recruitment Completion Tracker | 08:00, 12:00, 18:00 | `com.ally.recruitment-events.plist` |
| Service Health Check | 09:00 daily | `com.ally.service-check.plist` |
| AI Spend Tracker | 08:00 on 2nd of month | `com.ally.ai-spend.plist` |

### Adding a New Scheduled Job

1. Create a launchd plist (copy existing, update Label/ProgramArguments/schedule)
2. Add entry to `.claude/skills/check-service-status/templates/job-registry.json`
3. Install plist to `~/Library/LaunchAgents/` and bootstrap

### Install / Uninstall

```bash
# Install (example for pipeline report — repeat pattern for other jobs)
cp scheduling/com.ally.pipeline-report.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ally.pipeline-report.plist

# Uninstall
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.ally.pipeline-report.plist
rm ~/Library/LaunchAgents/com.ally.pipeline-report.plist
```

**Logs:** `local-data/logs/` (gitignored)
**Status files:** `local-data/service-status/` (gitignored)

## Linear MCP Tool

- To update issue status, use the `state` parameter (not `status`). The `status` param is silently ignored.
- When multiple states share the same type (e.g., "Canceled" and "Duplicate" are both type `canceled`), use the **UUID** instead of the name to avoid ambiguous matching.
- Team: "With Ally", team ID: `f3fb95e8-5a4d-4949-b49e-4cf4c95f81d9`

## Notion Database Schema

Required properties for candidate database:
- `Full Name` (title)
- `Resume` (files)
- `Claude Rating` (rich_text)
- `Claude Recommendation` (select)
- `Claude Rationale` (rich_text)
- `Kimi Rating` (rich_text)
- `Kimi Recommendation` (select)
- `Kimi Rationale` (rich_text)
- `Status` (status)
- `Date Created` (created_time)
