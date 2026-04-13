"""
Scene Extraction Module
Extracts key frames/screenshots from videos using FFmpeg scene detection.
"""

import os
import subprocess
import json


def get_video_duration(video_path: str) -> float:
    """Get the duration of a video in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path
        ],
        capture_output=True,
        text=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def extract_scenes(video_path: str, output_dir: str, method: str = "interval", interval: float = 2.0, threshold: float = 0.3) -> list:
    """
    Extract scene screenshots from a video.

    Args:
        video_path: Path to source video
        output_dir: Directory to save screenshots
        method: 'interval' (every N seconds) or 'scene_detect' (on scene changes)
        interval: Seconds between frames (for interval method)
        threshold: Scene change sensitivity 0-1 (for scene_detect method)

    Returns:
        List of dicts with keys: path, timestamp, scene_index
    """
    scenes_dir = os.path.join(output_dir, "scenes")
    os.makedirs(scenes_dir, exist_ok=True)

    if method == "scene_detect":
        return _extract_by_scene_detection(video_path, scenes_dir, threshold)
    else:
        return _extract_by_interval(video_path, scenes_dir, interval)


def _extract_by_interval(video_path: str, scenes_dir: str, interval: float) -> list:
    """Extract a frame every N seconds."""
    duration = get_video_duration(video_path)

    output_pattern = os.path.join(scenes_dir, "scene_%04d.jpg")

    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            output_pattern, "-y"
        ],
        capture_output=True,
        check=True,
    )

    scenes = []
    idx = 1
    timestamp = 0.0
    while timestamp < duration:
        filename = f"scene_{idx:04d}.jpg"
        filepath = os.path.join(scenes_dir, filename)
        if os.path.exists(filepath):
            scenes.append({
                "path": filepath,
                "filename": filename,
                "timestamp": round(timestamp, 2),
                "scene_index": idx,
            })
        idx += 1
        timestamp += interval

    return scenes


def _extract_by_scene_detection(video_path: str, scenes_dir: str, threshold: float) -> list:
    """Extract frames at scene change boundaries."""
    # First pass: detect scene changes and get timestamps
    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-vsync", "vfr",
            "-f", "null", "-"
        ],
        capture_output=True,
        text=True,
    )

    # Extract timestamps from showinfo output
    timestamps = [0.0]  # Always include the first frame
    for line in result.stderr.split("\n"):
        if "pts_time:" in line:
            try:
                pts_part = line.split("pts_time:")[1].split()[0]
                ts = float(pts_part)
                timestamps.append(round(ts, 2))
            except (ValueError, IndexError):
                continue

    # Extract frames at detected timestamps
    scenes = []
    for idx, ts in enumerate(timestamps, 1):
        filename = f"scene_{idx:04d}.jpg"
        filepath = os.path.join(scenes_dir, filename)

        subprocess.run(
            [
                "ffmpeg", "-ss", str(ts),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                filepath, "-y"
            ],
            capture_output=True,
        )

        if os.path.exists(filepath):
            scenes.append({
                "path": filepath,
                "filename": filename,
                "timestamp": ts,
                "scene_index": idx,
            })

    return scenes


def get_scene_with_transcript(scenes: list, transcript_segments: list) -> list:
    """Match scenes with their corresponding transcript segments."""
    enriched_scenes = []

    for scene in scenes:
        scene_start = scene["timestamp"]
        # Find the next scene's timestamp or use a large value
        scene_end = scene_start + 5.0  # Default 5 second window

        matching_text = []
        for seg in transcript_segments:
            if seg["start"] <= scene_start + 5.0 and seg["end"] >= scene_start - 0.5:
                matching_text.append(seg["text"])

        enriched_scenes.append({
            **scene,
            "transcript": " ".join(matching_text) if matching_text else "(No speech)",
        })

    return enriched_scenes
