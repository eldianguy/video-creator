"""
Video Reconstruction Module
Rebuilds the video from scenes with optional subtitles using FFmpeg.
"""

import os
import subprocess
import json


def create_scene_video(image_path: str, duration: float, output_path: str, resolution: str = "1920x1080") -> str:
    """Create a video clip from a single image."""
    width, height = resolution.split("x")
    subprocess.run(
        [
            "ffmpeg", "-loop", "1",
            "-i", image_path,
            "-t", str(duration),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            output_path, "-y"
        ],
        capture_output=True,
        check=True,
    )
    return output_path


def _get_video_resolution(video_path: str) -> tuple:
    """Get width and height of a video."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "v:0",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return int(stream["width"]), int(stream["height"])


def _normalize_clip(input_path: str, output_path: str, width: int, height: int) -> str:
    """Re-encode a clip to match the target resolution, framerate, and codec."""
    subprocess.run(
        [
            "ffmpeg", "-i", input_path,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-c:a", "aac",
            "-ar", "44100", "-ac", "2",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            output_path, "-y"
        ],
        capture_output=True,
        check=True,
    )
    return output_path


def reconstruct_with_custom_clips(video_path: str, scenes: list, output_dir: str, custom_clips: dict = None) -> str:
    """
    Reconstruct a video, replacing specific scenes with user-uploaded custom clips.

    The structure and timing of the original video is preserved.
    Custom clips are re-encoded to match the original video's resolution
    so transitions stay seamless.

    Args:
        video_path: Path to the original downloaded video
        scenes: List of scene dicts with timestamp, scene_index
        output_dir: Working directory
        custom_clips: Dict mapping scene_index (int) -> custom clip file path
    """
    if custom_clips is None:
        custom_clips = {}

    output_path = os.path.join(output_dir, "reconstructed.mp4")

    # Get original video resolution for normalizing custom clips
    orig_w, orig_h = _get_video_resolution(video_path)

    # Build segments with duration info
    segments = []
    for i, scene in enumerate(scenes):
        start = scene["timestamp"]
        if i + 1 < len(scenes):
            duration = scenes[i + 1]["timestamp"] - start
        else:
            duration = _get_remaining_duration(video_path, start)
        if duration <= 0:
            duration = 2.0

        segments.append({
            "start": start,
            "duration": duration,
            "scene_index": scene["scene_index"],
        })

    concat_file = os.path.join(output_dir, "concat_list.txt")
    temp_clips = []

    for i, seg in enumerate(segments):
        clip_path = os.path.join(output_dir, f"clip_{i:04d}.mp4")
        scene_idx = seg["scene_index"]

        if scene_idx in custom_clips and os.path.exists(custom_clips[scene_idx]):
            # Use the custom clip, normalized to match original resolution
            _normalize_clip(custom_clips[scene_idx], clip_path, orig_w, orig_h)
        else:
            # Cut from original video
            cmd = [
                "ffmpeg", "-ss", str(seg["start"]),
                "-i", video_path,
                "-t", str(seg["duration"]),
                "-c:v", "libx264", "-c:a", "aac",
                "-avoid_negative_ts", "make_zero",
                clip_path, "-y"
            ]
            subprocess.run(cmd, capture_output=True, check=True)

        temp_clips.append(clip_path)

    # Write concat list
    with open(concat_file, "w") as f:
        for clip in temp_clips:
            f.write(f"file '{clip}'\n")

    # Concatenate all clips
    subprocess.run(
        [
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            output_path, "-y"
        ],
        capture_output=True,
        check=True,
    )

    # Clean up temp clips
    for clip in temp_clips:
        if os.path.exists(clip):
            os.remove(clip)
    if os.path.exists(concat_file):
        os.remove(concat_file)

    return output_path


def add_subtitles_to_video(video_path: str, srt_path: str, output_path: str, style: str = "default") -> str:
    """
    Burn subtitles into a video file.

    Args:
        video_path: Source video
        srt_path: SRT subtitle file
        output_path: Output video path
        style: Subtitle style ('default', 'bold', 'outline')
    """
    style_map = {
        "default": "FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2",
        "bold": "FontSize=28,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=3",
        "outline": "FontSize=26,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,Outline=4,Shadow=2",
    }

    subtitle_style = style_map.get(style, style_map["default"])

    # Escape special characters in path for FFmpeg filter
    escaped_srt = srt_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vf", f"subtitles='{escaped_srt}':force_style='{subtitle_style}'",
            "-c:v", "libx264",
            "-c:a", "copy",
            "-preset", "fast",
            output_path, "-y"
        ],
        capture_output=True,
        check=True,
    )

    return output_path


def create_final_video(video_path: str, output_dir: str, srt_path: str = None, include_subtitles: bool = False, subtitle_style: str = "default") -> str:
    """
    Create the final downloadable video.

    If subtitles are requested and an SRT file exists, burn them into the video.
    Otherwise, just copy the reconstructed video.
    """
    if include_subtitles and srt_path and os.path.exists(srt_path):
        final_path = os.path.join(output_dir, "final_with_subtitles.mp4")
        return add_subtitles_to_video(video_path, srt_path, final_path, subtitle_style)
    else:
        final_path = os.path.join(output_dir, "final.mp4")
        # Just re-encode for consistent output
        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-c:v", "libx264", "-c:a", "aac",
                "-preset", "fast",
                final_path, "-y"
            ],
            capture_output=True,
            check=True,
        )
        return final_path


def _get_remaining_duration(video_path: str, start_time: float) -> float:
    """Get remaining video duration from a given start time."""
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
    total = float(info["format"]["duration"])
    return max(total - start_time, 0.5)
