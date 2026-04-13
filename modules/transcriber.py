"""
Audio Transcription Module
Transcribes spoken words from video using OpenAI Whisper.
"""

import os
import subprocess
import whisper


def extract_audio(video_path: str, output_dir: str) -> str:
    """Extract audio track from video file."""
    audio_path = os.path.join(output_dir, "audio.wav")
    subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            audio_path, "-y"
        ],
        capture_output=True,
        check=True,
    )
    return audio_path


def transcribe_video(video_path: str, output_dir: str, model_size: str = "base") -> dict:
    """
    Transcribe all spoken words from the video.

    Args:
        video_path: Path to the video file
        output_dir: Directory to store temp files
        model_size: Whisper model size (tiny, base, small, medium, large)

    Returns:
        dict with keys: full_text, segments (list of {start, end, text})
    """
    audio_path = extract_audio(video_path, output_dir)

    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path, verbose=False)

    segments = []
    for seg in result.get("segments", []):
        segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip(),
        })

    # Clean up audio file
    if os.path.exists(audio_path):
        os.remove(audio_path)

    return {
        "full_text": result.get("text", "").strip(),
        "segments": segments,
        "language": result.get("language", "unknown"),
    }


def generate_srt(segments: list, output_path: str) -> str:
    """Generate an SRT subtitle file from transcription segments."""
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = _format_timestamp(seg["start"])
            end = _format_timestamp(seg["end"])
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{seg['text']}\n\n")
    return output_path


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
