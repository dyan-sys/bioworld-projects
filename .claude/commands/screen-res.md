---
description: Screen candidate resumes using AI scoring
argument-hint: [model-or-url]
allowed-tools: Bash(python3:*), Read, Grep, Glob
---

Screen candidate resumes using the Ally OS resume screener pipeline.

Parse the following arguments: $ARGUMENTS

## Argument Parsing

The argument can be:
1. **A model name** (`kimi`, `claude`, or `codex`) — use that screener variant
2. **A Notion URL** (contains `notion.so` or `notion.site`) — score that specific candidate using the default model (Kimi)
3. **Both** a model name AND a Notion URL — score that specific candidate with the specified model
4. **Empty** — run the default Kimi batch screener

## Model → Script Mapping

| Model | Script |
|-------|--------|
| `kimi` (default) | `workflows/talent/resume_screener_kimi.py` |
| `claude` | `workflows/talent/resume_screener.py` |
| `codex` | `workflows/talent/resume_screener_codex.py` |

## Execution

### Batch Mode (no Notion URL provided)

Run the appropriate screener script from the project root:

```bash
python3 workflows/talent/resume_screener_<variant>.py
```

Report the results — how many candidates were scored, any errors encountered.

### Single-Candidate Mode (Notion URL provided)

When a Notion URL is provided for a specific candidate page:

1. Extract the Notion page ID from the URL
2. Use the Notion API (via `NOTION_KEY` env var) to fetch the page and get the candidate's name and resume PDF URL
3. Extract resume text using `libraries/pdf_tools.py` → `extract_text_from_url()`
4. Load the scoring rubric from `templates/resume-scorer-v4.md`
5. Call the appropriate AI model to score the resume against the rubric
6. Save the receipt JSON to `data/talent/resume_receipts/`
7. Update the Notion page with the rating, recommendation, and rationale

For single-candidate mode, reference the batch screener script for the chosen model to understand the exact API calls, Notion field names, and JSON structure. Follow the same patterns.

## After Completion

Summarize results: candidate name(s), score(s), recommendation(s), and any errors.
