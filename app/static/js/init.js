// Initialization and event listeners

document.addEventListener('DOMContentLoaded', () => {
    // Set default schedule times to now and +1 hour
    const now = new Date();
    const oneHourLater = new Date(now.getTime() + 60 * 60 * 1000);

    // Format as YYYY-MM-DDTHH:MM for datetime-local input
    const formatDateTime = (date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    };

    document.getElementById('sched-start').value = formatDateTime(now);
    document.getElementById('sched-end').value = formatDateTime(oneHourLater);

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
