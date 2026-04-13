"""
Video Downloader Module
Downloads videos from YouTube, TikTok, and other platforms using yt-dlp.
"""

import os
import uuid
import yt_dlp


def download_video(url: str, output_dir: str) -> dict:
    """
    Download a video from the given URL.

    Returns:
        dict with keys: video_path, title, duration, thumbnail
    """
    video_id = uuid.uuid4().hex[:10]
    output_template = os.path.join(output_dir, f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "subtitleslangs": ["en", "de", "auto"],
        "writeautomaticsub": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        # Find the downloaded file
        video_path = None
        for ext in ["mp4", "mkv", "webm"]:
            candidate = os.path.join(output_dir, f"{video_id}.{ext}")
            if os.path.exists(candidate):
                video_path = candidate
                break

        if not video_path:
            # Fallback: find any file matching our ID
            for f in os.listdir(output_dir):
                if f.startswith(video_id) and not f.endswith(".vtt") and not f.endswith(".srt"):
                    video_path = os.path.join(output_dir, f)
                    break

        if not video_path:
            raise FileNotFoundError("Downloaded video file not found")

        return {
            "video_path": video_path,
            "video_id": video_id,
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "description": info.get("description", ""),
            "uploader": info.get("uploader", "Unknown"),
        }
