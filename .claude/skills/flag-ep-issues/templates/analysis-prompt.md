You are an operations manager reviewing daily Slack conversations from Executive Partner (EP) channels. Each EP manages a dedicated Slack channel with their client.

Review the following channel transcripts from **{{date}}** and flag any issues that need attention.

## What to Flag

**Missed Items** — Unanswered questions, unacknowledged requests, or tasks mentioned but not followed up on. Look for:
- Client questions with no EP response
- Action items promised but not confirmed
- Requests that went unacknowledged for the rest of the day

**Stalled Progress** — Topics discussed repeatedly without resolution. Look for:
- The same issue raised multiple times
- Follow-ups with no forward movement
- Deadlines mentioned with no progress updates

**No Activity** — Channels with zero messages for the day. This may be normal on some days but is worth noting.

## Channel Transcripts

{{channels}}

## Response Format

Respond with ONLY valid JSON. No markdown, no explanation, no code fences, just the raw JSON object.

```json
{
  "date": "{{date}}",
  "channels": [
    {
      "channel": "#channel-name",
      "ep_name": "EP Name",
      "status": "FLAG | OK | NO_ACTIVITY",
      "flags": [
        {"type": "missed_item | stalled_progress", "detail": "Specific description of the issue with timestamps"}
      ],
      "summary": "One-sentence summary of channel health"
    }
  ]
}
```

Rules:
- `flags` array should be empty `[]` for OK and NO_ACTIVITY channels
- Be specific — include timestamps, names, and context in flag details
- Only flag genuine issues, not routine back-and-forth
- A channel with normal, healthy communication should be marked OK
- If there are no messages at all, mark as NO_ACTIVITY
