// Initialization and event listeners

document.addEventListener('DOMContentLoaded', () => {
    initSchedulePickers();

    loadDownloads();
    loadSchedules();
    loadCompletedDownloads();
    setInterval(loadSchedules, 10000); // Refresh schedules every 10s
    setInterval(loadDownloads, 1000); // Refresh active downloads every 1 second
    setInterval(loadCompletedDownloads, 10000); // Refresh completed downloads every 10 seconds

    // Close modal when clicking outside of it
    window.onclick = function (event) {
        const streamModal = document.getElementById('stream-modal');
        const editScheduleModal = document.getElementById('edit-schedule-modal');

        if (event.target === streamModal) {
            closeStreamModal();
        }

        if (event.target === editScheduleModal) {
            closeEditScheduleModal();
        }
    };

    // Add blur event listeners for filename validation
    document.getElementById('direct-filename').addEventListener('blur', () => {
        const format = document.getElementById('direct-format').value;
        validateFilename('direct-filename', 'direct-filename-error', format);
    });

    document.getElementById('browser-filename').addEventListener('blur', () => {
        const format = document.getElementById('browser-format').value;
        validateFilename('browser-filename', 'browser-filename-error', format);
    });
});
