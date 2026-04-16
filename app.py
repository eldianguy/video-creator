"""
Video Copy Tool - Flask Application
A web tool that analyzes, transcribes, and reconstructs videos from YouTube/TikTok.
"""

import os
import re
import shutil
import subprocess
import time
import uuid
import json
from threading import Thread
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory

from modules.downloader import download_video
from modules.transcriber import transcribe_video, generate_srt
from modules.scene_extractor import extract_scenes, get_scene_with_transcript, auto_crop_detect
from modules.reconstructor import reconstruct_with_custom_clips, create_final_video

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload

WORKSPACE = os.path.join(os.path.dirname(__file__), "workspace")
os.makedirs(WORKSPACE, exist_ok=True)

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
PROJECT_TTL = 24 * 3600  # 24 hours

# Store active projects in memory
projects = {}


def _validate_video_file(video_path: str) -> bool:
    """Check if a file is a valid video with a video stream."""
    try:
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
            timeout=15,
        )
        info = json.loads(result.stdout)
        return len(info.get("streams", [])) > 0
    except Exception:
        return False


def _cleanup_expired_projects():
    """Background thread: remove projects older than PROJECT_TTL."""
    while True:
        time.sleep(3600)  # Check every hour
        now = time.time()
        expired = [
            pid for pid, proj in list(projects.items())
            if now - proj.get("created_at", 0) > PROJECT_TTL
        ]
        for pid in expired:
            project_dir = projects[pid].get("dir", "")
            if project_dir and os.path.exists(project_dir):
                shutil.rmtree(project_dir, ignore_errors=True)
            projects.pop(pid, None)


_cleanup_thread = Thread(target=_cleanup_expired_projects, daemon=True)
_cleanup_thread.start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def api_download():
    """Step 1: Download the video from URL."""
    data = request.get_json()
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "Bitte gib eine Video-URL ein."}), 400

    project_id = uuid.uuid4().hex[:12]
    project_dir = os.path.join(WORKSPACE, project_id)
    os.makedirs(project_dir, exist_ok=True)

    try:
        result = download_video(url, project_dir)
        projects[project_id] = {
            "dir": project_dir,
            "video_path": result["video_path"],
            "title": result["title"],
            "duration": result["duration"],
            "url": url,
            "created_at": time.time(),
        }
        return jsonify({
            "project_id": project_id,
            "title": result["title"],
            "duration": result["duration"],
            "uploader": result["uploader"],
        })
    except Exception as e:
        shutil.rmtree(project_dir, ignore_errors=True)
        return jsonify({"error": f"Download fehlgeschlagen: {str(e)}"}), 500


@app.route("/api/upload-local", methods=["POST"])
def api_upload_local():
    """Step 1 (alt): Upload a local video file (e.g. screen recording)."""
    if "file" not in request.files:
        return jsonify({"error": "Keine Datei hochgeladen."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Keine Datei ausgewählt."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXT:
        return jsonify({"error": f"Nicht unterstütztes Format. Erlaubt: {', '.join(ALLOWED_VIDEO_EXT)}"}), 400

    project_id = uuid.uuid4().hex[:12]
    project_dir = os.path.join(WORKSPACE, project_id)
    os.makedirs(project_dir, exist_ok=True)

    video_path = os.path.join(project_dir, f"source{ext}")
    file.save(video_path)

    # Get video duration via ffprobe
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
            capture_output=True, text=True,
        )
        info = json.loads(result.stdout)
        duration = float(info["format"].get("duration", 0))
    except Exception:
        duration = 0

    title = os.path.splitext(file.filename)[0]
    projects[project_id] = {
        "dir": project_dir,
        "video_path": video_path,
        "title": title,
        "duration": duration,
        "url": f"local://{file.filename}",
        "created_at": time.time(),
    }

    return jsonify({
        "project_id": project_id,
        "title": title,
        "duration": duration,
        "uploader": "Lokale Datei",
    })


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    """Step 2: Transcribe the video audio."""
    data = request.get_json()
    project_id = data.get("project_id")
    model_size = data.get("model_size", "base")

    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]

    try:
        result = transcribe_video(
            project["video_path"],
            project["dir"],
            model_size=model_size,
        )
        project["transcript"] = result
        project["segments"] = result["segments"]

        # Generate SRT file
        srt_path = os.path.join(project["dir"], "subtitles.srt")
        generate_srt(result["segments"], srt_path)
        project["srt_path"] = srt_path

        return jsonify({
            "full_text": result["full_text"],
            "segments": result["segments"],
            "language": result["language"],
            "segment_count": len(result["segments"]),
        })
    except Exception as e:
        return jsonify({"error": f"Transkription fehlgeschlagen: {str(e)}"}), 500


