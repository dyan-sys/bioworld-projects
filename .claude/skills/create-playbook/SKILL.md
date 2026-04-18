---
name: create-playbook
description: Trigger when user mentions creating a playbook, internal dashboard, SOP hub, or team wiki page
---

# Create Playbook Skill

Generates a fully styled internal HTML playbook dashboard — branded to Ally, with dark galactic background, glassmorphism cards, Lucide icons, Netlify Identity login, and shareable/internal SOP access control.

Each playbook is a self-contained folder of HTML files deployable to Netlify for free.

## Trigger phrases

| What you say | What it does |
|---|---|
| "Create a playbook for [team]" | Builds a new branded playbook from scratch |
| "Add a section to the playbook" | Adds a new section card + SOPs to an existing playbook |
| "Add an SOP to [section]" | Adds a new SOP card + modal to an existing playbook |
| "Make [SOP name] external" | Converts an internal SOP to a standalone shareable page |
| "Deploy the playbook" | Guides through Netlify deploy + Identity setup |

## What gets generated

```
local-data/[playbook-name]/
├── index.html              ← Main dashboard (login-gated)
├── _redirects              ← Netlify Identity redirect rule
├── ally-logo.jpeg          ← Copied from Desktop/Ally/
└── [sop-name].html         ← One file per External SOP
```

## Information to collect before building

Ask the user for:

1. **Playbook name** — e.g. "Finance Playbook", "Recruiting Playbook"
2. **Sections** — department groupings (e.g. People Ops, Finance, CS)
3. **SOPs per section** — list of SOP titles
4. **Access per SOP** — Internal (modal) or External (standalone page)
5. **Quick Links** — 2–4 links to show at the bottom (Slack channels, forms, tools)

## Design system (do not change)

All playbooks use the Ally brand. These values are fixed:

| Element | Value |
|---|---|
| Background | `#0e0e10` near-black |
| Primary font | Inter (body), DM Serif Display (headings) |
| Logo | "ally" lowercase bold, cream `#f0ece4` |
| Accent | Purple `#9b6dff` |
| Pink glow | `rgba(255,14,90,0.72)` center blob |
| Purple glow | `rgba(120,50,220,0.4)` side blob |
| Stars | 120 dots, pseudo-random placement |
| Cards | `rgba(255,255,255,0.06)` glass surface |
| Header | `rgba(14,14,16,0.7)` frosted glass |
| Icons | Lucide SVG, `stroke-width: 1.75` |

## Section color classes

Each section gets a color class. Use in order:

| Order | Class | Use for |
|---|---|---|
| 1 | `slate` | Standards, Documentation |
| 2 | `amber` | Recruitment, Hiring |
| 3 | `purple` | People Ops, HR |
| 4 | `blue` | Client, CS |
| 5 | `green` | Finance, Payments |
| 6 | `pink` | Brand, Creative |

## SOP card pattern

**Internal SOP** (opens modal on same page):
```html
<div class="sop-item" onclick="openModal('sop-id')">
  <i data-lucide="icon-name" class="sop-icon"></i>
  <span class="sop-label">SOP Title</span>
  <div class="sop-footer">
    <div class="sop-dot [color]"></div>
    <span class="access-tag internal">Internal</span>
  </div>
</div>
```

**External SOP** (opens standalone page in new tab):
```html
<div class="sop-item" onclick="window.open('sop-slug.html','_blank')">
  <i data-lucide="icon-name" class="sop-icon"></i>
  <span class="sop-label">SOP Title</span>
  <div class="sop-footer">
    <div class="sop-dot [color]"></div>
    <span class="access-tag external">
      <svg width="9" height="9" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
      External
    </span>
  </div>
</div>
```

## Modal pattern (Internal SOPs)

```html
<div class="modal-overlay" id="modal-sop-id">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-header-left">
        <div class="modal-icon [color]"><i data-lucide="icon-name" style="width:22px;height:22px;stroke-width:1.5;"></i></div>
        <div>
          <div class="modal-title">SOP Title</div>
          <div class="modal-category">Section Name</div>
        </div>
      </div>
      <button class="modal-close" onclick="closeModal('sop-id')">✕</button>
    </div>
    <div class="modal-body">
      <h3>Overview</h3>
      <p>What this SOP covers.</p>
      <h3>Steps</h3>
      <ol class="step-list">
        <li>Step one.</li>
        <li>Step two.</li>
      </ol>
      <h3>Notes</h3>
      <div class="info-box">Edge cases and exceptions here.</div>
    </div>
  </div>
</div>
```

## External SOP standalone page pattern

Copy `templates/external-sop.html`, replace these placeholders:
- `{{SOP_TITLE}}` — e.g. "How to File a Leave"
- `{{SECTION_NAME}}` — e.g. "People Ops"
- `{{DESCRIPTION}}` — one-line description for the doc header
- `{{OWNER}}` — e.g. "People Ops team"
- `{{CONTENT}}` — full SOP body (overview, steps, notes)

## Netlify deploy steps (Phase 2)

Tell the user:
1. Go to netlify.com → sign in with Google
2. Add new site → Deploy manually → drag the playbook folder
3. Site Settings → Identity → Enable Identity
4. Registration → set to **Invite only**
5. Identity → External providers → add **Google** (requires Google OAuth app)
6. Invite users → paste team member emails
7. Done — share the `.netlify.app` URL

## Base template location

`.claude/skills/create-playbook/templates/playbook-template.html`

Always start from this template. Never copy a previously built playbook directly — use the template and customise from there.
