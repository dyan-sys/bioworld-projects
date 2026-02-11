#!/usr/bin/env python3.11
"""Summarize a YouTube playlist using Gemini's native video understanding."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.types import Part

from google.genai.types import HttpOptions

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_DIR = PROJECT_ROOT / "local-data" / "youtube"
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
MODEL = "gemini-2.5-flash"
MAX_RETRIES = 2


def get_default_prompt() -> str:
    prompt_file = TEMPLATE_DIR / "default-prompt.md"
    return prompt_file.read_text().strip()


def extract_playlist(url: str) -> list[dict]:
    """Use yt-dlp to extract video URLs and titles from a playlist or single video."""
    cmd = ["yt-dlp", "--flat-playlist", "-J", url]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"Error extracting playlist: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(result.stdout)

    # Single video (no entries key)
    if "entries" not in data:
        return [{
            "title": data.get("title", "Unknown"),
            "url": data.get("webpage_url") or data.get("url") or url,
            "id": data.get("id", "unknown"),
            "duration": data.get("duration"),
        }]

    videos = []
    for entry in data["entries"]:
        if entry is None:
            continue
        video_id = entry.get("id", "")
        video_url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
        videos.append({
            "title": entry.get("title", "Unknown"),
            "url": video_url,
            "id": video_id,
            "duration": entry.get("duration"),
        })

    return videos


def summarize_video(client: genai.Client, video_url: str, prompt: str, high_res: bool = False) -> str:
    """Send a single video to Gemini for summarization with retry."""
    config_kwargs = {}
    if not high_res:
        config_kwargs["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=[
                    Part.from_uri(file_uri=video_url, mime_type="video/mp4"),
                    prompt,
                ],
                config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
            )
            return response.text
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 5 * (attempt + 1)
                print(f"  Retry {attempt + 1}/{MAX_RETRIES} in {wait}s... ({e})")
                time.sleep(wait)
            else:
                raise


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


def main():
    parser = argparse.ArgumentParser(description="Summarize a YouTube playlist with Gemini")
    parser.add_argument("url", help="YouTube playlist or video URL")
    parser.add_argument("--prompt", "-p", help="Custom summarization prompt (overrides default)")
    parser.add_argument("--high-res", action="store_true", help="Use high resolution (3x cost, more detail)")
    parser.add_argument("--output", "-o", help="Custom output file path")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set in environment", file=sys.stderr)
        sys.exit(1)

    prompt = args.prompt or get_default_prompt()

    # Extract playlist
    print(f"Extracting videos from: {args.url}")
    videos = extract_playlist(args.url)
    print(f"Found {len(videos)} video(s)")

    if not videos:
        print("No videos found.", file=sys.stderr)
        sys.exit(1)

    # Init Gemini client (5 min timeout for long videos)
    client = genai.Client(
        api_key=api_key,
        http_options=HttpOptions(timeout=300_000),
    )

    # Summarize each video
    summaries = []
    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] Summarizing: {video['title']} ({format_duration(video['duration'])})")
        try:
            summary = summarize_video(client, video["url"], prompt, args.high_res)
            summaries.append({"video": video, "summary": summary})
            print(f"  Done.")
        except Exception as e:
            error_msg = str(e)
            print(f"  Error: {error_msg}", file=sys.stderr)
            summaries.append({"video": video, "summary": f"*Error summarizing this video: {error_msg}*"})

        # Brief pause between requests to be respectful of rate limits
        if i < len(videos):
            time.sleep(2)

    # Compile output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.output:
        output_path = Path(args.output)
    else:
        # Use playlist title or video title for filename
        safe_name = videos[0]["title"][:50].replace("/", "-").replace(" ", "-").lower()
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_")
        output_path = OUTPUT_DIR / f"{safe_name}_{timestamp}.md"

    lines = []
    lines.append(f"# YouTube Playlist Summary")
    lines.append(f"")
    lines.append(f"**Source:** {args.url}")
    lines.append(f"**Videos:** {len(videos)}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if args.prompt:
        lines.append(f"**Custom prompt:** {args.prompt}")
    lines.append(f"**Resolution:** {'high' if args.high_res else 'low'}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    for i, item in enumerate(summaries, 1):
        video = item["video"]
        lines.append(f"## {i}. {video['title']}")
        lines.append(f"")
        lines.append(f"**URL:** {video['url']}  ")
        lines.append(f"**Duration:** {format_duration(video['duration'])}")
        lines.append(f"")
        lines.append(item["summary"])
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    # Cross-video synthesis for playlists with multiple videos
    if len(summaries) > 1:
        print(f"\nGenerating cross-video synthesis...")
        all_summaries = "\n\n".join(
            f"Video: {s['video']['title']}\n{s['summary']}"
            for s in summaries if not s["summary"].startswith("*Error")
        )
        try:
            synthesis = client.models.generate_content(
                model=MODEL,
                contents=f"""Here are summaries of {len(summaries)} videos from the same playlist:

{all_summaries}

Provide a brief synthesis across all videos:
1. **Common themes** — What topics or ideas appear repeatedly?
2. **Key contradictions** — Do any videos disagree with each other?
3. **Top 5 takeaways** — The most important insights from the entire playlist, ranked by impact.""",
            )
            lines.append(f"## Cross-Video Synthesis")
            lines.append(f"")
            lines.append(synthesis.text)
            lines.append(f"")
        except Exception as e:
            print(f"  Synthesis error: {e}", file=sys.stderr)

    output_path.write_text("\n".join(lines))
    print(f"\nOutput saved to: {output_path}")


if __name__ == "__main__":
    main()