@app.route("/api/extract-scenes", methods=["POST"])
def api_extract_scenes():
    """Step 3: Extract scene screenshots."""
    data = request.get_json()
    project_id = data.get("project_id")
    method = data.get("method", "interval")
    interval = float(data.get("interval", 2.0))
    threshold = float(data.get("threshold", 0.3))
    min_scene_duration = float(data.get("min_scene_duration", 0.0))
    do_auto_crop = data.get("auto_crop", False)

    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]

    try:
        # Auto-crop detection for screen recordings
        if do_auto_crop:
            crop_filter = auto_crop_detect(project["video_path"])
            project["crop_filter"] = crop_filter
        else:
            project["crop_filter"] = ""

        scenes = extract_scenes(
            project["video_path"],
            project["dir"],
            method=method,
            interval=interval,
            threshold=threshold,
            min_scene_duration=min_scene_duration,
            auto_crop=do_auto_crop,
        )

        # Enrich scenes with transcript data if available
        if "segments" in project:
            scenes = get_scene_with_transcript(scenes, project["segments"])

        project["scenes"] = scenes

        # Build response with relative paths for the frontend
        scene_data = []
        for s in scenes:
            scene_data.append({
                "filename": s["filename"],
                "timestamp": s["timestamp"],
                "scene_index": s["scene_index"],
                "transcript": s.get("transcript", ""),
                "image_url": f"/api/scene-image/{project_id}/{s['filename']}",
            })

        return jsonify({
            "scenes": scene_data,
            "total_scenes": len(scene_data),
        })
    except Exception as e:
        return jsonify({"error": f"Szenen-Extraktion fehlgeschlagen: {str(e)}"}), 500


@app.route("/api/scene-image/<project_id>/<filename>")
def api_scene_image(project_id, filename):
    """Serve a scene screenshot image."""
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    # Validate filename to prevent path traversal
    if not re.match(r'^scene_\d{4}\.jpg$', filename):
        return jsonify({"error": "Ungültiger Dateiname."}), 400

    scenes_dir = os.path.join(projects[project_id]["dir"], "scenes")
    return send_from_directory(scenes_dir, filename)


@app.route("/api/upload-clip/<project_id>/<int:scene_index>", methods=["POST"])
def api_upload_clip(project_id, scene_index):
    """Upload a custom video clip to replace a specific scene."""
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    if "file" not in request.files:
        return jsonify({"error": "Keine Datei hochgeladen."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Keine Datei ausgewählt."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXT:
        return jsonify({"error": f"Nicht unterstütztes Format. Erlaubt: {', '.join(ALLOWED_VIDEO_EXT)}"}), 400

    project = projects[project_id]
    custom_dir = os.path.join(project["dir"], "custom_clips")
    os.makedirs(custom_dir, exist_ok=True)

    clip_path = os.path.join(custom_dir, f"custom_{scene_index}{ext}")
    file.save(clip_path)

    # Validate that the file is a real video with a video stream
    if not _validate_video_file(clip_path):
        os.remove(clip_path)
        return jsonify({"error": "Datei ist keine gültige Videodatei oder hat keinen Video-Stream."}), 400

    # Store the custom clip mapping
    if "custom_clips" not in project:
        project["custom_clips"] = {}
    project["custom_clips"][scene_index] = clip_path

    return jsonify({
        "success": True,
        "scene_index": scene_index,
        "filename": file.filename,
        "preview_url": f"/api/custom-clip-preview/{project_id}/{scene_index}",
    })


@app.route("/api/remove-clip/<project_id>/<int:scene_index>", methods=["DELETE"])
def api_remove_clip(project_id, scene_index):
    """Remove a custom clip and revert to the original scene."""
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]
    custom_clips = project.get("custom_clips", {})

    if scene_index in custom_clips:
        clip_path = custom_clips[scene_index]
        if os.path.exists(clip_path):
            os.remove(clip_path)
        del custom_clips[scene_index]

    return jsonify({"success": True, "scene_index": scene_index})


@app.route("/api/custom-clip-preview/<project_id>/<int:scene_index>")
def api_custom_clip_preview(project_id, scene_index):
    """Generate and serve a thumbnail for an uploaded custom clip."""
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]
    custom_clips = project.get("custom_clips", {})

    if scene_index not in custom_clips:
        return jsonify({"error": "Kein eigener Clip für diese Szene."}), 404

    clip_path = custom_clips[scene_index]
    thumb_path = clip_path + ".thumb.jpg"

    if not os.path.exists(thumb_path):
        subprocess.run(
            [
                "ffmpeg", "-i", clip_path,
                "-vframes", "1", "-q:v", "2",
                thumb_path, "-y"
            ],
            capture_output=True,
        )

    if os.path.exists(thumb_path):
        return send_file(thumb_path, mimetype="image/jpeg")
    return jsonify({"error": "Vorschau konnte nicht erstellt werden."}), 500


