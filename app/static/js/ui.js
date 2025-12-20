// UI and popup management

function showDownloadPopup(data) {
    const popup = document.getElementById('download-popup');
    const overlay = document.getElementById('popup-overlay');
    const thumbnail = document.getElementById('popup-thumbnail');
    const streamType = document.getElementById('popup-stream-type');
    const filename = document.getElementById('popup-filename');

    // Set data
    if (data.thumbnail) {
        thumbnail.src = 'data:image/png;base64,' + data.thumbnail;
    }

    if (data.latest_stream) {
        streamType.textContent = data.latest_stream.type;
    }

    if (data.download) {
        filename.textContent = data.download.output_path;
    }

    // Show popup
    popup.classList.add('active');
    overlay.classList.add('active');

    // DEBUG MODE: Countdown timer disabled
    // startCountdown();
}

// Start countdown (DISABLED FOR DEBUGGING)
function startCountdown() {
    // AppState.countdownValue = 15;
    // updateCountdown();
    // AppState.countdownInterval = setInterval(() => {
    //     AppState.countdownValue--;
    //     updateCountdown();
    //     if (AppState.countdownValue <= 0) {
    //         clearInterval(AppState.countdownInterval);
    //         closePopup();
    //         closeBrowser();
    //     }
    // }, 1000);
}

// Update countdown display
function updateCountdown() {
    const countdown = document.getElementById('popup-countdown');
    countdown.innerHTML = `Download in progress - browser will stay open`;
}

// Close popup
function closePopup() {
    const popup = document.getElementById('download-popup');
    const overlay = document.getElementById('popup-overlay');

    popup.classList.remove('active');
    overlay.classList.remove('active');

    if (AppState.countdownInterval) {
        clearInterval(AppState.countdownInterval);
    }
}

// Keep browser open
function keepOpen() {
    if (AppState.countdownInterval) {
        clearInterval(AppState.countdownInterval);
    }
    closePopup();

    const statusBox = document.getElementById('browser-status');
    showStatus(statusBox, 'Browser kept open. Close manually when done.', 'success');
}

// Show resolution selection popup
function showResolutionPopup(resolutions) {
    const popup = document.getElementById('resolution-popup');
    const overlay = document.getElementById('popup-overlay');
    const optionsContainer = document.getElementById('resolution-options');

    // Clear existing options
    optionsContainer.innerHTML = '';

    // Add resolution buttons with detailed info
    resolutions.forEach(res => {
        const card = document.createElement('div');
        card.style.cssText = 'background: #1e1e30; padding: 15px; border-radius: 8px; margin-bottom: 10px; cursor: pointer; border: 2px solid #4a4a6a; transition: all 0.2s;';
        card.onmouseover = () => card.style.borderColor = '#7e8ce0';
        card.onmouseout = () => card.style.borderColor = '#4a4a6a';
        card.onclick = () => selectResolution(res);

        const title = document.createElement('h4');
        title.style.cssText = 'margin: 0 0 8px 0; color: #7e8ce0; font-size: 1.1rem;';
        title.textContent = res.name || 'Unknown';

        const details = document.createElement('div');
        details.style.cssText = 'font-size: 0.9rem; color: #b8b8d1;';

        const resolution = res.resolution || 'Unknown';
        const framerate = res.framerate ? Math.round(parseFloat(res.framerate)) + ' fps' : 'Unknown';

        details.innerHTML = `
            <p style="margin: 4px 0;"><strong>Resolution:</strong> ${resolution}</p>
            <p style="margin: 4px 0;"><strong>Framerate:</strong> ${framerate}</p>
            <p style="margin: 4px 0; font-size: 0.75rem; word-break: break-all;"><strong>URL:</strong> ${res.url.substring(0, 80)}...</p>
        `;

        card.appendChild(title);
        card.appendChild(details);
        optionsContainer.appendChild(card);
    });

    // Show popup
    popup.classList.add('active');
    overlay.classList.add('active');
}

