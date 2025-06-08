#!/bin/bash
#
# For Dan's picture frame, he'll upload it his synology folder 
# and then we'll move it to the watched share folder. Easier to 
# figure out for him.


# Configuration
WATCH_DIR="/volume1/homes/mounts-frame"
TO_DIR="/volume1/mounts-frame-share"
LOG_FILE="/volume1/scripts/photo-logging.log"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

log_message "----------"
log_message "Starting monitor for $WATCH_DIR"

# Monitor the directory for new files
inotifywait -m -e create -e moved_to "$WATCH_DIR" --format '%w%f %e' |
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
            if mv "$FILE" "$TO_DIR" >> "$LOG_FILE" 2>&1; then
                return
            else
                log_message "Error: Failed to copy: $FILE"
            fi
            ;;
        *)
            # Silently ignore non-image files
            ;;
    esac
done