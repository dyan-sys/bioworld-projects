# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ally OS is an automation platform for talent operations. The repository is organized by skills:

- `.claude/skills/` - Automation skills (each skill contains its own libraries, templates, and workflows)
- `local-data/` - Output artifacts (not committed to git)

Each skill has a `SKILL.md` with full documentation (workflows, templates, edge cases). Read the relevant SKILL.md when working on a specific skill.

## Development Setup

```bash
# Always use python3.11 (not python3) — dependencies are installed under 3.11
python3.11 --version  # Should show Python 3.11.x with OpenSSL 3.x
pip install -r requirements.txt
# Environment variables: see REFERENCE.md for full list
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
| Background Check | `.claude/skills/background-check/` | Screens candidates' online presence via Serper.dev (Google Search) + Gemini analysis. On-demand only. |
| Process EP Invoices | `.claude/skills/process-ep-invoices/` | Reconciles EP invoice submissions (Google Form) against time tracker sheet, flags mismatches to Slack, submits matched payments via Airwallex API. Runs days 1–3 of each month. Trigger: "Run EP invoices" (Step 1) or "Process invoices on Airwallex" (Step 2). |
| Review Airwallex Spend | `.claude/skills/review-airwallex-spend/` | Pulls all Airwallex transactions (cards, wallet, transfers) over a configurable window, groups by vendor, flags recurring subscriptions, writes review CSVs. On-demand. Trigger: "Review Airwallex spend". |
| Track Leave Requests | `.claude/skills/track-leave-requests/` | Reads new EP leave submissions from Ally HRIS Google Sheet, posts to #people-ops-private Slack, adds to Team Calendar, marks as Accepted. On-demand. Trigger: "Process leave requests". |
| Track AI Spend | `.claude/skills/track-ai-spend/` | Parses billing emails from Gmail, extracts AUD amounts, upserts monthly rows to Notion "AI Spend" DB. Runs monthly. |
| Code Jam | `.claude/skills/code-jam/` | Generates Google Slides decks for Claude Code Jam sessions + sets up Notion project tracker. Parameterized by jam number and EA names. |
| Create Playbook | `.claude/skills/create-playbook/` | Generates a branded internal HTML playbook dashboard — dark galactic theme, Ally brand, Lucide icons, Netlify Identity login, internal/external SOP access control. Trigger: "Create a playbook for [team]". |
| Markdown to Slides | `.claude/skills/md-to-slides/` | Converts `.md` slide files into styled Google Slides presentations via template deck cloning. On-demand. |
| CS Digest | `.claude/skills/cs-digest/` | Generates structured digest reports from mixed CS text files via Kimi AI. On-demand only. |
| Daily Pepper | `.claude/skills/daily-pepper/` | Morning calendar summary bot. Fetches Google Calendar events, sends Slack DM overview with free blocks. Runs daily 7 AM SGT. |
| Slack Bot | `.claude/skills/slack-bot/` | General-purpose Slack skill gateway. Exposes skills via slash commands (Socket Mode daemon). Phase 1: `/ally-invite`. |
| Find on Linear | `.claude/skills/find-on-linear/` | Finds Linear issues — quick wins, next tasks, work discovery. |
| First Time Setup | `.claude/skills/first-time-setup/` | Environment setup and troubleshooting for new team members. |
| Help on Gmail | `.claude/skills/help-on-gmail/` | Checks and triages ally-os-help emails from Gmail. |
| Mac Status | `.claude/skills/mac-status/` | Mac health diagnostic — memory, swap, disk, top processes, Ally job status. |
| Pepper | `.claude/skills/pepper/` | Personal EA — general assistance drawing on accumulated learnings. |
| YouTube Summarizer | `.claude/skills/youtube-summarizer/` | Summarizes YouTube videos and extracts insights from playlists. |
| Bioworld LinkedIn | `.claude/skills/bioworld-linkedin/` | Weekly LinkedIn automation for Bioworld Ventures — news scanning, draft generation, Ivan approval, auto-publishing. Trigger: "Scan Bioworld news", "Generate Bioworld drafts", "Publish Bioworld LinkedIn". |

For data architecture, scheduling, and env var details, see `REFERENCE.md`.

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
