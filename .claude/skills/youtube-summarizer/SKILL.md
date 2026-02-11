---
name: youtube-summarizer
description: Trigger when user mentions summarizing YouTube videos, extracting insights from playlists, or YouTube content analysis
---

# YouTube Playlist Summarizer

Summarizes all videos in a YouTube playlist using Gemini's native video understanding. No transcript extraction needed — Gemini processes the videos directly.

## How to Run

```bash
# Basic usage
python3.11 .claude/skills/youtube-summarizer/workflows/summarize_playlist.py \
  "https://www.youtube.com/playlist?list=PLxxx"

# With custom prompt
python3.11 .claude/skills/youtube-summarizer/workflows/summarize_playlist.py \
  "https://www.youtube.com/playlist?list=PLxxx" \
  --prompt "Extract key actionable insights for a recruiting startup"

# Single video
python3.11 .claude/skills/youtube-summarizer/workflows/summarize_playlist.py \
  "https://www.youtube.com/watch?v=VIDEO_ID"

# High resolution (more detail, 3x cost)
python3.11 .claude/skills/youtube-summarizer/workflows/summarize_playlist.py \
  "https://www.youtube.com/playlist?list=PLxxx" --high-res
```

## Output

Generates a markdown file in `local-data/youtube/` with:
- Playlist title and metadata
- Per-video sections with title, URL, and summary
- Cross-video synthesis at the end

## Requirements

- Python 3.11+
- `google-genai`, `yt-dlp`, `python-dotenv`
- Environment variable: `GEMINI_API_KEY`
- Only works with **public** YouTube videos

## Cost

- ~$0.02 per 10-min video (low resolution, default)
- ~$0.06 per 10-min video (high resolution)
- Free tier: ~1,000 requests/day