@app.route("/api/upload-bulk-clips/<project_id>", methods=["POST"])
def api_upload_bulk_clips(project_id):
    """Upload multiple clips at once to replace scenes in order.

    If 'selected_scenes' is provided (JSON array of scene indices),
    clips are mapped only to those scenes in order. Otherwise, clips
    are mapped to all scenes sequentially.
    """
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]
    all_scenes = project.get("scenes", [])
    files = request.files.getlist("files")

    if not files:
        return jsonify({"error": "Keine Dateien hochgeladen."}), 400

    # Use selected scene indices if provided, otherwise all scenes
    selected_raw = request.form.get("selected_scenes", "")
    if selected_raw:
        try:
            selected_indices = set(json.loads(selected_raw))
            target_scenes = [s for s in all_scenes if s["scene_index"] in selected_indices]
        except (json.JSONDecodeError, TypeError):
            target_scenes = all_scenes
    else:
        target_scenes = all_scenes

    custom_dir = os.path.join(project["dir"], "custom_clips")
    os.makedirs(custom_dir, exist_ok=True)

    if "custom_clips" not in project:
        project["custom_clips"] = {}

    assigned = []
    for i, file in enumerate(files):
        if i >= len(target_scenes):
            break

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_VIDEO_EXT:
            continue

        scene_idx = target_scenes[i]["scene_index"]
        clip_path = os.path.join(custom_dir, f"custom_{scene_idx}{ext}")
        file.save(clip_path)
        project["custom_clips"][scene_idx] = clip_path

        # Generate thumbnail
        thumb_path = clip_path + ".thumb.jpg"
        subprocess.run(
            ["ffmpeg", "-i", clip_path, "-vframes", "1", "-q:v", "2", thumb_path, "-y"],
            capture_output=True,
        )

        assigned.append({
            "scene_index": scene_idx,
            "filename": file.filename,
            "preview_url": f"/api/custom-clip-preview/{project_id}/{scene_idx}",
        })

    return jsonify({
        "success": True,
        "assigned_clips": assigned,
        "total_assigned": len(assigned),
    })


@app.route("/api/reconstruct", methods=["POST"])
def api_reconstruct():
    """Step 4: Reconstruct the video."""
    data = request.get_json()
    project_id = data.get("project_id")
    include_subtitles = data.get("include_subtitles", False)
    subtitle_style = data.get("subtitle_style", "default")
    selected_scenes = data.get("selected_scenes", None)
    export_preset = data.get("export_preset", "original")
    keep_original_audio = data.get("keep_original_audio", True)
    encoding_speed = data.get("encoding_speed", "fast")

    # Validate encoding speed preset
    valid_speeds = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"}
    if encoding_speed not in valid_speeds:
        encoding_speed = "fast"

    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]

    try:
        # Use selected scenes or all scenes
        scenes = project.get("scenes", [])
        if selected_scenes is not None:
            scenes = [s for s in scenes if s["scene_index"] in selected_scenes]

        # Get custom clip mappings and crop filter
        custom_clips = project.get("custom_clips", {})
        crop_filter = project.get("crop_filter", "")

        # Reconstruct with custom clips mixed in
        reconstructed_path = reconstruct_with_custom_clips(
            project["video_path"],
            scenes,
            project["dir"],
            custom_clips=custom_clips,
            export_preset=export_preset,
            crop_filter=crop_filter,
            keep_original_audio=keep_original_audio,
            encoding_speed=encoding_speed,
        )

        # Create final video (with optional subtitles)
        srt_path = project.get("srt_path")
        final_path = create_final_video(
            reconstructed_path,
            project["dir"],
            srt_path=srt_path,
            include_subtitles=include_subtitles,
            subtitle_style=subtitle_style,
        )

        project["final_video"] = final_path

        # Get file size
        file_size = os.path.getsize(final_path)

        return jsonify({
            "success": True,
            "download_url": f"/api/download-video/{project_id}",
            "file_size_mb": round(file_size / (1024 * 1024), 2),
        })
    except Exception as e:
        return jsonify({"error": f"Rekonstruktion fehlgeschlagen: {str(e)}"}), 500


@app.route("/api/download-video/<project_id>")
def api_download_video(project_id):
    """Download the final reconstructed video."""
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]
    final_video = project.get("final_video")

    if not final_video or not os.path.exists(final_video):
        return jsonify({"error": "Video noch nicht erstellt."}), 404

    safe_title = "".join(c for c in project["title"] if c.isalnum() or c in " -_").strip()
    filename = f"{safe_title or 'video'}_copy.mp4"

    return send_file(final_video, as_attachment=True, download_name=filename)


@app.route("/api/download-srt/<project_id>")
def api_download_srt(project_id):
    """Download the SRT subtitle file."""
    if project_id not in projects:
        return jsonify({"error": "Projekt nicht gefunden."}), 404

    project = projects[project_id]
    srt_path = project.get("srt_path")

    if not srt_path or not os.path.exists(srt_path):
        return jsonify({"error": "Untertitel nicht vorhanden."}), 404

    return send_file(srt_path, as_attachment=True, download_name="subtitles.srt")


@app.route("/api/cleanup/<project_id>", methods=["DELETE"])
def api_cleanup(project_id):
    """Clean up project files."""
    if project_id in projects:
        project_dir = projects[project_id]["dir"]
        shutil.rmtree(project_dir, ignore_errors=True)
        del projects[project_id]

    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
