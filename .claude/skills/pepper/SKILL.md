# Pepper — Personal EA

Pepper is your Personal Executive Assistant skill. Unlike other skills that automate specific workflows, Pepper is a growing knowledge base for general-purpose assistance patterns — the things a good EA just *knows* how to handle.

## Philosophy

- No pre-loaded workflows. Learnings accumulate organically from real interactions.
- Each pattern captured here should be something that came up naturally and proved useful.
- Pepper is the skill you invoke when the task doesn't fit neatly into another skill.

## How It Works

When `/pepper` is invoked, read this file and the `learnings/` directory to recall accumulated context, then assist with whatever the user needs — drawing on patterns, preferences, and past decisions documented here.

## Learnings

Documented in `learnings/` as individual markdown files, organized by topic:

| File | Topic |
|------|-------|
| `client-meeting-prep.md` | Patterns for prepping client-facing meetings (context gathering, personalizing templates, surfacing tensions, teammate handoff) |

Future topics:
- Communication preferences and templates
- Decision-making frameworks used repeatedly
- Vendor/tool notes and gotchas
- Recurring requests and how they were handled

## Owner Preferences

- **Client emails always from ivan@withally.com** — use `gmail_token_ivan.json` token (not the recruitment@ default). Pass `credentials_path='Google-credentials.json'` and `token_path='local-data/gmail_token_ivan.json'` to `get_gmail_service()`.

## Templates

Email templates in `templates/`, ready to customize per client:

| File | Use Case |
|------|----------|
| `post-deep-dive-email-full.md` | Full post-deep-dive email with partnership recap, EP intro, pricing, attached docs, and contract detail request. Use when client hasn't received a formal overview yet. |
| `post-deep-dive-email-short.md` | Short thank-you + contract details ask. Use when client already has context and just needs the follow-up. |

**Usage:** Read the template, fill in `{{placeholders}}`, drop `{{OPTIONAL: ...}}` blocks if not needed.

## Playbooks

*(To be added as repeatable patterns are identified)*
