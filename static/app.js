// Video Copy Tool - Frontend Logic

let projectId = null;
let selectedScenes = new Set();
let customClips = {};  // scene_index -> { filename, preview_url }

// --- Helpers ---

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showStatus(elementId, message, type) {
    const el = document.getElementById(elementId);
    el.className = `status ${type}`;
    el.classList.remove('hidden');
    if (type === 'loading') {
        el.innerHTML = `<div class="spinner"></div> ${message}`;
    } else {
        const icon = type === 'success' ? '✓' : '✗';
        el.innerHTML = `<strong>${icon}</strong> ${message}`;
    }
}

function hideStatus(elementId) {
    document.getElementById(elementId).classList.add('hidden');
}

function setStepActive(stepNum) {
    document.querySelectorAll('.step').forEach((step, i) => {
        const num = i + 1;
        step.classList.remove('active');
        if (num < stepNum) {
            step.classList.add('completed');
        } else if (num === stepNum) {
            step.classList.add('active');
            step.classList.remove('completed');
        } else {
            step.classList.remove('completed');
        }
    });
}

function showSection(id) {
    document.getElementById(id).classList.remove('hidden');
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatTimestamp(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
        return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m}:${s.toString().padStart(2, '0')}`;
}

async function apiCall(endpoint, data) {
    const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || 'Ein Fehler ist aufgetreten.');
    }
    return result;
}

// --- Step 1: Download ---

async function downloadVideo() {
    const url = document.getElementById('video-url').value.trim();
    if (!url) {
        showStatus('download-status', 'Bitte gib eine Video-URL ein.', 'error');
        return;
    }

    const btn = document.getElementById('btn-download');
    btn.disabled = true;

    showStatus('download-status', 'Video wird heruntergeladen... Das kann einen Moment dauern.', 'loading');
    document.getElementById('video-info').classList.add('hidden');

    try {
        const result = await apiCall('/api/download', { url });
        projectId = result.project_id;

        showStatus('download-status', 'Video erfolgreich heruntergeladen!', 'success');

        const info = document.getElementById('video-info');
        info.innerHTML = `
            <p><strong>Titel:</strong> ${escapeHtml(result.title)}</p>
            <p><strong>Dauer:</strong> ${formatTime(result.duration)}</p>
            <p><strong>Uploader:</strong> ${escapeHtml(result.uploader)}</p>
        `;
        info.classList.remove('hidden');

        // Unlock step 2
        setStepActive(2);
        showSection('step-2');
    } catch (err) {
        showStatus('download-status', err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

// --- Step 1b: Local file upload ---

function updateFileLabel(input) {
    const label = document.getElementById('file-upload-text');
    if (input.files && input.files[0]) {
        label.textContent = input.files[0].name;
    } else {
        label.textContent = 'Lokale Videodatei auswählen...';
    }
}

async function uploadLocalVideo() {
    const input = document.getElementById('local-file-input');
    if (!input.files || !input.files[0]) {
        showStatus('download-status', 'Bitte wähle eine Videodatei aus.', 'error');
        return;
    }

    const btn = document.getElementById('btn-upload-local');
    btn.disabled = true;

    const formData = new FormData();
    formData.append('file', input.files[0]);

    showStatus('download-status', 'Video wird hochgeladen...', 'loading');
    document.getElementById('video-info').classList.add('hidden');

    try {
        const response = await fetch('/api/upload-local', {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Upload fehlgeschlagen.');
        }

        projectId = result.project_id;

        showStatus('download-status', 'Video erfolgreich geladen!', 'success');

        const info = document.getElementById('video-info');
        info.innerHTML = `
            <p><strong>Titel:</strong> ${escapeHtml(result.title)}</p>
            <p><strong>Dauer:</strong> ${formatTime(result.duration)}</p>
            <p><strong>Quelle:</strong> ${escapeHtml(result.uploader)}</p>
        `;
        info.classList.remove('hidden');

        setStepActive(2);
        showSection('step-2');
    } catch (err) {
        showStatus('download-status', err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

// --- Step 2: Transcription ---

async function transcribeVideo() {
    if (!projectId) return;

    const btn = document.getElementById('btn-transcribe');
    btn.disabled = true;

    const modelSize = document.getElementById('whisper-model').value;
    showStatus('transcribe-status', 'Audio wird transkribiert... Bei längeren Videos kann das mehrere Minuten dauern.', 'loading');
    document.getElementById('transcript-result').classList.add('hidden');

    try {
        const result = await apiCall('/api/transcribe', {
            project_id: projectId,
            model_size: modelSize,
        });

        showStatus('transcribe-status', `Transkription abgeschlossen! ${result.segment_count} Segmente erkannt.`, 'success');

        // Show language
        document.getElementById('detected-language').textContent = result.language.toUpperCase();

        // Show full transcript
        document.getElementById('full-transcript').textContent = result.full_text || '(Kein Text erkannt)';

        // Show segments
        const segList = document.getElementById('segments-list');
        segList.innerHTML = '';
        result.segments.forEach(seg => {
            const div = document.createElement('div');
            div.className = 'segment-item';
            div.innerHTML = `
                <span class="segment-time">${formatTimestamp(seg.start)} → ${formatTimestamp(seg.end)}</span>
                <span class="segment-text">${escapeHtml(seg.text)}</span>
            `;
            segList.appendChild(div);
        });

        document.getElementById('transcript-result').classList.remove('hidden');

        // Unlock step 3
        setStepActive(3);
        showSection('step-3');
    } catch (err) {
        showStatus('transcribe-status', err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

function skipTranscription() {
    // Skip transcription and go directly to scene extraction
    setStepActive(3);
    showSection('step-3');
    showStatus('transcribe-status', 'Transkription übersprungen.', 'success');
}

function downloadSRT() {
    if (projectId) {
        window.location.href = `/api/download-srt/${projectId}`;
    }
}

// --- Step 3: Scene Extraction ---

function toggleExtractionOptions() {
    const method = document.getElementById('extraction-method').value;
    const isInterval = method === 'interval';
    const isSceneDetect = method === 'scene_detect';
    const isAnime = method === 'anime';

    document.getElementById('interval-option').classList.toggle('hidden', !isInterval);
    document.getElementById('threshold-option').classList.toggle('hidden', !isSceneDetect);

    // Anime preset auto-configures for fast cuts
    if (isAnime) {
        document.getElementById('threshold-value').value = '0.1';
        document.getElementById('threshold-display').textContent = '0.1';
    }
}

// Threshold display update
document.getElementById('threshold-value').addEventListener('input', function() {
    document.getElementById('threshold-display').textContent = this.value;
});

// Subtitle checkbox toggle
document.getElementById('include-subtitles').addEventListener('change', function() {
    document.getElementById('subtitle-style-option').classList.toggle('hidden', !this.checked);
});

async function extractScenes() {
    if (!projectId) return;

    const btn = document.getElementById('btn-extract');
    btn.disabled = true;

    let method = document.getElementById('extraction-method').value;
    const interval = document.getElementById('interval-value').value;
    const threshold = document.getElementById('threshold-value').value;

    // Anime preset: use scene_detect with optimized settings for fast cuts
    let animeThreshold = parseFloat(threshold);
    let minSceneDuration = 0.0;
    if (method === 'anime') {
        method = 'scene_detect';
        animeThreshold = 0.1;
        minSceneDuration = 0.3;
    }

    showStatus('extract-status', 'Szenen werden extrahiert...', 'loading');
    document.getElementById('scenes-grid').classList.add('hidden');

    try {
        const autoCrop = document.getElementById('auto-crop').checked;

        const result = await apiCall('/api/extract-scenes', {
            project_id: projectId,
            method,
            interval: parseFloat(interval),
            threshold: animeThreshold,
            min_scene_duration: minSceneDuration,
            auto_crop: autoCrop,
        });

        showStatus('extract-status', `${result.total_scenes} Szenen erfolgreich extrahiert!`, 'success');

        // Render scene cards
        document.getElementById('scene-count').textContent = result.total_scenes;
        const container = document.getElementById('scenes-container');
        container.innerHTML = '';
        selectedScenes.clear();

        customClips = {};

        result.scenes.forEach(scene => {
            selectedScenes.add(scene.scene_index);

            const card = document.createElement('div');
            card.className = 'scene-card selected';
            card.dataset.index = scene.scene_index;
            card.id = `scene-card-${scene.scene_index}`;
            card.innerHTML = `
                <div class="scene-check" onclick="toggleScene(this.parentElement, ${scene.scene_index})">✓</div>
                <div class="scene-media" onclick="toggleScene(this.parentElement, ${scene.scene_index})">
                    <img src="${scene.image_url}" alt="Szene ${scene.scene_index}" loading="lazy" id="scene-img-${scene.scene_index}">
                </div>
                <div class="scene-info">
                    <div class="scene-time">⏱ ${formatTimestamp(scene.timestamp)}</div>
                    <div class="scene-transcript">${escapeHtml(scene.transcript || '(Kein Text)')}</div>
                    <div class="scene-actions">
                        <label class="btn-swap" title="Eigenen Clip hochladen">
                            ↑ Ersetzen
                            <input type="file" accept="video/*" class="file-input-hidden"
                                   onchange="uploadCustomClip(${scene.scene_index}, this)">
                        </label>
                        <button class="btn-revert hidden" id="btn-revert-${scene.scene_index}"
                                onclick="removeCustomClip(${scene.scene_index})">
                            ✕ Original
                        </button>
                    </div>
                    <div class="custom-clip-badge hidden" id="badge-${scene.scene_index}">
                        Eigener Clip geladen
                    </div>
                </div>
            `;
            container.appendChild(card);
        });

        document.getElementById('scenes-grid').classList.remove('hidden');

        // Unlock step 4
        setStepActive(4);
        showSection('step-4');
    } catch (err) {
        showStatus('extract-status', err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

function toggleScene(card, index) {
    if (selectedScenes.has(index)) {
        selectedScenes.delete(index);
        card.classList.remove('selected');
    } else {
        selectedScenes.add(index);
        card.classList.add('selected');
    }
}

function selectAllScenes() {
    document.querySelectorAll('.scene-card').forEach(card => {
        const idx = parseInt(card.dataset.index);
        selectedScenes.add(idx);
        card.classList.add('selected');
    });
}

function deselectAllScenes() {
    document.querySelectorAll('.scene-card').forEach(card => {
        const idx = parseInt(card.dataset.index);
        selectedScenes.delete(idx);
        card.classList.remove('selected');
    });
}

// --- Step 4: Reconstruction ---

async function reconstructVideo() {
    if (!projectId) return;

    const btn = document.getElementById('btn-reconstruct');
    btn.disabled = true;

    const includeSubtitles = document.getElementById('include-subtitles').checked;
    const subtitleStyle = document.getElementById('subtitle-style').value;
    const exportPreset = document.getElementById('export-preset').value;
    const keepOriginalAudio = document.getElementById('keep-original-audio').checked;

    showStatus('reconstruct-status', 'Video wird rekonstruiert... Das kann bei längeren Videos etwas dauern.', 'loading');
    document.getElementById('download-section').classList.add('hidden');

    try {
        const result = await apiCall('/api/reconstruct', {
            project_id: projectId,
            include_subtitles: includeSubtitles,
            subtitle_style: subtitleStyle,
            selected_scenes: Array.from(selectedScenes),
            export_preset: exportPreset,
            keep_original_audio: keepOriginalAudio,
        });

        showStatus('reconstruct-status', 'Video erfolgreich erstellt!', 'success');

        document.getElementById('file-size').textContent = result.file_size_mb;
        document.getElementById('download-link').href = result.download_url;
        document.getElementById('download-section').classList.remove('hidden');
    } catch (err) {
        showStatus('reconstruct-status', err.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

// --- Bulk Upload ---

async function uploadBulkClips(input) {
    if (!input.files || input.files.length === 0) return;
    if (!projectId) return;

    const formData = new FormData();
    for (const file of input.files) {
        formData.append('files', file);
    }
    // Send selected scenes so clips map to the correct scenes
    formData.append('selected_scenes', JSON.stringify(Array.from(selectedScenes)));

    showStatus('extract-status', `${input.files.length} Clips werden hochgeladen und zugeordnet...`, 'loading');

    try {
        const response = await fetch(`/api/upload-bulk-clips/${projectId}`, {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Bulk-Upload fehlgeschlagen.');
        }

        // Update UI for each assigned clip
        result.assigned_clips.forEach(clip => {
            const card = document.getElementById(`scene-card-${clip.scene_index}`);
            const badge = document.getElementById(`badge-${clip.scene_index}`);
            const revertBtn = document.getElementById(`btn-revert-${clip.scene_index}`);
            const img = document.getElementById(`scene-img-${clip.scene_index}`);

            if (card && badge && img) {
                customClips[clip.scene_index] = {
                    filename: clip.filename,
                    preview_url: clip.preview_url,
                };
                img.src = clip.preview_url;
                card.classList.add('has-custom-clip');
                badge.textContent = `Eigener Clip: ${clip.filename}`;
                badge.classList.remove('hidden');
                if (revertBtn) revertBtn.classList.remove('hidden');
            }
        });

        showStatus('extract-status',
            `${result.total_assigned} von ${input.files.length} Clips erfolgreich zugeordnet!`, 'success');
    } catch (err) {
        showStatus('extract-status', err.message, 'error');
    }

    input.value = '';
}

// --- Custom Clip Upload/Remove ---

async function uploadCustomClip(sceneIndex, input) {
    if (!input.files || !input.files[0]) return;
    if (!projectId) return;

    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);

    const card = document.getElementById(`scene-card-${sceneIndex}`);
    const badge = document.getElementById(`badge-${sceneIndex}`);
    const revertBtn = document.getElementById(`btn-revert-${sceneIndex}`);
    const img = document.getElementById(`scene-img-${sceneIndex}`);

    badge.textContent = 'Wird hochgeladen...';
    badge.classList.remove('hidden');

    try {
        const response = await fetch(`/api/upload-clip/${projectId}/${sceneIndex}`, {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Upload fehlgeschlagen.');
        }

        customClips[sceneIndex] = {
            filename: result.filename,
            preview_url: result.preview_url,
        };

        // Show custom clip preview thumbnail
        img.src = result.preview_url;
        card.classList.add('has-custom-clip');
        badge.textContent = `Eigener Clip: ${result.filename}`;
        revertBtn.classList.remove('hidden');
    } catch (err) {
        badge.textContent = `Fehler: ${err.message}`;
        badge.classList.add('error-badge');
        setTimeout(() => {
            if (!customClips[sceneIndex]) {
                badge.classList.add('hidden');
                badge.classList.remove('error-badge');
            }
        }, 3000);
    }

    // Reset file input so the same file can be re-selected
    input.value = '';
}

async function removeCustomClip(sceneIndex) {
    if (!projectId) return;

    try {
        await fetch(`/api/remove-clip/${projectId}/${sceneIndex}`, { method: 'DELETE' });
    } catch (e) {
        // Ignore network errors on cleanup
    }

    delete customClips[sceneIndex];

    const card = document.getElementById(`scene-card-${sceneIndex}`);
    const badge = document.getElementById(`badge-${sceneIndex}`);
    const revertBtn = document.getElementById(`btn-revert-${sceneIndex}`);
    const img = document.getElementById(`scene-img-${sceneIndex}`);

    // Restore original scene image
    const originalUrl = img.dataset.originalSrc || img.src;
    // We need to find the original URL — stored as data attribute
    card.classList.remove('has-custom-clip');
    badge.classList.add('hidden');
    revertBtn.classList.add('hidden');

    // Reload original image by rebuilding src
    img.src = `/api/scene-image/${projectId}/scene_${String(sceneIndex).padStart(4, '0')}.jpg`;
}

// --- Allow Enter key in URL input ---
document.getElementById('video-url').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        downloadVideo();
    }
});
