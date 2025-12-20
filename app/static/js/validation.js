// Filename validation module

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

// Export for use in other modules
window.validateFilename = validateFilename;
