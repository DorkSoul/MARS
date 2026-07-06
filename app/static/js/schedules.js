// Schedule management functions

// Module-level TimePicker instances (initialised by initSchedulePickers)
let schedStartTP, schedEndTP, editStartTP, editEndTP;

function initSchedulePickers() {
    const now   = new Date();
    const later = new Date(now.getTime() + 3600000);

    schedStartTP = new TimePicker('sched-start-time', { initialValue: _fmtTime(now) });
    schedEndTP   = new TimePicker('sched-end-time',   { initialValue: _fmtTime(later) });
    editStartTP  = new TimePicker('edit-sched-start-time', { initialValue: '00:00' });
    editEndTP    = new TimePicker('edit-sched-end-time',   { initialValue: '01:00' });

    document.getElementById('sched-start-date').value = _fmtDate(now);
    document.getElementById('sched-end-date').value   = _fmtDate(later);
}

// ── Helpers ──────────────────────────────────────────────────

function _fmtDate(d) {
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function _fmtTime(d) {
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function _getDatetime(dateId, tp) {
    const date = document.getElementById(dateId).value;
    const time = tp.getValue();
    return date && time ? `${date}T${time}` : '';
}

function _setDatetime(dateId, tp, iso) {
    if (!iso) return;
    if (iso.includes('T')) {
        const [d, t] = iso.split('T');
        document.getElementById(dateId).value = d;
        tp.setValue(t.substring(0, 5));
    } else {
        tp.setValue(iso.substring(0, 5));
    }
}

function _showDateInputs(groupId, visible) {
    const el = document.getElementById(groupId)?.querySelector('.date-input');
    if (el) el.style.display = visible ? '' : 'none';
}

// ── Load / display ────────────────────────────────────────────

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

        schedules.sort((a, b) => {
            if (a.paused && !b.paused) return 1;
            if (!a.paused && b.paused) return -1;
            const getSortTime = (s) => {
                if (s.next_check) return new Date(s.next_check).getTime();
                if (s.daily) {
                    const now = new Date();
                    const [h, m] = s.start_time.split(':').map(Number);
                    const next = new Date(); next.setHours(h, m, 0, 0);
                    if (next <= now) next.setDate(next.getDate() + 1);
                    return next.getTime();
                }
                return new Date(s.start_time).getTime();
            };
            return getSortTime(a) - getSortTime(b);
        });

        schedules.forEach(sched => {
            const item = document.createElement('div');
            item.className = 'download-item';

            const formatRFC2822 = (dateStr) => {
                const date = new Date(dateStr);
                const days   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
                const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                return `${days[date.getDay()]}, ${String(date.getDate()).padStart(2,'0')} ${months[date.getMonth()]} ${date.getFullYear()} ${String(date.getHours()).padStart(2,'0')}:${String(date.getMinutes()).padStart(2,'0')}`;
            };

            let windowText = '', repeatText = '';
            if (sched.daily) {
                windowText = `${sched.start_time} – ${sched.end_time} (Daily)`;
                repeatText = 'Daily';
            } else {
                windowText = `${formatRFC2822(sched.start_time)} – ${formatRFC2822(sched.end_time)}`;
                repeatText = sched.repeat ? 'Weekly' : 'Once';
            }

            let statusColor = '#666', statusText = sched.status;
            if (sched.paused) {
                statusColor = '#888'; statusText = 'paused';
            } else if (sched.status === 'active') {
                statusColor = '#28a745';
                const nextCheck = sched.next_check ? formatRFC2822(sched.next_check) : 'Pending window';
                statusText = `${sched.status} (Next check: ${nextCheck})`;
            } else if (sched.status === 'download_started') {
                statusColor = '#17a2b8';
                statusText = 'Download started (Recording in progress)';
            } else if (sched.status === 'pending' && sched.next_check) {
                statusColor = '#666';
                statusText = `${sched.status} (Next check: ${formatRFC2822(sched.next_check)})`;
            }

            // Build with DOM APIs — the URL is user-controlled and must not be
            // interpolated into HTML or inline handlers
            const row = _el('div', 'display:flex;justify-content:space-between;align-items:start;gap:10px;');

            const info = _el('div', 'flex:1;min-width:0;');
            const title = _el('h4', 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;', sched.url);
            title.title = sched.url;
            info.appendChild(title);
            info.appendChild(_infoLine('Window', windowText, ''));
            info.appendChild(_infoLine('Repeat', repeatText, ''));
            info.appendChild(_infoLine('Status', statusText, `color:${statusColor}`));
            row.appendChild(info);

            const buttons = _el('div', 'display:flex;flex-direction:column;gap:5px;');
            const btnCss = 'width:auto;padding:5px 10px;font-size:0.8rem;';

            const editBtn = _el('button', btnCss + 'background:#7e8ce0;', 'EDIT');
            editBtn.className = 'btn btn-secondary';
            editBtn.addEventListener('click', () => editSchedule(sched));
            buttons.appendChild(editBtn);

            const pauseBtn = _el('button', btnCss + `background:${sched.paused ? '#28a745' : '#e09820'};`, sched.paused ? 'UNPAUSE' : 'PAUSE');
            pauseBtn.className = 'btn btn-secondary';
            pauseBtn.addEventListener('click', () => pauseSchedule(sched.id, pauseBtn));
            buttons.appendChild(pauseBtn);

            const deleteBtn = _el('button', btnCss + 'background:#dc3545;', 'DELETE');
            deleteBtn.className = 'btn btn-secondary';
            deleteBtn.addEventListener('click', () => deleteSchedule(sched.id, deleteBtn));
            buttons.appendChild(deleteBtn);

            row.appendChild(buttons);
            item.appendChild(row);
            container.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading schedules:', error);
    }
}

// ── Toggle daily mode ─────────────────────────────────────────

function toggleDailySchedule() {
    const daily = document.getElementById('sched-daily').checked;
    const repeatContainer = document.getElementById('sched-repeat-container');
    document.getElementById('sched-repeat').checked = false;

    document.getElementById('sched-start-label').textContent = daily ? 'Start Time (Daily)' : 'Start Time';
    document.getElementById('sched-end-label').textContent   = daily ? 'End Time (Daily)'   : 'End Time';

    _showDateInputs('sched-start-group', !daily);
    _showDateInputs('sched-end-group',   !daily);
    repeatContainer.style.display = daily ? 'none' : 'block';
}

function toggleEditDailySchedule() {
    const daily = document.getElementById('edit-sched-daily').checked;
    document.getElementById('edit-sched-repeat').checked = false;

    document.getElementById('edit-sched-start-label').textContent = daily ? 'Start Time (Daily)' : 'Start Time';
    document.getElementById('edit-sched-end-label').textContent   = daily ? 'End Time (Daily)'   : 'End Time';

    _showDateInputs('edit-sched-start-group', !daily);
    _showDateInputs('edit-sched-end-group',   !daily);
    document.getElementById('edit-sched-repeat-container').style.display = daily ? 'none' : 'block';
}

// ── Add schedule ──────────────────────────────────────────────

async function addSchedule() {
    let url    = document.getElementById('sched-url').value.trim();
    const name = document.getElementById('sched-name').value.trim();
    const repeat    = document.getElementById('sched-repeat').checked;
    const daily     = document.getElementById('sched-daily').checked;
    const resolution = document.getElementById('sched-resolution').value;
    const framerate  = document.getElementById('sched-framerate').value;
    const format     = document.getElementById('sched-format').value;
    const statusBox  = document.getElementById('sched-status');

    const start = daily ? schedStartTP.getValue() : _getDatetime('sched-start-date', schedStartTP);
    const end   = daily ? schedEndTP.getValue()   : _getDatetime('sched-end-date',   schedEndTP);

    if (!url || !start || !end) {
        showStatus(statusBox, 'Please fill all fields', 'error');
        return;
    }

    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;

    const requestBody = {
        url, start_time: start, end_time: end,
        repeat, daily, resolution, framerate, format,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
    if (name) requestBody.name = name;

    try {
        const response = await fetch('/api/schedules/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });
        const data = await response.json();
        if (data.success) {
            showStatus(statusBox, 'Schedule added!', 'success');
            document.getElementById('sched-url').value  = '';
            document.getElementById('sched-name').value = '';
            loadSchedules();
        } else {
            showStatus(statusBox, 'Error: ' + data.error, 'error');
        }
    } catch (error) {
        showStatus(statusBox, 'Error: ' + error.message, 'error');
    }
}

// ── Pause / delete / refresh ──────────────────────────────────

async function pauseSchedule(id, btn) {
    try {
        btn.disabled = true;
        const response = await fetch(`/api/schedules/${id}/pause`, { method: 'POST' });
        const data = await response.json();
        if (data.success) { loadSchedules(); } else { alert('Error: ' + data.error); btn.disabled = false; }
    } catch (error) { console.error(error); btn.disabled = false; }
}

async function deleteSchedule(id, btn) {
    if (!confirm('Delete this schedule?')) return;
    try {
        btn.disabled = true;
        const response = await fetch(`/api/schedules/${id}`, { method: 'DELETE' });
        const data = await response.json();
        if (data.success) { loadSchedules(); } else { alert('Error: ' + data.error); btn.disabled = false; }
    } catch (error) { console.error(error); btn.disabled = false; }
}

async function refreshScheduleTimes() {
    try {
        const response = await fetch('/api/schedules/refresh', { method: 'POST' });
        const data = await response.json();
        if (data.success) { alert(`✓ Refreshed ${data.count} schedule(s)`); loadSchedules(); }
        else { alert('Error: ' + data.error); }
    } catch (error) { alert('Error refreshing schedules: ' + error.message); }
}

// ── Edit schedule modal ───────────────────────────────────────

function editSchedule(schedule) {
    AppState.currentEditScheduleId = schedule.id;

    document.getElementById('edit-sched-url').value        = schedule.url;
    document.getElementById('edit-sched-name').value       = schedule.name || '';
    document.getElementById('edit-sched-resolution').value = schedule.resolution || 'source';
    document.getElementById('edit-sched-framerate').value  = schedule.framerate || 'any';
    document.getElementById('edit-sched-format').value     = schedule.format || 'mp4';
    document.getElementById('edit-sched-repeat').checked   = schedule.repeat || false;
    document.getElementById('edit-sched-daily').checked    = schedule.daily  || false;

    const daily = schedule.daily || false;
    document.getElementById('edit-sched-start-label').textContent = daily ? 'Start Time (Daily)' : 'Start Time';
    document.getElementById('edit-sched-end-label').textContent   = daily ? 'End Time (Daily)'   : 'End Time';
    _showDateInputs('edit-sched-start-group', !daily);
    _showDateInputs('edit-sched-end-group',   !daily);
    document.getElementById('edit-sched-repeat-container').style.display = daily ? 'none' : 'block';

    _setDatetime('edit-sched-start-date', editStartTP, schedule.start_time);
    _setDatetime('edit-sched-end-date',   editEndTP,   schedule.end_time);

    document.getElementById('edit-sched-status').classList.remove('active', 'success', 'error');
    document.getElementById('edit-schedule-modal').classList.add('active');
}

function closeEditScheduleModal() {
    document.getElementById('edit-schedule-modal').classList.remove('active');
    AppState.currentEditScheduleId = null;
}

async function updateSchedule() {
    if (!AppState.currentEditScheduleId) { alert('Error: No schedule selected for editing'); return; }

    let url    = document.getElementById('edit-sched-url').value.trim();
    const name = document.getElementById('edit-sched-name').value.trim();
    const repeat    = document.getElementById('edit-sched-repeat').checked;
    const daily     = document.getElementById('edit-sched-daily').checked;
    const resolution = document.getElementById('edit-sched-resolution').value;
    const framerate  = document.getElementById('edit-sched-framerate').value;
    const format     = document.getElementById('edit-sched-format').value;
    const statusBox  = document.getElementById('edit-sched-status');

    const start = daily ? editStartTP.getValue() : _getDatetime('edit-sched-start-date', editStartTP);
    const end   = daily ? editEndTP.getValue()   : _getDatetime('edit-sched-end-date',   editEndTP);

    if (!url || !start || !end) { showStatus(statusBox, 'Please fill all fields', 'error'); return; }
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;

    const requestBody = {
        url, start_time: start, end_time: end,
        repeat, daily, resolution, framerate, format,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
    if (name) requestBody.name = name;

    try {
        const response = await fetch(`/api/schedules/${AppState.currentEditScheduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });
        const data = await response.json();
        if (data.success) {
            showStatus(statusBox, 'Schedule updated!', 'success');
            setTimeout(() => { closeEditScheduleModal(); loadSchedules(); }, 1000);
        } else {
            showStatus(statusBox, 'Error: ' + data.error, 'error');
        }
    } catch (error) {
        showStatus(statusBox, 'Error: ' + error.message, 'error');
    }
}
