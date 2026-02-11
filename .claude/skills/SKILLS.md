# Ally OS Skills

Available skills for Claude Code in this project.

| Skill | Description |
|-------|-------------|
| [screen-resume](./screen-resume/SKILL.md) | Score candidate resumes against the Executive Partner rubric using Kimi or Claude. Writes results to Notion. |
| [update-job-posts](./update-job-posts/SKILL.md) | Create job post pages in the Job Posts DB for Open openings, one per Post Channel with platform-specific templates. |
| [check-recruit-status](./check-recruit-status/SKILL.md) | Check recruitment pipeline status: pipeline overview, status breakdown, screening backlog, and quality distribution. |
| [invite-candidates](./invite-candidates/SKILL.md) | Create Gmail draft R1 invite emails routed by Screener status (Live/Async). Config-driven via R1-invite-mapping.json. Never sends — drafts only. |
| [flag-ep-issues](./flag-ep-issues/SKILL.md) | Daily review of EP Slack channels. Reads yesterday's messages, analyzes via Kimi AI, flags missed items and stalled progress. Posts to #ally-jarvis. |
| [linkedin-content](./linkedin-content/SKILL.md) | Generate LinkedIn post drafts. Combines user creative direction with Kimi web research and Ally's voice/strategy. Outputs draft .md files for human review. |
| [mac-status](./mac-status/SKILL.md) | Quick Mac health diagnostic — memory pressure, swap, disk, top CPU/memory processes, and Ally scheduled job status. |
