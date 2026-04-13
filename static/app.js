// Video Copy Tool - Frontend Logic

let projectId = null;
let selectedScenes = new Set();

// --- Helpers ---

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
            <p><strong>Titel:</strong> ${result.title}</p>
            <p><strong>Dauer:</strong> ${formatTime(result.duration)}</p>
            <p><strong>Uploader:</strong> ${result.uploader}</p>
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
                <span class="segment-text">${seg.text}</span>
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

function downloadSRT() {
    if (projectId) {
        window.location.href = `/api/download-srt/${projectId}`;
    }
}

// --- Step 3: Scene Extraction ---

function toggleExtractionOptions() {
    const method = document.getElementById('extraction-method').value;
    document.getElementById('interval-option').classList.toggle('hidden', method !== 'interval');
    document.getElementById('threshold-option').classList.toggle('hidden', method !== 'scene_detect');
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

    const method = document.getElementById('extraction-method').value;
    const interval = document.getElementById('interval-value').value;
    const threshold = document.getElementById('threshold-value').value;

    showStatus('extract-status', 'Szenen werden extrahiert...', 'loading');
    document.getElementById('scenes-grid').classList.add('hidden');

    try {
        const result = await apiCall('/api/extract-scenes', {
            project_id: projectId,
            method,
            interval: parseFloat(interval),
            threshold: parseFloat(threshold),
        });

        showStatus('extract-status', `${result.total_scenes} Szenen erfolgreich extrahiert!`, 'success');

        // Render scene cards
        document.getElementById('scene-count').textContent = result.total_scenes;
        const container = document.getElementById('scenes-container');
        container.innerHTML = '';
        selectedScenes.clear();

        result.scenes.forEach(scene => {
            selectedScenes.add(scene.scene_index);

            const card = document.createElement('div');
            card.className = 'scene-card selected';
            card.dataset.index = scene.scene_index;
            card.onclick = () => toggleScene(card, scene.scene_index);
            card.innerHTML = `
                <div class="scene-check">✓</div>
                <img src="${scene.image_url}" alt="Szene ${scene.scene_index}" loading="lazy">
                <div class="scene-info">
                    <div class="scene-time">⏱ ${formatTimestamp(scene.timestamp)}</div>
                    <div class="scene-transcript">${scene.transcript || '(Kein Text)'}</div>
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

    showStatus('reconstruct-status', 'Video wird rekonstruiert... Das kann bei längeren Videos etwas dauern.', 'loading');
    document.getElementById('download-section').classList.add('hidden');

    try {
        const result = await apiCall('/api/reconstruct', {
            project_id: projectId,
            include_subtitles: includeSubtitles,
            subtitle_style: subtitleStyle,
            selected_scenes: Array.from(selectedScenes),
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

// --- Allow Enter key in URL input ---
document.getElementById('video-url').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        downloadVideo();
    }
});
