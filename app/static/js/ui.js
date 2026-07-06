// UI and popup management

// ── DOM helpers ───────────────────────────────────────────────
// All dynamic values (filenames, stream names, URLs) are set via
// textContent/properties, never interpolated into HTML — quotes in a
// filename or a malicious playlist's stream name must not break the UI.

function _el(tag, cssText = '', text = null) {
    const node = document.createElement(tag);
    if (cssText) node.style.cssText = cssText;
    if (text !== null) node.textContent = text;
    return node;
}

function _infoLine(label, value, cssText = 'margin: 4px 0; color: #b8b8d1; font-size: 0.9rem;') {
    const p = _el('p', cssText);
    const strong = document.createElement('strong');
    strong.textContent = `${label}: `;
    p.appendChild(strong);
    p.appendChild(document.createTextNode(value));
    return p;
}

// Show download started popup
function showDownloadStartedPopup(streamMetadata, thumbnail, isDirect = false) {
    const popup = document.getElementById('download-started-popup');
    const overlay = document.getElementById('popup-overlay');
    const infoContainer = document.getElementById('download-info');
    const countdownText = document.getElementById('countdown-text');
    const browserButtons = document.getElementById('browser-buttons');
    const directButtons = document.getElementById('direct-buttons');

    // Force close stream selection modal if open
    closeStreamModal();

    // Populate download info
    const resolution = streamMetadata?.resolution || 'Unknown';
    const framerate = streamMetadata?.framerate ? Math.round(parseFloat(streamMetadata.framerate)) + ' fps' : 'Unknown';
    const name = streamMetadata?.name || 'Video';

    infoContainer.innerHTML = '';

    if (thumbnail) {
        const img = _el('img', 'width: 100%; border-radius: 8px; margin-bottom: 10px;');
        img.src = 'data:image/png;base64,' + thumbnail;
        infoContainer.appendChild(img);
    }

    infoContainer.appendChild(_el('h4', 'margin: 0 0 10px 0; color: #7e8ce0;', name));
    infoContainer.appendChild(_infoLine('Resolution', resolution, 'margin: 4px 0;'));
    infoContainer.appendChild(_infoLine('Framerate', framerate, 'margin: 4px 0;'));

    // Show/hide appropriate elements based on download type
    if (isDirect) {
        // Direct download: just show OK button, no countdown
        countdownText.style.display = 'none';
        browserButtons.style.display = 'none';
        directButtons.style.display = 'flex';
    } else {
        // Browser download: show countdown and browser control buttons
        countdownText.style.display = 'block';
        browserButtons.style.display = 'flex';
        directButtons.style.display = 'none';
        // Start 15 second countdown
        startDownloadCountdown();
    }

    // Show popup
    popup.classList.add('active');
    overlay.classList.add('active');
}

// Start countdown timer
function startDownloadCountdown() {
    AppState.countdownValue = 15;
    const countdownElement = document.getElementById('countdown');
    countdownElement.textContent = AppState.countdownValue;

    if (AppState.countdownInterval) {
        clearInterval(AppState.countdownInterval);
    }

    AppState.countdownInterval = setInterval(() => {
        AppState.countdownValue--;
        countdownElement.textContent = AppState.countdownValue;

        if (AppState.countdownValue <= 0) {
            clearInterval(AppState.countdownInterval);
            closeBrowserNow();
        }
    }, 1000);
}

// Close browser now (from download popup)
async function closeBrowserNow() {
    if (AppState.countdownInterval) {
        clearInterval(AppState.countdownInterval);
    }

    const popup = document.getElementById('download-started-popup');
    const overlay = document.getElementById('popup-overlay');
    popup.classList.remove('active');
    overlay.classList.remove('active');

    await closeBrowser();
}

// Keep browser open (from download popup)
function keepBrowserOpen() {
    if (AppState.countdownInterval) {
        clearInterval(AppState.countdownInterval);
    }

    const popup = document.getElementById('download-started-popup');
    const overlay = document.getElementById('popup-overlay');
    popup.classList.remove('active');
    overlay.classList.remove('active');

    const statusBox = document.getElementById('browser-status');
    showStatus(statusBox, 'Browser kept open. Close manually when done.', 'success');
}

