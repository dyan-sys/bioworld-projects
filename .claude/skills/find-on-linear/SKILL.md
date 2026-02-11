---
name: find-on-linear
description: Trigger when user mentions finding Linear issues, looking for work, picking up tasks, quick wins, or next project
user_invocable: true
---

# Find on Linear

Browse open Linear issues and pick something to work on. Offers a quick toggle between small tasks and bigger projects.

## Workflow

### 1. Ask what kind of work

Use `AskUserQuestion` to present the toggle:

- **Quick wins** — Small, well-scoped tasks I can knock out fast (filters: priority Low/Normal, no project, not blocked)
- **Significant project** — Larger effort with more impact (filters: priority Urgent/High, or issues in a project)

### 2. Fetch issues from Linear

Use the Linear MCP tools. Team is **"With Ally"** (ID: `f3fb95e8-5a4d-4949-b49e-4cf4c95f81d9`).

**Quick wins query:**
```
list_issues(team: "With Ally", state: "started", priority: 4, limit: 10)
list_issues(team: "With Ally", state: "unstarted", priority: 4, limit: 10)
list_issues(team: "With Ally", state: "unstarted", priority: 3, limit: 10)
```
Merge results. Exclude issues that have blockers or are sub-issues of larger epics.

**Significant project query:**
```
list_issues(team: "With Ally", state: "started", priority: 1, limit: 10)
list_issues(team: "With Ally", state: "started", priority: 2, limit: 10)
list_issues(team: "With Ally", state: "unstarted", priority: 1, limit: 10)
list_issues(team: "With Ally", state: "unstarted", priority: 2, limit: 10)
```
Merge results. Prefer issues attached to a project or cycle.

### 3. Present results

Show a clean table:

| # | Issue | Priority | Status | Labels | Created |
|---|-------|----------|--------|--------|---------|

- Sort by priority (urgent first), then by most recently updated
- Cap at ~10 results
- For each issue show the identifier (e.g. `WA-42`), title, priority emoji (urgent/high/normal/low), state name, labels, and created date
- If no issues found, say so and suggest trying the other mode

### 4. Let user pick

After showing the table, ask: **"Want to dive into any of these? Give me a number or issue ID."**

When the user picks one, fetch full details with `get_issue` and display:
- Full description
- Comments (if any)
- Sub-issues (if any)
- Assignee, project, cycle info

Then ask if they want to start working on it (update state to In Progress).
