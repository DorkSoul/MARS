// Schedule management functions

async function loadSchedules() {
    try {
        const response = await fetch('/api/schedules/');
        const schedules = await response.json();

        const container = document.getElementById('schedules-list');
        container.innerHTML = '';

        if (schedules.length === 0) {
            container.innerHTML = '<p style="color: #b8b8d1; font-size: 0.9rem;">No active schedules</p>';
            return;
        }

        // Sort schedules by next_check time (soonest first)
        // For schedules without next_check, use start_time
        schedules.sort((a, b) => {
            // Helper function to get sortable timestamp
            const getSortTime = (sched) => {
                // If next_check exists, use it (it's already calculated by backend)
                if (sched.next_check) {
                    return new Date(sched.next_check).getTime();
                }

                // Fallback to start_time for schedules without next_check
                if (sched.daily) {
                    // Daily schedule - calculate next occurrence from time string
                    const now = new Date();
                    const [hours, minutes] = sched.start_time.split(':').map(Number);
                    const nextRun = new Date();
                    nextRun.setHours(hours, minutes, 0, 0);

                    // If the time has passed today, schedule for tomorrow
                    if (nextRun <= now) {
                        nextRun.setDate(nextRun.getDate() + 1);
                    }

                    return nextRun.getTime();
                } else {
                    // Regular schedule - use start_time directly
                    return new Date(sched.start_time).getTime();
                }
            };

            const timeA = getSortTime(a);
            const timeB = getSortTime(b);
            return timeA - timeB;
        });

        schedules.forEach(sched => {
            const item = document.createElement('div');
            item.className = 'download-item';

            // Format dates as RFC 2822 without seconds (e.g., "Mon, 08 Dec 2025 14:03")
            const formatRFC2822 = (dateStr) => {
                const date = new Date(dateStr);
                const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
                const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

                const day = days[date.getDay()];
                const dateNum = String(date.getDate()).padStart(2, '0');
                const month = months[date.getMonth()];
                const year = date.getFullYear();
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');

                return `${day}, ${dateNum} ${month} ${year} ${hours}:${minutes}`;
            };

            let windowText = '';
            let repeatText = '';

            if (sched.daily) {
                // Daily schedule - just show times
                windowText = `${sched.start_time} - ${sched.end_time} (Daily)`;
                repeatText = 'Daily';
            } else {
                // Regular schedule - show full datetime
                const start = formatRFC2822(sched.start_time);
                const end = formatRFC2822(sched.end_time);
                windowText = `${start} - ${end}`;
                repeatText = sched.repeat ? 'Weekly' : 'Once';
            }

            let statusColor = '#666';
            let statusText = sched.status;

            if (sched.status === 'active') {
                statusColor = '#28a745';
                const nextCheck = sched.next_check ? formatRFC2822(sched.next_check) : 'Pending window';
                statusText = `${sched.status} (Next check: ${nextCheck})`;
            } else if (sched.status === 'download_started') {
                statusColor = '#17a2b8';
                statusText = 'Download started (Recording in progress)';
            } else if (sched.status === 'pending') {
                statusColor = '#666';
                if (sched.next_check) {
                    const nextCheck = formatRFC2822(sched.next_check);
                    statusText = `${sched.status} (Next check: ${nextCheck})`;
                } else {
                    statusText = sched.status;
                }
            } else {
                statusText = sched.status;
            }

            item.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: start; gap: 10px;">
                    <div style="flex: 1; min-width: 0;">
                        <h4 style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${sched.url}">${sched.url}</h4>
                        <p><strong>Window:</strong> ${windowText}</p>
                        <p><strong>Repeat:</strong> ${repeatText}</p>
                        <p style="color: ${statusColor}"><strong>Status:</strong> ${statusText}</p>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 5px;">
                        <button class="btn btn-secondary" style="width: auto; padding: 5px 10px; font-size: 0.8rem; background: #7e8ce0;" onclick='editSchedule(${JSON.stringify(sched)})'>EDIT</button>
                        <button class="btn btn-secondary" style="width: auto; padding: 5px 10px; font-size: 0.8rem; background: #dc3545;" onclick="deleteSchedule('${sched.id}', this)">DELETE</button>
                    </div>
                </div>
            `;
            container.appendChild(item);
        });

    } catch (error) {
        console.error('Error loading schedules:', error);
    }
}

function toggleDailySchedule() {
    const daily = document.getElementById('sched-daily').checked;
    const startInput = document.getElementById('sched-start');
    const endInput = document.getElementById('sched-end');
    const startLabel = document.getElementById('sched-start-label');
    const endLabel = document.getElementById('sched-end-label');
    const repeatContainer = document.getElementById('sched-repeat-container');
    const repeatCheckbox = document.getElementById('sched-repeat');

    if (daily) {
        // Hide weekly repeat option (daily already repeats)
        repeatContainer.style.display = 'none';
        repeatCheckbox.checked = false;

        // Convert to time inputs
        startInput.type = 'time';
        endInput.type = 'time';
        startLabel.textContent = 'Start Time (Daily)';
        endLabel.textContent = 'End Time (Daily)';

        // Set default time values if empty
        if (!startInput.value) {
            const now = new Date();
            startInput.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
        }
        if (!endInput.value) {
            const oneHourLater = new Date(new Date().getTime() + 60 * 60 * 1000);
            endInput.value = `${String(oneHourLater.getHours()).padStart(2, '0')}:${String(oneHourLater.getMinutes()).padStart(2, '0')}`;
        }
    } else {
        // Show weekly repeat option
        repeatContainer.style.display = 'block';

        // Convert to datetime-local inputs
        startInput.type = 'datetime-local';
        endInput.type = 'datetime-local';
        startLabel.textContent = 'Start Time';
        endLabel.textContent = 'End Time';

        // Set default datetime values
        const now = new Date();
        const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);
        const formatDateTime = (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return `${year}-${month}-${day}T${hours}:${minutes}`;
        };
        startInput.value = formatDateTime(now);
        endInput.value = formatDateTime(oneHourLater);
    }
}

async function addSchedule() {
    let url = document.getElementById('sched-url').value.trim();
    const start = document.getElementById('sched-start').value;
    const end = document.getElementById('sched-end').value;
    const repeat = document.getElementById('sched-repeat').checked;
    const daily = document.getElementById('sched-daily').checked;
    const resolution = document.getElementById('sched-resolution').value;
    const framerate = document.getElementById('sched-framerate').value;
    const format = document.getElementById('sched-format').value;
    const statusBox = document.getElementById('sched-status');

    if (!url || !start || !end) {
        showStatus(statusBox, 'Please fill all fields', 'error');
        return;
    }

    // Add https:// if no protocol specified
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }

    try {
        const response = await fetch('/api/schedules/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                start_time: start,
                end_time: end,
                repeat: repeat,
                daily: daily,
                resolution: resolution,
                framerate: framerate,
                format: format,
                name: url.substring(0, 30) + '...'
            })
        });

        const data = await response.json();
        if (data.success) {
            showStatus(statusBox, 'Schedule added!', 'success');
            document.getElementById('sched-url').value = '';
            loadSchedules();
        } else {
            showStatus(statusBox, 'Error: ' + data.error, 'error');
        }
    } catch (error) {
        showStatus(statusBox, 'Error: ' + error.message, 'error');
    }
}

async function deleteSchedule(id, btn) {
    if (!confirm('Delete this schedule?')) return;

    try {
        btn.disabled = true;
        const response = await fetch(`/api/schedules/${id}`, { method: 'DELETE' });
        const data = await response.json();

        if (data.success) {
            loadSchedules();
        } else {
            alert('Error: ' + data.error);
            btn.disabled = false;
        }
    } catch (error) {
        console.error(error);
        btn.disabled = false;
    }
}

async function refreshScheduleTimes() {
    try {
        const response = await fetch('/api/schedules/refresh', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            alert(`✓ Refreshed ${data.count} schedule(s)`);
            loadSchedules();
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        console.error(error);
        alert('Error refreshing schedules: ' + error.message);
    }
}


function editSchedule(schedule) {
    // Store the schedule ID
    AppState.currentEditScheduleId = schedule.id;

    // Populate the form fields
    document.getElementById('edit-sched-url').value = schedule.url;
    document.getElementById('edit-sched-resolution').value = schedule.resolution || 'source';
    document.getElementById('edit-sched-framerate').value = schedule.framerate || 'any';
    document.getElementById('edit-sched-format').value = schedule.format || 'mp4';
    document.getElementById('edit-sched-repeat').checked = schedule.repeat || false;
    document.getElementById('edit-sched-daily').checked = schedule.daily || false;

    // Set up time inputs based on whether it's a daily schedule
    const startInput = document.getElementById('edit-sched-start');
    const endInput = document.getElementById('edit-sched-end');
    const startLabel = document.getElementById('edit-sched-start-label');
    const endLabel = document.getElementById('edit-sched-end-label');
    const repeatContainer = document.getElementById('edit-sched-repeat-container');

    if (schedule.daily) {
        // Daily schedule - use time inputs and hide weekly repeat
        startInput.type = 'time';
        endInput.type = 'time';
        startLabel.textContent = 'Start Time (Daily)';
        endLabel.textContent = 'End Time (Daily)';
        startInput.value = schedule.start_time;
        endInput.value = schedule.end_time;
        repeatContainer.style.display = 'none';
    } else {
        // Regular schedule - use datetime-local inputs and show weekly repeat
        startInput.type = 'datetime-local';
        endInput.type = 'datetime-local';
        startLabel.textContent = 'Start Time';
        endLabel.textContent = 'End Time';
        startInput.value = schedule.start_time;
        endInput.value = schedule.end_time;
        repeatContainer.style.display = 'block';
    }

    // Clear status
    const statusBox = document.getElementById('edit-sched-status');
    statusBox.classList.remove('active', 'success', 'error');

    // Show modal
    document.getElementById('edit-schedule-modal').classList.add('active');
}

function toggleEditDailySchedule() {
    const daily = document.getElementById('edit-sched-daily').checked;
    const startInput = document.getElementById('edit-sched-start');
    const endInput = document.getElementById('edit-sched-end');
    const startLabel = document.getElementById('edit-sched-start-label');
    const endLabel = document.getElementById('edit-sched-end-label');
    const repeatContainer = document.getElementById('edit-sched-repeat-container');
    const repeatCheckbox = document.getElementById('edit-sched-repeat');

    if (daily) {
        // Hide weekly repeat option (daily already repeats)
        repeatContainer.style.display = 'none';
        repeatCheckbox.checked = false;

        // Convert to time inputs
        startInput.type = 'time';
        endInput.type = 'time';
        startLabel.textContent = 'Start Time (Daily)';
        endLabel.textContent = 'End Time (Daily)';

        // If values are datetime, extract time part
        if (startInput.value && startInput.value.includes('T')) {
            startInput.value = startInput.value.split('T')[1];
        }
        if (endInput.value && endInput.value.includes('T')) {
            endInput.value = endInput.value.split('T')[1];
        }
    } else {
        // Show weekly repeat option
        repeatContainer.style.display = 'block';

        // Convert to datetime-local inputs
        startInput.type = 'datetime-local';
        endInput.type = 'datetime-local';
        startLabel.textContent = 'Start Time';
        endLabel.textContent = 'End Time';

        // If values are just times, convert to datetime
        if (startInput.value && !startInput.value.includes('T')) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            startInput.value = `${year}-${month}-${day}T${startInput.value}`;
        }
        if (endInput.value && !endInput.value.includes('T')) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            endInput.value = `${year}-${month}-${day}T${endInput.value}`;
        }
    }
}

function closeEditScheduleModal() {
    document.getElementById('edit-schedule-modal').classList.remove('active');
    AppState.currentEditScheduleId = null;
}

async function updateSchedule() {
    if (!AppState.currentEditScheduleId) {
        alert('Error: No schedule selected for editing');
        return;
    }

    let url = document.getElementById('edit-sched-url').value.trim();
    const start = document.getElementById('edit-sched-start').value;
    const end = document.getElementById('edit-sched-end').value;
    const repeat = document.getElementById('edit-sched-repeat').checked;
    const daily = document.getElementById('edit-sched-daily').checked;
    const resolution = document.getElementById('edit-sched-resolution').value;
    const framerate = document.getElementById('edit-sched-framerate').value;
    const format = document.getElementById('edit-sched-format').value;
    const statusBox = document.getElementById('edit-sched-status');

    if (!url || !start || !end) {
        showStatus(statusBox, 'Please fill all fields', 'error');
        return;
    }

    // Add https:// if no protocol specified
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }

    try {
        const response = await fetch(`/api/schedules/${AppState.currentEditScheduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: url,
                start_time: start,
                end_time: end,
                repeat: repeat,
                daily: daily,
                resolution: resolution,
                framerate: framerate,
                format: format,
                name: url.substring(0, 30) + '...'
            })
        });

        const data = await response.json();
        if (data.success) {
            showStatus(statusBox, 'Schedule updated!', 'success');
            setTimeout(() => {
                closeEditScheduleModal();
                loadSchedules();
            }, 1000);
        } else {
            showStatus(statusBox, 'Error: ' + data.error, 'error');
        }
    } catch (error) {
        showStatus(statusBox, 'Error: ' + error.message, 'error');
    }
}

// Initialize
