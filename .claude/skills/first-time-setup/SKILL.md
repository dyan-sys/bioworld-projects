---
name: first-time-setup
description: Run when a new team member needs to set up their environment, or when something isn't working and they need to troubleshoot their setup
user_invocable: true
---

# First-Time Setup

Checks and installs everything a new team member needs to work on Ally OS with Claude Code. Safe to run multiple times — it skips anything already installed.

## Workflow

### 1. Check what's already installed

Run these checks and collect results:

```bash
# Git
git --version 2>/dev/null

# Node.js
node --version 2>/dev/null

# Claude Code
claude --version 2>/dev/null

# Python 3.11
python3.11 --version 2>/dev/null

# GitHub CLI
gh --version 2>/dev/null

# GitHub auth status
gh auth status 2>/dev/null
```

### 2. Install missing tools

For each missing tool, walk the user through installation. Ask before installing anything.

**Git (via Xcode Command Line Tools):**
```bash
xcode-select --install
```

**Node.js:** Direct the user to download LTS from https://nodejs.org — needed for Claude Code.

**Claude Code:**
```bash
npm install -g @anthropic-ai/claude-code
```

**GitHub CLI:**
```bash
brew install gh
```
If Homebrew isn't installed, direct them to https://brew.sh first.

**Python 3.11:** Direct to https://www.python.org/downloads/ — needed for some skills.

### 3. GitHub authentication

If `gh auth status` fails:
```bash
gh auth login
```
Walk them through the browser-based flow.

### 4. Environment file

Check if `.env` exists:
```bash
test -f .env && echo "exists" || echo "missing"
```

If missing, create from template:
```bash
cp .env.template .env
```

Tell the user: *"Ask Ivan for the API keys you need for your skills. Open `.env` in any text editor and paste them in. You only need the keys for skills you'll be working on — leave the rest blank."*

### 5. Git config

Check if git user is configured:
```bash
git config user.name
git config user.email
```

If not set, ask the user for their name and email, then:
```bash
git config user.name "Their Name"
git config user.email "their@email.com"
```

### 6. Summary

Print a checklist of what's ready and what still needs attention:

```
Setup status:
  [x] Git
  [x] Node.js
  [x] Claude Code
  [x] GitHub CLI
  [x] GitHub authenticated
  [x] Python 3.11
  [x] .env file
  [x] Git user configured

You're all set! Try: "Give me a rundown of this project"
```

If anything is still missing, explain what's needed and offer to help fix it.
