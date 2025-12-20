// Download and browser functionality

// Core functionality: validation, downloads, browser, and UI


// Validate filename doesn't already exist
async function validateFilename(inputId, errorId, format) {
    const input = document.getElementById(inputId);
    const errorDiv = document.getElementById(errorId);
    let filename = input.value.trim();

    if (!filename) {
        input.classList.remove('input-error');
        errorDiv.classList.remove('visible');
        return true; // Empty is valid (will be handled by required check)
    }

    // Auto-append extension if not present
    if (!filename.includes('.')) {
        filename = filename + '.' + format;
    }

    try {
        const response = await fetch(`/api/downloads/check-filename?filename=${encodeURIComponent(filename)}`);
        const data = await response.json();

        if (data.exists) {
            input.classList.add('input-error');
            errorDiv.classList.add('visible');
            return false;
        } else {
            input.classList.remove('input-error');
            errorDiv.classList.remove('visible');
            return true;
        }
    } catch (error) {
        console.error('Filename validation error:', error);
        return true; // Allow on error
    }
}

// Start direct download
async function startDirectDownload() {
    let url = document.getElementById('direct-url').value.trim();
    let filename = document.getElementById('direct-filename').value.trim();
    const format = document.getElementById('direct-format').value;
    const statusBox = document.getElementById('direct-status');
    const btn = document.getElementById('direct-download-btn');

    if (!url) {
        showStatus(statusBox, 'Please enter a stream URL', 'error');
        return;
    }

    // Add https:// if no protocol specified
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }

    // Auto-generate filename if empty
    if (!filename) {
        const timestamp = Date.now();
        filename = `video_${timestamp}.${format}`;
    } else {
        // Check if filename exists (only if user provided one)
        const isValid = await validateFilename('direct-filename', 'direct-filename-error', format);
        if (!isValid) {
            showStatus(statusBox, 'Please choose a different filename - this one already exists', 'error');
            return;
        }

        // Auto-append extension if not present
        if (!filename.includes('.')) {
            filename = filename + '.' + format;
        }
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting download...';

    try {
        const response = await fetch('/api/downloads/direct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, filename })
        });

        const data = await response.json();

        if (data.success) {
            showStatus(statusBox, `✓ Download started! Extracting metadata with ffmpeg...`, 'success');

            // Poll for metadata and thumbnail (ffmpeg extracts these from the stream)
            pollDirectDownloadStatus(data.browser_id);

            setTimeout(() => loadDownloads(), 2000);
        } else {
            showStatus(statusBox, `Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showStatus(statusBox, `Error: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Download Now';
    }
}

// Start browser mode
async function startBrowser() {
    let url = document.getElementById('browser-url').value.trim();
    let filename = document.getElementById('browser-filename').value.trim();
    const format = document.getElementById('browser-format').value;
    const resolution = document.getElementById('preferred-resolution').value;
    const framerate = document.getElementById('preferred-framerate').value;
    const autoDownload = document.getElementById('auto-download').checked;
    const statusBox = document.getElementById('browser-status');
    const btn = document.getElementById('browser-start-btn');

    if (!url) {
        showStatus(statusBox, 'Please enter a webpage URL', 'error');
        return;
    }

    // Add https:// if no protocol specified
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }

    // Check if filename exists (only if filename is provided)
    if (filename) {
        const isValid = await validateFilename('browser-filename', 'browser-filename-error', format);
        if (!isValid) {
            showStatus(statusBox, 'Please choose a different filename - this one already exists', 'error');
            return;
        }
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Starting browser...';

    try {
        const payload = {
            url,
            resolution: resolution,
            framerate: framerate,
            auto_download: autoDownload,
            format: format
        };

        // Only add filename if provided (with auto extension)
        if (filename) {
            if (!filename.includes('.')) {
                filename = filename + '.' + format;
            }
            payload.filename = filename;
        }

        const response = await fetch('/api/browser/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            AppState.currentBrowserId = data.browser_id;
            AppState.downloadPopupShown = false; // Reset for new session
            const resolutionText = framerate === 'any' ? `${resolution} (any framerate)` : `${resolution} ${framerate}fps`;
            const modeText = autoDownload ? 'auto-download enabled' : 'manual selection';
            showStatus(statusBox, `✓ Browser started! Looking for ${resolutionText} (${modeText})...`, 'success');

            // Only show VNC viewer initially if NOT in auto-download mode
            // In auto-download mode, VNC will only show if manual selection is needed
            if (!autoDownload) {
                const vncContainer = document.getElementById('vnc-container');
                const vncFrame = document.getElementById('vnc-frame');

                // Auto-connect to VNC and hide toolbar
                const vncUrl = 'http://' + window.location.hostname + ':6080/vnc.html?autoconnect=true&resize=scale';
                vncFrame.src = vncUrl;
                vncContainer.classList.add('active');

                // Scroll to VNC viewer
                setTimeout(() => {
                    vncContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 500);
            }

            // Update button to show browser is running
            btn.disabled = false;
            btn.innerHTML = '✓ Browser Running';

            // Start status polling
            startStatusPolling();
        } else {
            showStatus(statusBox, `Error: ${data.error}`, 'error');
            btn.disabled = false;
            btn.innerHTML = 'Open Browser & Detect';
        }
    } catch (error) {
        showStatus(statusBox, `Error: ${error.message}`, 'error');
        btn.disabled = false;
        btn.innerHTML = 'Open Browser & Detect';
    }
}

// Poll direct download status (just for metadata and thumbnail, no browser)
async function pollDirectDownloadStatus(browserId) {
    let attempts = 0;
    const maxAttempts = 10; // 10 seconds max

    const checkStatus = async () => {
        try {
            const response = await fetch(`/api/browser/status/${browserId}`);
            const data = await response.json();

            console.log('Direct download status check:', data);

            // Check if metadata and thumbnail are ready
            if (data.download_started && data.selected_stream_metadata) {
                console.log('✓ Direct download metadata ready');

                // Show popup with metadata and thumbnail (isDirect = true)
                showDownloadStartedPopup(data.selected_stream_metadata, data.thumbnail, true);

                // Stop polling
                return true;
            }

            attempts++;
            if (attempts < maxAttempts) {
                // Poll again in 1 second
                setTimeout(checkStatus, 1000);
            } else {
                console.log('Direct download metadata timeout - showing without thumbnail');
                // Show popup without thumbnail if timeout (isDirect = true)
                showDownloadStartedPopup({ name: 'Direct Download', resolution: 'Processing...', framerate: '' }, null, true);
            }
        } catch (error) {
            console.error('Error checking direct download status:', error);
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(checkStatus, 1000);
            }
        }
    };

    // Start checking
    checkStatus();
}

// Poll browser status
function startStatusPolling() {
    if (AppState.statusCheckInterval) {
        clearInterval(AppState.statusCheckInterval);
    }

    AppState.statusCheckInterval = setInterval(async () => {
        if (!AppState.currentBrowserId) return;

        try {
            const response = await fetch(`/api/browser/status/${AppState.currentBrowserId}`);
            const data = await response.json();

            // DEBUG: Log status data
            console.log('=== BROWSER STATUS UPDATE ===');
            console.log('Browser ID:', AppState.currentBrowserId);
            console.log('Is Running:', data.is_running);
            console.log('Download Started:', data.download_started);
            console.log('Detected Streams Count:', data.detected_streams);
            console.log('Awaiting Resolution Selection:', data.awaiting_resolution_selection);

            // Show stream selection modal if streams are available and manual mode
            if (data.awaiting_resolution_selection && data.available_resolutions && data.available_resolutions.length > 0) {
                console.log('=== AVAILABLE STREAMS ===');
                console.log('Count:', data.available_resolutions.length);

                data.available_resolutions.forEach((res, index) => {
                    console.log(`--- Stream ${index + 1} ---`);
                    console.log('Name:', res.name);
                    console.log('Resolution:', res.resolution);
                    console.log('Framerate:', res.framerate);
                });

                // Show VNC browser if not already shown (needed for manual selection)
                const vncContainer = document.getElementById('vnc-container');
                if (!vncContainer.classList.contains('active')) {
                    const vncFrame = document.getElementById('vnc-frame');
                    const vncUrl = 'http://' + window.location.hostname + ':6080/vnc.html?autoconnect=true&resize=scale';
                    vncFrame.src = vncUrl;
                    vncContainer.classList.add('active');
                    setTimeout(() => {
                        vncContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }, 500);
                }

                // Show modal with all available streams
                showStreamModal(data.available_resolutions);

                const statusBox = document.getElementById('browser-status');
                showStatus(statusBox, `✓ Found ${data.available_resolutions.length} streams - Select one to download`, 'success');
            }

            // Handle download started (both auto and manual)
            if (data.download_started && !AppState.downloadPopupShown) {
                console.log('✓ Download started');
                AppState.downloadPopupShown = true;
                const statusBox = document.getElementById('browser-status');
                showStatus(statusBox, '✓ Download started!', 'success');

                // Show download confirmation popup
                showDownloadStartedPopup(data.selected_stream_metadata, data.thumbnail);

                setTimeout(() => loadDownloads(), 2000);
            }

            if (!data.is_running) {
                console.log('!!! BROWSER STOPPED !!!');
                clearInterval(AppState.statusCheckInterval);

                // Reset button and hide VNC
                const btn = document.getElementById('browser-start-btn');
                btn.disabled = false;
                btn.innerHTML = 'Open Browser & Detect';

                const vncContainer = document.getElementById('vnc-container');
                vncContainer.classList.remove('active');

                AppState.currentBrowserId = null;
                loadDownloads();
            }
        } catch (error) {
            console.error('Status check error:', error);
        }
    }, 2000);
}

// Show download popup
