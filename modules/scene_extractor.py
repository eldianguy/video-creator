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


def auto_crop_detect(video_path: str) -> str:
    """
    Detect screen recording borders/black bars automatically.
    Returns an FFmpeg crop filter string, or empty string if no crop needed.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-t", "30",
            "-vf", "cropdetect=24:16:0",
            "-f", "null", "-"
        ],
        capture_output=True,
        text=True,
    )

    # Parse the last cropdetect line (most stable after a few seconds)
    crop_filter = ""
    for line in result.stderr.split("\n"):
        if "crop=" in line:
            try:
                crop_filter = line.split("crop=")[1].split()[0]
            except IndexError:
                continue

    return crop_filter


def extract_scenes(video_path: str, output_dir: str, method: str = "interval",
                   interval: float = 2.0, threshold: float = 0.3,
                   min_scene_duration: float = 0.0,
                   auto_crop: bool = False) -> list:
    """
    Extract scene screenshots from a video.

    Args:
        video_path: Path to source video
        output_dir: Directory to save screenshots
        method: 'interval' (every N seconds) or 'scene_detect' (on scene changes)
        interval: Seconds between frames (for interval method)
        threshold: Scene change sensitivity 0-1 (for scene_detect method)
        min_scene_duration: Minimum seconds between detected scenes (filters duplicates)
        auto_crop: Automatically detect and remove screen recording borders

    Returns:
        List of dicts with keys: path, timestamp, scene_index
    """
    scenes_dir = os.path.join(output_dir, "scenes")
    os.makedirs(scenes_dir, exist_ok=True)

    # Detect crop if requested
    crop_filter = ""
    if auto_crop:
        crop_filter = auto_crop_detect(video_path)

    if method == "scene_detect":
        return _extract_by_scene_detection(video_path, scenes_dir, threshold, crop_filter, min_scene_duration)
    else:
        return _extract_by_interval(video_path, scenes_dir, interval, crop_filter)


def _extract_by_interval(video_path: str, scenes_dir: str, interval: float, crop_filter: str = "") -> list:
    """Extract a frame every N seconds."""
    duration = get_video_duration(video_path)

    output_pattern = os.path.join(scenes_dir, "scene_%04d.jpg")

    vf = f"fps=1/{interval}"
    if crop_filter:
        vf = f"crop={crop_filter},{vf}"

    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", vf,
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


def _extract_by_scene_detection(video_path: str, scenes_dir: str, threshold: float,
                                crop_filter: str = "", min_scene_duration: float = 0.0) -> list:
    """Extract frames at scene change boundaries."""
    select_expr = f"select='gt(scene,{threshold})',showinfo"
    if crop_filter:
        select_expr = f"crop={crop_filter},{select_expr}"

    result = subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", select_expr,
            "-vsync", "vfr",
            "-f", "null", "-"
        ],
        capture_output=True,
        text=True,
    )

    # Extract timestamps from showinfo output
    raw_timestamps = [0.0]  # Always include the first frame
    for line in result.stderr.split("\n"):
        if "pts_time:" in line:
            try:
                pts_part = line.split("pts_time:")[1].split()[0]
                ts = float(pts_part)
                raw_timestamps.append(round(ts, 2))
            except (ValueError, IndexError):
                continue

    # Filter out scenes that are too close together (important for fast anime cuts)
    timestamps = [raw_timestamps[0]]
    for ts in raw_timestamps[1:]:
        if ts - timestamps[-1] >= min_scene_duration:
            timestamps.append(ts)

    # Build crop vf for frame extraction
    crop_vf = []
    if crop_filter:
        crop_vf = ["-vf", f"crop={crop_filter}"]

    # Extract frames at detected timestamps
    scenes = []
    for idx, ts in enumerate(timestamps, 1):
        filename = f"scene_{idx:04d}.jpg"
        filepath = os.path.join(scenes_dir, filename)

        cmd = [
            "ffmpeg", "-ss", str(ts),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
        ] + crop_vf + [filepath, "-y"]

        subprocess.run(cmd, capture_output=True)

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
