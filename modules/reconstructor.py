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


def reconstruct_from_original(video_path: str, scenes: list, output_dir: str, include_audio: bool = True) -> str:
    """
    Reconstruct a video by cutting and reassembling scenes from the original.

    This creates a copy of the video with the same scenes,
    maintaining original quality.
    """
    output_path = os.path.join(output_dir, "reconstructed.mp4")

    # Build filter complex for scene concatenation
    segments = []
    filter_parts = []
    concat_inputs = []

    for i, scene in enumerate(scenes):
        start = scene["timestamp"]
        # Calculate duration until next scene
        if i + 1 < len(scenes):
            duration = scenes[i + 1]["timestamp"] - start
        else:
            # Last scene: get remaining duration
            duration = _get_remaining_duration(video_path, start)

        if duration <= 0:
            duration = 2.0

        segments.append({"start": start, "duration": duration})

    # Use concat demuxer approach for clean cuts
    concat_file = os.path.join(output_dir, "concat_list.txt")
    temp_clips = []

    for i, seg in enumerate(segments):
        clip_path = os.path.join(output_dir, f"clip_{i:04d}.mp4")
        temp_clips.append(clip_path)

        cmd = [
            "ffmpeg", "-ss", str(seg["start"]),
            "-i", video_path,
            "-t", str(seg["duration"]),
            "-c:v", "libx264", "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            clip_path, "-y"
        ]
        subprocess.run(cmd, capture_output=True, check=True)

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
