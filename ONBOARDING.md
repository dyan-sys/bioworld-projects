# Onboarding to Ally OS

Welcome! You don't need to know how to code. Claude Code handles that — you just tell it what you want in plain English.

## 1. Create Accounts

Before anything else, you need two accounts:

- **GitHub** — go to [github.com](https://github.com/signup) and create a free account. Share your username with the Ally team so you can be added as a collaborator on the repo.
- **Claude** — go to [claude.ai](https://claude.ai) and create an account. You need a **Pro plan** (or access to a team workspace) to use Claude Code. You'll log in via the browser the first time you run it.

Wait until you've been added as a collaborator before continuing to step 3.

## 2. Install Tools

**Git**

*Mac:* Open Terminal (search "Terminal" in Spotlight) and run:

```bash
xcode-select --install
```

Click "Install" when prompted. This gives you Git and other command-line tools.

*Windows:* Download and install from [git-scm.com](https://git-scm.com/download/win). Use the default options during installation. This also gives you Git Bash, a terminal you can use for the rest of this guide.

**Node.js**

Download the **LTS** version from [nodejs.org](https://nodejs.org) and install it. This is needed to run Claude Code.

**Claude Code**

In Terminal, run:

```bash
npm install -g @anthropic-ai/claude-code
```

**VS Code** (recommended but optional)

Download from [code.visualstudio.com](https://code.visualstudio.com). Gives you a nice editor with a built-in terminal.

## 3. Clone the Repo

```bash
cd ~/Documents
git clone git@github.com:withally/ally-os.git
cd ally-os
```

If git clone fails with a permission error, you may need to set up an SSH key. Try running `gh auth login` and follow the prompts, then clone again.

## 4. Set Up Your Environment

Copy the template and fill in the API keys shared with you by the Ally team:

```bash
cp .env.template .env
```

Open `.env` in any text editor and paste in the values. You only need the keys for the skills you'll be working on — leave the rest blank.

**Important:** Never commit the `.env` file. It contains secrets and is already gitignored.

## 5. Start Claude Code

You're ready. Open Terminal, go to the project folder, and type:

```bash
cd ~/Documents/ally-os
claude
```

### First things to try

Run the setup check to make sure everything is configured correctly:

```
/first-time-setup
```

Then get oriented:

```
Give me a rundown of this project
```

Claude will explain what Ally OS does, what skills are available, and how things fit together. Take a minute to read through it.

### Now try something

Pick one that matches your comfort level:

**Just looking around** — nothing changes, you're just reading:
```
What does the invite-candidates skill do? Walk me through it.
```

**Run something** — executes a read-only skill with real output:
```
Check the recruitment pipeline status
```

**Make a change** — Claude edits a file and shows you the diff before saving:
```
Update the email template in invite-candidates to include our office address: 123 Main St
```

When you're happy with a change, Claude can help you submit it for Ivan to review.

## The Golden Rules

1. **Never work directly on `main`.** Always create a branch. (Claude Code can do this for you.)
2. **One branch per task.** Keep changes focused.
3. **Open a pull request** when you're done. Ivan reviews and merges.

You don't need to memorize git commands. Just tell Claude Code what you want:
- *"Create a branch for my changes"*
- *"Commit this and open a PR"*

## Tips

- Be specific about which skill you're working on.
- If Claude Code asks to run a command, read what it says before approving.
- If something goes wrong, say *"undo that"* — Claude Code can revert changes.
- When in doubt, just ask. Claude Code knows this codebase.

## Skills Reference

Each skill lives in `.claude/skills/` and has its own `SKILL.md` with full documentation.

| Skill | What it does |
|-------|-------------|
| `screen-resume` | Scores candidates against job-specific rubrics |
| `update-job-posts` | Creates Notion job post pages per platform |
| `check-recruit-status` | Generates pipeline reports |
| `invite-candidates` | Drafts Gmail invitations for R1 interviews |
| `track-recruitment-events` | Tracks async completions and Calendly bookings |
| `flag-ep-issues` | Reviews EP Slack channels, flags missed items |
| `linkedin-content` | Generates LinkedIn post drafts |
| `recruit-consulting` | Reviews client JDs and interview templates |
| `background-check` | Screens candidates' online presence |
| `track-ai-spend` | Parses billing emails, updates Notion spend DB |

## Staying Updated

Before starting any new work, pull the latest changes:

```bash
git pull
```

## Getting Help

- Ask Claude Code first — it can explain any file, skill, or process.
- Message the Ally team on Slack.
