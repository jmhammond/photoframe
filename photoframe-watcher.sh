#!/bin/bash

# Configuration
SCRIPT_TO_RUN="/volume1/scripts/family-frame-processor.sh"
LOG_FILE="/volume1/scripts/photo-logging.log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log_message "----------"
log_message "Starting monitor for the square-ish frames"

# Monitor multiple directories for new files
inotifywait -m -e create,moved_to \
    /volume1/homes/farm-frame \
    /volume1/homes/gamble-frame \
    /volume1/mounts-frame-share \
    /volume1/homes/ict-frame \
    --format '%w%f %e' | 
while read FILE EVENT; do
    log_message "Detected $EVENT: $FILE"
    
    # Optional: Wait a moment for file to be fully written
    sleep 2
    
    # Extract just the filename for extension checking
    filename=$(basename "$FILE")

    # Check if it's an image file
    case "${filename,,}" in
        *.jpg|*.jpeg|*.png|*.heic|*.JPG|*.JPEG|*.PNG|*.HEIC)
            # Process the image
            if "$SCRIPT_TO_RUN" "$FILE" >> "$LOG_FILE" 2>&1; then
                # Skip logging success
                return
            else
                log_message "Error: Failed to process: $FILE"
            fi
            ;;
        *)
            # Silently ignore non-image files
            ;;
    esac
done