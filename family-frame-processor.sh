#!/bin/bash

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" 
}

IMAGE_FILE="$1"

# Function to send email notification
send_error_email() {
    local error_message="$1"
    local subject="Family Frame Processor Error"
    local body="Error occurred while processing image: $IMAGE_FILE

Error Details:
$error_message

Check the log at /volume1/scripts/photo-logging.log for more details.

Timestamp: $(date '+%Y-%m-%d %H:%M:%S')
Host: $(hostname)
Script: $0"

    # Check if ssmtp is available
    if command -v ssmtp &> /dev/null; then
        {
            echo "To: jmhammond@gmail.com"
            echo "Subject: $subject"
            echo ""
            echo "$body"
        } | ssmtp jmhammond@gmail.com
    else
        log_message "Warning: ssmtp not found, cannot send email notification"
    fi
}

# Function to handle errors and send email
handle_error() {
    local error_msg="$1"
    log_message "$error_msg"
    send_error_email "$error_msg"
    exit 1
}

# Check if file exists
if [[ ! -f "$IMAGE_FILE" ]]; then
    handle_error "Error: File not found: $IMAGE_FILE"
fi

# Check if ImageMagick is installed
if ! command -v magick &> /dev/null; then
    handle_error "Error: ImageMagick is not installed or 'magick' command not found"
fi

# Get the directory containing the image file
IMAGE_DIR=$(dirname "$IMAGE_FILE")
FILENAME=$(basename "$IMAGE_FILE")

OLD_DIR="$IMAGE_DIR/old_doNotTouch"
PROCESSED_DIR="$IMAGE_DIR/processed_doNotTouch"

mkdir -p "$OLD_DIR"
mkdir -p "$PROCESSED_DIR"

# Check if file has supported extension
case "${FILENAME,,}" in
    *.jpg|*.jpeg|*.png|*.heic)
        ;;
    *)
        # if there's an unsupported file, I don't care about an email.
        log_message "Error: Unsupported file format: $FILENAME"
        exit 1 
esac

# Get image dimensions
dimensions=$(magick identify -format "%w %h" "$IMAGE_FILE" 2>/dev/null)
if [[ $? -ne 0 ]]; then
    handle_error "Error: Could not read dimensions for $IMAGE_FILE"
fi

# Fixed dimension parsing - use echo instead of log_message
width=$(echo $dimensions | cut -d' ' -f1)
height=$(echo $dimensions | cut -d' ' -f2)

# Extract filename without extension for output
name_no_ext="${FILENAME%.*}"
extension="${FILENAME##*.}"

# Create output filename in processed directory with framed_ prefix
output="$PROCESSED_DIR/framed_$FILENAME"

# Check if image is already very close to target dimensions or should be skipped
width_border_needed=$(( (1280 - width) / 2 ))
height_border_needed=$(( (1024 - height) / 2 ))
width_border_abs=${width_border_needed#-}  # Get absolute value
height_border_abs=${height_border_needed#-}  # Get absolute value

# Skip processing for images that are already good sizes
if [[ ($width -eq 1280 && $height -eq 1280) || 
      ($width -eq 1280 && $height -gt 1024 && $height -le 1280) || 
      ($height -eq 1024 && $width -gt 1280 && $width -le 1600) ||
      ($width -ge 1280 && $height -ge 1024 && $width -le 1600 && $height -le 1280) ]]; then
    cp "$IMAGE_FILE" "$output"
    if [[ $? -ne 0 ]]; then
        handle_error "Error: Failed to copy $IMAGE_FILE"
    fi
elif [[ $width_border_abs -lt 35 && $height_border_abs -lt 35 ]]; then
    # Image is very close to target size - just scale it to exact dimensions without borders
    magick "$IMAGE_FILE" \
        -auto-orient \
        -resize "1280x1024!" \
        "$output"
    
    if [[ $? -ne 0 ]]; then
        handle_error "Error: Failed to scale $IMAGE_FILE"
    fi
else
    # Standard processing for images that need significant resizing
    if [[ $width -lt $height ]]; then
        # Portrait: height is larger, so make 1024 the max height
        resize_bg="1280x1024^"
        crop_size="1280x1024+0+0"
        resize_fg="1280x1024"
        extent_size="1280x1024"
        border1="15x0"
        border2="3x0"
    else
        # Landscape: width is larger, so make 1280 the max width
        resize_bg="^1280x1024"
        crop_size="1280x1024+0+0"
        resize_fg="1280x1024"
        extent_size="1280x1024"
        border1="0x15"
        border2="0x3"
    fi
    
    # Apply the ImageMagick command with dynamic dimensions
    if [[ -z "$crop_size" ]]; then
        # No cropping - just resize and composite
        magick "$IMAGE_FILE" \
            -auto-orient \
            -resize "$resize_bg" \
            -gravity center \
            +repage \
            -blur '0x12' \
            -brightness-contrast '-20x0' \
            \( "$IMAGE_FILE" \
                -bordercolor black \
                -border "$border1" \
                -bordercolor black \
                -border "$border2" \
                -resize "$resize_fg" \
                -background transparent \
                -gravity center \
                -extent "$extent_size" \
            \) \
            -composite \
            "$output"
    else
        # Standard processing with cropping
        magick "$IMAGE_FILE" \
            -auto-orient \
            -resize "$resize_bg" \
            -gravity center \
            -crop "$crop_size" \
            +repage \
            -blur '0x12' \
            -brightness-contrast '-20x0' \
            \( "$IMAGE_FILE" \
                -bordercolor black \
                -border "$border1" \
                -bordercolor black \
                -border "$border2" \
                -resize "$resize_fg" \
                -background transparent \
                -gravity center \
                -extent "$extent_size" \
            \) \
            -composite \
            "$output"
    fi
    
    if [[ $? -ne 0 ]]; then
        handle_error "Error: Failed to frame $IMAGE_FILE"
    fi
fi

# Move original file to old directory (only after successful processing)
if ! mv "$IMAGE_FILE" "$OLD_DIR/"; then
    handle_error "Error: Failed to move original file to old directory"
fi

log_message "✓ Processed: $(basename "$IMAGE_FILE")"