// Select a resolution
async function selectResolution(stream) {
    closeResolutionPopup();

    const statusBox = document.getElementById('browser-status');
    showStatus(statusBox, `✓ Starting download for ${stream.name}...`, 'success');

    try {
        const response = await fetch('/api/browser/select-resolution', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                browser_id: AppState.currentBrowserId,
                stream: stream
            })
        });

        const data = await response.json();
        if (!data.success) {
            showStatus(statusBox, `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showStatus(statusBox, `Error: ${error.message}`, 'error');
    }
}

// Close resolution popup
function closeResolutionPopup() {
    const popup = document.getElementById('resolution-popup');
    const overlay = document.getElementById('popup-overlay');

    popup.classList.remove('active');
    overlay.classList.remove('active');
}

// Show debug popup
function showDebugPopup() {
    const popup = document.getElementById('debug-popup');
    const overlay = document.getElementById('popup-overlay');

    popup.classList.add('active');
    overlay.classList.add('active');
}

// Update debug log with stream information
function updateDebugLog(resolutions) {
    const timestamp = new Date().toISOString();
    let newContent = `\n=== STREAM DETECTION UPDATE @ ${timestamp} ===\n`;
    newContent += `Total Streams Detected: ${resolutions.length}\n\n`;

    resolutions.forEach((res, index) => {
        newContent += `--- Stream ${index + 1} ---\n`;
        newContent += `Name: ${res.name || 'Unknown'}\n`;
        newContent += `Resolution: ${res.resolution || 'Unknown'}\n`;
        newContent += `Framerate: ${res.framerate || 'Unknown'}\n`;
        newContent += `Codecs: ${res.codecs || 'Unknown'}\n`;
        newContent += `URL: ${res.url}\n`;
        newContent += `\n`;
    });

    // Append to existing content
    AppState.debugLogContent += newContent;

    // Update textarea
    const textarea = document.getElementById('debug-log');
    textarea.value = AppState.debugLogContent;

    // Auto-scroll to bottom
    textarea.scrollTop = textarea.scrollHeight;
}

// Copy debug log to clipboard
function copyDebugLog() {
    const textarea = document.getElementById('debug-log');
    textarea.select();
    document.execCommand('copy');

    // Show feedback
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = '✓ Copied!';
    setTimeout(() => {
        btn.innerHTML = originalText;
    }, 2000);
}

// Close debug popup
function closeDebugPopup() {
    const popup = document.getElementById('debug-popup');
    const overlay = document.getElementById('popup-overlay');

    popup.classList.remove('active');
    overlay.classList.remove('active');
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

    let infoHTML = `
        <h4 style="margin: 0 0 10px 0; color: #7e8ce0;">${name}</h4>
        <p style="margin: 4px 0;"><strong>Resolution:</strong> ${resolution}</p>
        <p style="margin: 4px 0;"><strong>Framerate:</strong> ${framerate}</p>
    `;

    // Add thumbnail if available
    if (thumbnail) {
        infoHTML = `<img src="data:image/png;base64,${thumbnail}" style="width: 100%; border-radius: 8px; margin-bottom: 10px;" />` + infoHTML;
    }

    infoContainer.innerHTML = infoHTML;

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
                const item = document.createElement('div');
                item.style.cssText = 'background: #1e1e30; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 2px solid #4a4a6a;';

                const sizeMB = (download.size / (1024 * 1024)).toFixed(2);
                const minutes = Math.floor(download.duration / 60);
                const seconds = download.duration % 60;
                const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                const statusIcon = download.is_running ? '⏬' : '✓';
                const statusText = download.is_running ? 'Downloading...' : 'Completed';

                item.innerHTML = `
                    <div style="display: flex; gap: 15px; align-items: center;">
                        ${download.thumbnail ? `
                            <div style="flex-shrink: 0;">
                                <img src="data:image/png;base64,${download.thumbnail}"
                                     style="width: 160px; height: 90px; object-fit: cover; border-radius: 8px; border: 2px solid #667eea;"
                                     alt="Video preview">
                            </div>
                        ` : ''}
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 8px 0; color: #7e8ce0;">${statusIcon} ${download.filename}</h4>
                            <p style="margin: 4px 0; color: #b8b8d1; font-size: 0.9rem;"><strong>Resolution:</strong> ${download.resolution}</p>
                            <p style="margin: 4px 0; color: #b8b8d1; font-size: 0.9rem;"><strong>Size:</strong> ${sizeMB} MB &nbsp;&nbsp; <strong>Duration:</strong> ${timeStr}</p>
                            <p style="margin: 4px 0; color: #b8b8d1; font-size: 0.9rem;"><strong>Status:</strong> ${statusText}</p>
                        </div>
                        <div style="flex-shrink: 0;">
                            ${download.is_running ? `<button class="btn btn-secondary" onclick="stopDownload('${download.browser_id}', this)" style="background: #dc3545;">⏹ Stop</button>` : ''}
                        </div>
                    </div>
                `;

                container.appendChild(item);
            });
        } else {
            container.innerHTML = '<p style="color: #b8b8d1; padding: 20px;">No active downloads</p>';
        }
    } catch (error) {
        console.error('Load downloads error:', error);
    }
}

async function stopDownload(browserId, buttonElement) {
    try {
        // Show deleting state
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
                const item = document.createElement('div');
                item.style.cssText = 'background: #1e1e30; padding: 15px; border-radius: 8px; margin-bottom: 10px; border: 2px solid #4a4a6a;';
                item.id = `completed-${download.filename}`;

                const sizeMB = (download.size / (1024 * 1024)).toFixed(2);
                const minutes = Math.floor(download.duration / 60);
                const seconds = download.duration % 60;
                const timeStr = download.duration > 0 ? `${minutes}:${seconds.toString().padStart(2, '0')}` : 'Unknown';
                const resolutionStr = download.framerate ? `${download.resolution}@${download.framerate}` : download.resolution;

                item.innerHTML = `
                    <div style="display: flex; gap: 15px; align-items: center;">
                        ${download.thumbnail ? `
                            <div style="flex-shrink: 0;">
                                <img src="data:image/jpeg;base64,${download.thumbnail}"
                                     style="width: 160px; height: 90px; object-fit: cover; border-radius: 8px; border: 2px solid #28a745;"
                                     alt="Video preview">
                            </div>
                        ` : `
                            <div style="flex-shrink: 0; width: 160px; height: 90px; background: linear-gradient(135deg, #3d3d5c 0%, #4a4a6a 100%); border-radius: 8px; display: flex; align-items: center; justify-content: center; color: #b8b8d1; font-size: 32px;">
                                🎬
                            </div>
                        `}
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 8px 0; color: #28a745;">✓ ${download.filename}</h4>
                            <p style="margin: 4px 0; color: #b8b8d1; font-size: 0.9rem;"><strong>Resolution:</strong> ${resolutionStr}</p>
                            <p style="margin: 4px 0; color: #b8b8d1; font-size: 0.9rem;"><strong>Size:</strong> ${sizeMB} MB &nbsp;&nbsp; <strong>Duration:</strong> ${timeStr}</p>
                        </div>
                        <div style="flex-shrink: 0;">
                            <button class="btn btn-secondary" onclick="deleteDownload('${download.filename}', this)" style="background: #dc3545;">🗑 Delete</button>
                        </div>
                    </div>
                `;

                container.appendChild(item);
            });
        } else {
            container.innerHTML = '<p style="color: #b8b8d1; padding: 20px;">No completed downloads</p>';
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
// Store timeout IDs for each status element

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

        card.innerHTML = `
            <div class="stream-thumbnail">
                ${stream.thumbnail ?
                `<img src="${stream.thumbnail}" alt="${stream.name}">` :
                '🎬'
            }
            </div>
            <div class="stream-details">
                <h3>${stream.name}</h3>
                <div class="stream-detail-row">
                    <span class="stream-detail-label">Resolution:</span>
                    <span>${stream.resolution || 'Unknown'}</span>
                </div>
                <div class="stream-detail-row">
                    <span class="stream-detail-label">Framerate:</span>
                    <span>${framerate}</span>
                </div>
                <div class="stream-detail-row">
                    <span class="stream-detail-label">Codec:</span>
                    <span>${stream.codecs || 'Unknown'}</span>
                </div>
            </div>
            <button class="stream-download-btn" onclick='downloadStream(${JSON.stringify(stream)})'>
                📥 Download This Stream
            </button>
        `;

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

// Schedules
