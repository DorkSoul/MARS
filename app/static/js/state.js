// Global state management
const AppState = {
    currentBrowserId: null,
    statusCheckInterval: null,
    statusEventSource: null,   // SSE EventSource for browser status updates
    countdownInterval: null,
    countdownValue: 15,
    debugLogContent: '',
    detectedStreamCount: 0,
    downloadPopupShown: false,
    statusTimeouts: new Map(),
    displayedStreams: new Set(),
    currentEditScheduleId: null
};

// Export for use in other modules
window.AppState = AppState;
