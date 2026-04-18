---
name: Invoice Portal — Break Scenarios reminder
description: User wants to revisit invoice portal break scenarios next time they ask
type: project
---

When user asks about "break scenarios", revisit the invoice portal vulnerabilities:

1. OAuth token expiry (highest risk)
2. EP Profiles sheet column rename/reorder
3. Invoice Submissions sheet column rename/reorder
4. Drive folder deleted/permissions revoked
5. Monthly subfolder doesn't exist yet (graceful fallback already in place)
6. Two simultaneous submissions (duplicate rows)
7. Very long description text (PDF overflow)
8. New contractor email not in EP Profiles (blank form, no contractor code)

**Why:** User said "circle back on this the next time I ask about break scenarios" — do not bring it up proactively, wait for them to ask.
