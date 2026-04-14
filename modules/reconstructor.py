"""
Video Reconstruction Module
Rebuilds the video from scenes with optional subtitles using FFmpeg.
"""

import os
import subprocess
import json


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


def _get_clip_duration(video_path: str) -> float:
    """Get the duration of a video clip in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def _build_scale_filter(target_w: int, target_h: int, fill: bool = False) -> str:
    """
    Build an FFmpeg scale+pad filter string.

    fill=False: Letterbox (fit inside, black bars)
    fill=True:  Center-crop (fill entire frame, crop overflow) - best for TikTok
    """
    if fill:
        return (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h},setsar=1"
        )
    else:
        return (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )


def _normalize_clip(input_path: str, output_path: str, width: int, height: int,
                    target_duration: float = None, fill: bool = False) -> str:
    """
    Re-encode a clip to match the target resolution, framerate, and codec.
    If target_duration is set and clip is shorter, the last frame is frozen.
    If clip is longer, it is trimmed.
    """
    scale_filter = _build_scale_filter(width, height, fill=fill)

    # Check actual clip duration to decide strategy
    clip_dur = _get_clip_duration(input_path)

    if target_duration is not None and clip_dur < target_duration:
        # Clip is shorter than scene: use tpad to freeze last frame
        pad_dur = target_duration - clip_dur
        vf = f"{scale_filter},tpad=stop_mode=clone:stop_duration={pad_dur:.3f}"
        cmd = [
            "ffmpeg", "-i", input_path,
            "-vf", vf,
            "-t", str(target_duration),
            "-c:v", "libx264", "-an",
            "-r", "30", "-pix_fmt", "yuv420p",
            output_path, "-y"
        ]
    else:
        cmd = ["ffmpeg", "-i", input_path]
        if target_duration is not None:
            cmd += ["-t", str(target_duration)]
        cmd += [
            "-vf", scale_filter,
            "-c:v", "libx264", "-an",
            "-r", "30", "-pix_fmt", "yuv420p",
            output_path, "-y"
        ]

    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


EXPORT_PRESETS = {
    "original": {"fill": False},
    "tiktok": {"width": 1080, "height": 1920, "fill": True},
    "tiktok_hd": {"width": 1080, "height": 1920, "fill": True},
    "youtube": {"width": 1920, "height": 1080, "fill": False},
    "youtube_short": {"width": 1080, "height": 1920, "fill": True},
    "instagram": {"width": 1080, "height": 1080, "fill": True},
    "instagram_reel": {"width": 1080, "height": 1920, "fill": True},
}


def reconstruct_with_custom_clips(video_path: str, scenes: list, output_dir: str,
                                  custom_clips: dict = None, export_preset: str = "original",
                                  crop_filter: str = "", keep_original_audio: bool = True) -> str:
    """
    Reconstruct a video, replacing specific scenes with user-uploaded custom clips.

    The structure and timing of the original video is preserved.
    Custom clips are trimmed/extended to match the original scene duration.
    When keep_original_audio is True, the original video's full audio track
    (music, beats, effects) is used instead of audio from individual clips.
    """
    if custom_clips is None:
        custom_clips = {}

    output_path = os.path.join(output_dir, "reconstructed.mp4")

    # Determine target resolution and fill mode
    preset = EXPORT_PRESETS.get(export_preset, EXPORT_PRESETS["original"])
    fill_mode = preset.get("fill", False)
    if "width" in preset:
        target_w, target_h = preset["width"], preset["height"]
    else:
        orig_w, orig_h = _get_video_resolution(video_path)
        target_w, target_h = orig_w, orig_h

    scale_filter = _build_scale_filter(target_w, target_h, fill=fill_mode)

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
            # Use the custom clip, matched to original scene duration
            _normalize_clip(
                custom_clips[scene_idx], clip_path,
                target_w, target_h,
                target_duration=seg["duration"],
                fill=fill_mode,
            )
        else:
            # Cut from original video (video-only)
            vf_parts = []
            if crop_filter:
                vf_parts.append(f"crop={crop_filter}")
            vf_parts.append(scale_filter)
            vf = ",".join(vf_parts)

            cmd = [
                "ffmpeg", "-ss", str(seg["start"]),
                "-i", video_path,
                "-t", str(seg["duration"]),
                "-vf", vf,
                "-c:v", "libx264", "-an",
                "-r", "30", "-pix_fmt", "yuv420p",
                "-avoid_negative_ts", "make_zero",
                clip_path, "-y"
            ]
            subprocess.run(cmd, capture_output=True, check=True)

        temp_clips.append(clip_path)

    # Write concat list
    with open(concat_file, "w") as f:
        for clip in temp_clips:
            f.write(f"file '{clip}'\n")

    # Concatenate all video clips (video-only)
    video_only_path = os.path.join(output_dir, "reconstructed_video_only.mp4")
    subprocess.run(
        [
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            video_only_path, "-y"
        ],
        capture_output=True,
        check=True,
    )

    if keep_original_audio:
        # Extract original audio track to a separate file first
        audio_path = os.path.join(output_dir, "original_audio.aac")
        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vn", "-c:a", "aac", "-b:a", "192k",
                audio_path, "-y"
            ],
            capture_output=True,
            check=True,
        )

        # Merge: use video duration, loop/pad audio if needed
        subprocess.run(
            [
                "ffmpeg",
                "-i", video_only_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                output_path, "-y"
            ],
            capture_output=True,
            check=True,
        )

        if os.path.exists(audio_path):
            os.remove(audio_path)
    else:
        os.rename(video_only_path, output_path)
        video_only_path = None

    # Clean up temp files
    for clip in temp_clips:
        if os.path.exists(clip):
            os.remove(clip)
    if os.path.exists(concat_file):
        os.remove(concat_file)
    if video_only_path and os.path.exists(video_only_path):
        os.remove(video_only_path)

    return output_path


def add_subtitles_to_video(video_path: str, srt_path: str, output_path: str, style: str = "default") -> str:
    """Burn subtitles into a video file."""
    style_map = {
        "default": "FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2",
        "bold": "FontSize=28,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=3",
        "outline": "FontSize=26,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,Outline=4,Shadow=2",
    }

    subtitle_style = style_map.get(style, style_map["default"])
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


def create_final_video(video_path: str, output_dir: str, srt_path: str = None,
                       include_subtitles: bool = False, subtitle_style: str = "default") -> str:
    """
    Create the final downloadable video.
    Strips all metadata from the output to avoid leaking source information.
    """
    if include_subtitles and srt_path and os.path.exists(srt_path):
        final_path = os.path.join(output_dir, "final_with_subtitles.mp4")
        add_subtitles_to_video(video_path, srt_path, final_path, subtitle_style)
    else:
        final_path = os.path.join(output_dir, "final.mp4")
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

    # Strip all metadata from final output (no source info leaking)
    clean_path = os.path.join(output_dir, "final_clean.mp4")
    subprocess.run(
        [
            "ffmpeg", "-i", final_path,
            "-map_metadata", "-1",
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-c", "copy",
            clean_path, "-y"
        ],
        capture_output=True,
        check=True,
    )
    os.replace(clean_path, final_path)

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