// Close download popup (for direct downloads - no browser to close)
function closeDownloadPopup() {
    const popup = document.getElementById('download-started-popup');
    const overlay = document.getElementById('popup-overlay');
    popup.classList.remove('active');
    overlay.classList.remove('active');
}

// Close browser
async function closeBrowser() {
    if (!AppState.currentBrowserId) return;

    try {
        await fetch(`/api/browser/close/${AppState.currentBrowserId}`, {
            method: 'POST'
        });

        const vncContainer = document.getElementById('vnc-container');
        vncContainer.classList.remove('active');

        AppState.currentBrowserId = null;

        if (AppState.statusCheckInterval) {
            clearInterval(AppState.statusCheckInterval);
        }

        // Reset the button
        const btn = document.getElementById('browser-start-btn');
        btn.disabled = false;
        btn.innerHTML = 'Open Browser & Detect';

        loadDownloads();
    } catch (error) {
        console.error('Close browser error:', error);
    }
}

// Clear cookies and Chrome profile data
async function clearCookies() {
    const statusBox = document.getElementById('browser-status');
    const btn = document.getElementById('clear-cookies-btn');

    // Confirmation dialog
    if (!confirm('This will close all browser sessions and clear all cookies and login data. Continue?')) {
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Clearing...';
    showStatus(statusBox, 'Closing browsers and clearing cookies...', 'error');

    try {
        const response = await fetch('/api/browser/clear-cookies', {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            showStatus(statusBox, '✓ ' + data.message, 'success');

            // Close VNC viewer if open
            const vncContainer = document.getElementById('vnc-container');
            vncContainer.classList.remove('active');
            AppState.currentBrowserId = null;

            if (AppState.statusCheckInterval) {
                clearInterval(AppState.statusCheckInterval);
            }
        } else {
            showStatus(statusBox, `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showStatus(statusBox, `Error: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🗑️ Clear Cookies';
    }
}

// Load downloads list
async function loadDownloads() {
    try {
        const response = await fetch('/api/downloads/active');
        const data = await response.json();

        const container = document.getElementById('active-downloads-container');
        container.innerHTML = '';

        if (data.active_downloads && data.active_downloads.length > 0) {
            data.active_downloads.forEach(download => {
                const item = _el('div', 'background: #1e1e30; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 2px solid #4a4a6a;');

                const sizeMB = (download.size / (1024 * 1024)).toFixed(2);
                const minutes = Math.floor(download.duration / 60);
                const seconds = download.duration % 60;
                const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                const statusIcon = download.is_running ? '⏬' : '✓';
                const statusText = download.is_running ? 'Downloading...' : 'Completed';

                const row = _el('div', 'display: flex; gap: 15px; align-items: center;');

                if (download.thumbnail) {
                    const thumbWrap = _el('div', 'flex-shrink: 0;');
                    const img = _el('img', 'width: 160px; height: 90px; object-fit: cover; border-radius: 8px; border: 2px solid #667eea;');
                    img.src = 'data:image/png;base64,' + download.thumbnail;
                    img.alt = 'Video preview';
                    thumbWrap.appendChild(img);
                    row.appendChild(thumbWrap);
                }

                const info = _el('div', 'flex: 1;');
                info.appendChild(_el('h4', 'margin: 0 0 8px 0; color: #7e8ce0;', `${statusIcon} ${download.filename}`));
                info.appendChild(_infoLine('Resolution', download.resolution));
                info.appendChild(_infoLine('Size', `${sizeMB} MB — Duration: ${timeStr}`));
                info.appendChild(_infoLine('Status', statusText));
                row.appendChild(info);

                const actions = _el('div', 'flex-shrink: 0;');
                if (download.is_running) {
                    const stopBtn = _el('button', 'background: #dc3545;', '⏹ Stop');
                    stopBtn.className = 'btn btn-secondary';
                    stopBtn.addEventListener('click', () => stopDownload(download.browser_id, stopBtn));
                    actions.appendChild(stopBtn);
                }
                row.appendChild(actions);

                item.appendChild(row);
                container.appendChild(item);
            });
        } else {
            container.appendChild(_el('p', 'color: #b8b8d1; padding: 20px;', 'No active downloads'));
        }
    } catch (error) {
        console.error('Load downloads error:', error);
    }
}

async function stopDownload(browserId, buttonElement) {
    try {
        // Show stopping state
        if (buttonElement) {
            buttonElement.disabled = true;
            buttonElement.innerHTML = '<span class="spinner"></span> Stopping...';
        }

        const response = await fetch(`/api/downloads/stop/${browserId}`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            loadDownloads();
        } else {
            // Restore button on failure
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = '⏹ Stop';
            }
        }
    } catch (error) {
        console.error('Stop download error:', error);
        // Restore button on error
        if (buttonElement) {
            buttonElement.disabled = false;
            buttonElement.innerHTML = '⏹ Stop';
        }
    }
}

// Load completed downloads
async function loadCompletedDownloads() {
    try {
        const response = await fetch('/api/downloads/list');
        const data = await response.json();

        const container = document.getElementById('completed-downloads-container');
        container.innerHTML = '';

        if (data.downloads && data.downloads.length > 0) {
            data.downloads.forEach(download => {
                const item = _el('div', 'background: #1e1e30; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 2px solid #4a4a6a;');

                const sizeMB = (download.size / (1024 * 1024)).toFixed(2);
                const minutes = Math.floor(download.duration / 60);
                const seconds = download.duration % 60;
                const timeStr = download.duration > 0 ? `${minutes}:${seconds.toString().padStart(2, '0')}` : 'Unknown';
                const resolutionStr = download.framerate ? `${download.resolution}@${download.framerate}` : download.resolution;

                const row = _el('div', 'display: flex; gap: 15px; align-items: center;');

                if (download.thumbnail) {
                    const thumbWrap = _el('div', 'flex-shrink: 0;');
                    const img = _el('img', 'width: 160px; height: 90px; object-fit: cover; border-radius: 8px; border: 2px solid #28a745;');
                    img.src = 'data:image/jpeg;base64,' + download.thumbnail;
                    img.alt = 'Video preview';
                    thumbWrap.appendChild(img);
                    row.appendChild(thumbWrap);
                } else {
                    row.appendChild(_el('div',
                        'flex-shrink: 0; width: 160px; height: 90px; background: linear-gradient(135deg, #3d3d5c 0%, #4a4a6a 100%); border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #b8b8d1; font-size: 32px;',
                        '🎬'));
                }

                const info = _el('div', 'flex: 1;');
                info.appendChild(_el('h4', 'margin: 0 0 8px 0; color: #28a745;', `✓ ${download.filename}`));
                info.appendChild(_infoLine('Resolution', resolutionStr));
                info.appendChild(_infoLine('Size', `${sizeMB} MB — Duration: ${timeStr}`));
                row.appendChild(info);

                const actions = _el('div', 'flex-shrink: 0;');
                const deleteBtn = _el('button', 'background: #dc3545;', '🗑 Delete');
                deleteBtn.className = 'btn btn-secondary';
                deleteBtn.addEventListener('click', () => deleteDownload(download.filename, deleteBtn));
                actions.appendChild(deleteBtn);
                row.appendChild(actions);

                item.appendChild(row);
                container.appendChild(item);
            });
        } else {
            container.appendChild(_el('p', 'color: #b8b8d1; padding: 20px;', 'No completed downloads'));
        }
    } catch (error) {
        console.error('Load completed downloads error:', error);
    }
}

async function deleteDownload(filename, buttonElement) {
    try {
        // Show deleting state
        if (buttonElement) {
            buttonElement.disabled = true;
            buttonElement.innerHTML = '<span class="spinner"></span> Deleting...';
        }

        const response = await fetch(`/api/downloads/delete/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.success) {
            loadCompletedDownloads();
        } else {
            // Restore button on failure
            if (buttonElement) {
                buttonElement.disabled = false;
                buttonElement.innerHTML = '🗑 Delete';
            }
            alert('Failed to delete: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Delete download error:', error);
        // Restore button on error
        if (buttonElement) {
            buttonElement.disabled = false;
            buttonElement.innerHTML = '🗑 Delete';
        }
    }
}

// Show status message
function showStatus(element, message, type) {
    element.textContent = message;
    element.className = 'status-box active ' + type;
    element.style.display = 'block';  // Explicitly show

    // Clear any existing timeout for this element
    if (AppState.statusTimeouts.has(element)) {
        clearTimeout(AppState.statusTimeouts.get(element));
    }

    // Set 10 second auto-hide timer
    const timeoutId = setTimeout(() => {
        element.classList.remove('active');
        element.style.display = 'none';  // Explicitly hide
        AppState.statusTimeouts.delete(element);
    }, 10000);

    AppState.statusTimeouts.set(element, timeoutId);
}

// Stream selection modal handling

function closeStreamModal() {
    document.getElementById('stream-modal').classList.remove('active');
}

function showStreamModal(streams) {
    const modal = document.getElementById('stream-modal');
    const container = document.getElementById('streams-container');

    // Filter out streams we've already displayed
    const newStreams = streams.filter(stream => {
        const streamId = `${stream.name}-${stream.resolution}-${stream.framerate}`;
        if (AppState.displayedStreams.has(streamId)) {
            return false;
        }
        AppState.displayedStreams.add(streamId);
        return true;
    });

    // If no new streams, don't show modal
    if (newStreams.length === 0) {
        return;
    }

    // Add new streams to the container (append, don't replace)
    newStreams.forEach(stream => {
        const card = document.createElement('div');
        card.className = 'stream-card';

        // Format framerate
        const framerate = stream.framerate ?
            `${stream.framerate} fps` :
            'Unknown';

        const thumb = document.createElement('div');
        thumb.className = 'stream-thumbnail';
        if (stream.thumbnail) {
            const img = document.createElement('img');
            img.src = stream.thumbnail;
            img.alt = stream.name || 'Stream';
            thumb.appendChild(img);
        } else {
            thumb.textContent = '🎬';
        }
        card.appendChild(thumb);

        const details = document.createElement('div');
        details.className = 'stream-details';
        details.appendChild(_el('h3', '', stream.name || 'Unknown'));

        const addRow = (label, value) => {
            const row = document.createElement('div');
            row.className = 'stream-detail-row';
            const labelSpan = document.createElement('span');
            labelSpan.className = 'stream-detail-label';
            labelSpan.textContent = `${label}:`;
            row.appendChild(labelSpan);
            row.appendChild(_el('span', '', value));
            details.appendChild(row);
        };
        addRow('Resolution', stream.resolution || 'Unknown');
        addRow('Framerate', framerate);
        addRow('Codec', stream.codecs || 'Unknown');
        card.appendChild(details);

        const downloadBtn = document.createElement('button');
        downloadBtn.className = 'stream-download-btn';
        downloadBtn.textContent = '📥 Download This Stream';
        downloadBtn.addEventListener('click', () => downloadStream(stream));
        card.appendChild(downloadBtn);

        container.appendChild(card);
    });

    modal.classList.add('active');
}

async function downloadStream(stream) {
    console.log('Downloading stream:', stream);

    try {
        const response = await fetch('/api/browser/select-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                browser_id: AppState.currentBrowserId,
                stream_url: stream.url
            })
        });

        const data = await response.json();

        if (data.success) {
            closeStreamModal();
            const statusBox = document.getElementById('browser-status');
            showStatus(statusBox, `✓ Download started! ${stream.name} (${stream.resolution})`, 'success');
            setTimeout(() => loadDownloads(), 2000);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}
