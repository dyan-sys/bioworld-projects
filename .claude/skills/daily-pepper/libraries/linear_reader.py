"""
Linear Reader — Fetch and categorize active issues for the Focus Board.

Uses Linear's GraphQL API directly (no MCP dependency) so it works in scheduled jobs.
"""

import os
import urllib.request
import urllib.error
import json

LINEAR_API_URL = "https://api.linear.app/graphql"
LINEAR_WORKSPACE_SLUG = "with-ally"

PRIORITY_EMOJI = {
    0: ":white_circle:",    # No priority
    1: ":rotating_light:",  # Urgent
    2: ":arrow_up:",        # High
    3: ":arrow_right:",     # Normal
    4: ":arrow_down:",      # Low
}

ISSUES_QUERY = """
query FocusBoard($teamId: ID!) {
  issues(
    filter: {
      team: { id: { eq: $teamId } }
      assignee: { isMe: { eq: true } }
      state: { type: { nin: ["completed", "canceled"] } }
    }
    first: 50
    orderBy: updatedAt
  ) {
    nodes {
      identifier
      title
      priority
      updatedAt
      state { type }
    }
  }
}
"""


def fetch_issues(team_id: str, api_key: str | None = None) -> list[dict]:
    """Fetch active issues for a team from Linear's GraphQL API.

    Returns a list of issue dicts with keys: identifier, title, priority, updatedAt, state_type.
    Raises on HTTP/network errors.
    """
    api_key = api_key or os.environ.get("LINEAR_API_KEY")
    if not api_key:
        raise ValueError("LINEAR_API_KEY not set")

    payload = json.dumps({"query": ISSUES_QUERY, "variables": {"teamId": team_id}}).encode()
    req = urllib.request.Request(
        LINEAR_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())

    if "errors" in body:
        raise RuntimeError(f"Linear API errors: {body['errors']}")

    nodes = body.get("data", {}).get("issues", {}).get("nodes", [])
    return [
        {
            "identifier": n["identifier"],
            "title": n["title"],
            "priority": n["priority"],
            "updatedAt": n["updatedAt"],
            "state_type": n["state"]["type"],
        }
        for n in nodes
    ]


def categorize(issues: list[dict], per_bucket: int = 3) -> dict[str, list[dict]]:
    """Split issues into quick_wins (pri 3-4) and strategic (pri 1-2).

    - Strategic impact: priority 1-2, sorted by priority asc then oldest first
    - Quick wins: priority 3-4, sorted by most recently updated
    Each bucket targets exactly `per_bucket` items. If one bucket is short,
    overflow from the other fills the gap.
    """
    strategic_pool = [i for i in issues if i["priority"] in (1, 2)]
    quick_pool = [i for i in issues if i["priority"] not in (1, 2)]

    strategic_pool.sort(key=lambda i: (i["priority"], i["updatedAt"]))
    quick_pool.sort(key=lambda i: i["updatedAt"], reverse=True)

    strategic = strategic_pool[:per_bucket]
    quick_wins = quick_pool[:per_bucket]

    # Backfill: if one bucket is short, pull extras from the other
    if len(strategic) < per_bucket and len(quick_pool) > per_bucket:
        need = per_bucket - len(strategic)
        strategic.extend(quick_pool[per_bucket : per_bucket + need])
    elif len(quick_wins) < per_bucket and len(strategic_pool) > per_bucket:
        need = per_bucket - len(quick_wins)
        quick_wins.extend(strategic_pool[per_bucket : per_bucket + need])

    return {
        "strategic": strategic,
        "quick_wins": quick_wins,
    }


def format_focus_board(buckets: dict[str, list[dict]]) -> str:
    """Format categorized issues into a Slack mrkdwn Focus Board section.

    Returns empty string if both buckets are empty.
    """
    strategic = buckets.get("strategic", [])
    quick_wins = buckets.get("quick_wins", [])

    if not strategic and not quick_wins:
        return ""

    lines = ["\n:dart: *Suggested Focus Board*", ""]

    def _issue_line(issue: dict) -> str:
        emoji = PRIORITY_EMOJI.get(issue["priority"], "")
        url = f"https://linear.app/{LINEAR_WORKSPACE_SLUG}/issue/{issue['identifier']}"
        return f"  {emoji} <{url}|{issue['identifier']}> {issue['title']}"

    if strategic:
        lines.append("_Strategic Impact:_")
        for issue in strategic:
            lines.append(_issue_line(issue))

    if quick_wins:
        if strategic:
            lines.append("")
        lines.append("_Quick Wins:_")
        for issue in quick_wins:
            lines.append(_issue_line(issue))

    return "\n".join(lines)


def get_focus_board(team_id: str, api_key: str | None = None) -> str:
    """High-level entry point: fetch → categorize → format.

    Returns formatted mrkdwn string, or empty string on any failure (logged).
    """
    issues = fetch_issues(team_id, api_key)
    buckets = categorize(issues)
    return format_focus_board(buckets)
