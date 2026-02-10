---
description: Review changes, update Linear ticket, commit and push
allowed-tools: Bash(git:*), Read, Grep, Glob, AskUserQuestion, mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__update_issue, mcp__claude_ai_Linear__create_comment, mcp__claude_ai_Linear__list_issue_statuses
---

Bundle the review-update-commit-push workflow into one interactive flow. Walk through each step below, asking the user for input at each decision point.

## Step 1: Detect Changes

Run `git status` and `git diff` (both staged and unstaged) to see all current changes. Summarize what changed for the user — which files were modified, added, or deleted, and a brief description of the changes.

If there are no changes at all, tell the user and stop.

## Step 2: Linear Ticket Selection

Use `mcp__claude_ai_Linear__list_issues` to fetch recent issues from the "With Ally" team (team ID: `f3fb95e8-5a4d-4949-b49e-4cf4c95f81d9`). Filter for in-progress/started issues.

Present the issues to the user via AskUserQuestion with a "Skip Linear update" option. If the user skips, jump directly to Step 5 (Commit).

## Step 3: Status Update

If a ticket was selected, use `mcp__claude_ai_Linear__list_issue_statuses` to get available statuses for the team.

Ask the user which status to set, with "Keep current status" as an option.

If the user picks a new status, update it via `mcp__claude_ai_Linear__update_issue` using the `state` parameter (NOT `status` — the `status` param is silently ignored). Use the state UUID when multiple states share the same type to avoid ambiguous matching.

## Step 4: Linear Comment

Draft a comment based on the git diff — summarize what was changed or learned. Show the draft to the user for confirmation or editing via AskUserQuestion (with options like "Post as-is", "Skip comment").

If confirmed, post via `mcp__claude_ai_Linear__create_comment`.

## Step 5: Commit

Stage the relevant changed files with `git add` (list specific files, do NOT use `git add -A` or `git add .`). Show the user which files will be staged.

Draft a concise commit message based on the changes. Ask the user to confirm or edit.

Create the commit. Include the co-author trailer:
```
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

## Step 6: Push

Run `git push` to push the commit to the remote.

Report the final result — commit hash, Linear ticket updated (if any), and push status.
