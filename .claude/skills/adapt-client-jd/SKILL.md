# Adapt Client JD Skill

## Overview

Adapts improved client job descriptions into platform-specific formats (OnlineJobs.ph, Jobstreet) for posting. Claude reads the client's improved JD, applies platform-specific transformation rules from format guides, and uses Ally's own job post templates as structural references.

This is a **process documentation skill** — Claude does the work interactively, guided by format guides and reference templates. No Python workflows.

## When to Use

**Trigger phrases:**
- "Adapt the JD for {client}"
- "Generate job posts for {client}"
- "Create OLJ/Jobstreet version of the {client} JD"
- "Format the {client} JD for {platform}"

**Prerequisites:**
- Client workspace exists at `local-data/client-consulting/{client-slug}/jd/`
- An improved JD exists (typically `improved.md` from the recruit-consulting skill)

## Quick Start

```bash
# 1. Ensure client workspace exists with an improved JD
ls local-data/client-consulting/{client-slug}/jd/improved.md

# 2. Ask Claude: "Adapt the JD for {client-slug} to OLJ and Jobstreet"

# 3. Claude will:
#    - Read the source JD
#    - Read platform format guide(s) + Ally reference templates
#    - Apply custom instructions (if any)
#    - Generate platform-specific version(s)
#    - Save to client workspace

# 4. Review output at:
#    local-data/client-consulting/{client-slug}/jd/improved-olj-v1.md
#    local-data/client-consulting/{client-slug}/jd/improved-jobstreet-v1.md
```

## Process

### Step 1: Identify Source JD

Read the source JD from the client workspace. Default is `improved.md`, but the user can point to any file (e.g., `improved-v2.md`, `original.md`).

```
local-data/client-consulting/{client-slug}/jd/improved.md
```

### Step 2: Ask Which Platforms

Ask which platforms to generate for. Supported platforms:

| Key | Platform | Status |
|-----|----------|--------|
| `olj` | OnlineJobs.ph | Supported |
| `jobstreet` | Jobstreet | Supported |

### Step 3: Ask for Custom Instructions (Optional)

The user can provide per-generation instructions that layer on top of the format guide rules. Examples:
- "Remove the Loom video requirement from the application steps"
- "Emphasize remote benefits"
- "Add Mandarin as a nice-to-have"
- "Tone down the hook — make it more professional"
- "Use PHP salary range instead of USD"

If no custom instructions, proceed with standard transformation rules.

### Step 4: Generate Platform Versions

For each requested platform:

1. Read the platform format guide from `templates/`
2. Read Ally's reference templates (listed in `platform-registry.json`)
3. Transform the source JD following the format guide rules
4. Apply any custom instructions from Step 3
5. Save to the client workspace

### Step 5: Verify Output

After generating:
- Compare output to source JD — ensure no content was lost or materially changed
- Confirm platform-specific structural rules were applied (headings, dividers, application section, etc.)
- Check that the tone and voice match the source JD, not Ally's internal templates

## Output Files

Files are saved to the client's JD directory with version numbering:

```
local-data/client-consulting/{client-slug}/jd/
├── improved.md                   # Source (from recruit-consulting)
├── improved-olj-v1.md            # First OLJ adaptation
├── improved-olj-v2.md            # Revised OLJ (if iterated)
├── improved-jobstreet-v1.md      # First Jobstreet adaptation
└── improved-jobstreet-v2.md      # Revised Jobstreet (if iterated)
```

If the user iterates ("tweak the hook", "remove that bullet"), increment the version number and save as a new file.

## Supported Platforms

| Platform | Format Guide | Reference Templates |
|----------|-------------|-------------------|
| OnlineJobs.ph | `olj-format-guide.md` | EP-OLJ.md |
| Jobstreet | `jobstreet-format-guide.md` | EP-Jobstreet.md, EPP-Jobstreet.md |

## Adding New Platforms

To support a new job platform:

1. Study 2-3 existing posts on the platform to identify structural patterns
2. Create `templates/{platform}-format-guide.md` describing the format rules
3. Add entry to `templates/platform-registry.json` with format guide path and any reference templates
4. Update this SKILL.md with the new platform in the tables above

No code changes needed — Claude reads the registry and format guides dynamically.

## Integration

This skill is the **downstream step** after `recruit-consulting`:

```
recruit-consulting          adapt-client-jd
─────────────────           ───────────────
original.md                 improved.md (input)
  → analysis.json             → improved-olj-v1.md
  → improved.md               → improved-jobstreet-v1.md
```

**Upstream:** `recruit-consulting` — Analyzes and improves the client's original JD
**This skill:** Adapts the improved JD to platform-specific formats for posting

## Important Notes

- **Content fidelity:** The platform adaptation should preserve the client's content and voice. Use Ally's templates for *structural* reference only — don't inject Ally-specific messaging (company description, benefits) into client JDs.
- **Format guides are rules, not templates:** They describe structural conventions and transformation rules. Claude applies judgment to map the client's specific content into the platform format.
- **Custom instructions override defaults:** If the user says "skip the Loom video step", that takes priority over what the format guide says about the application section.

## Requirements

- No special dependencies (uses Claude Code directly)
- No API keys required
- Files stored locally in `local-data/client-consulting/`
