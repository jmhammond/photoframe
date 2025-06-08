#!/bin/bash

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" 
}

# Take the specific file path as input
INPUT_FILE="$1"

# Check if a file was provided
if [[ -z "$INPUT_FILE" ]]; then
    log_message "Error: No file path provided"
    log_message "Usage: $0 /path/to/image/file"
    exit 1
fi

# Check if the file exists
if [[ ! -f "$INPUT_FILE" ]]; then
    log_message "Error: File '$INPUT_FILE' does not exist"
    exit 1
fi

# Check if ImageMagick is installed
if ! command -v magick &> /dev/null; then
    log_message "Error: ImageMagick is not installed or 'magick' command not found"
    exit 1
fi

# Get the directory containing the file
IMAGE_DIR=$(dirname "$INPUT_FILE")

# Get just the filename
filename=$(basename "$INPUT_FILE")

# Check if it's an image file by extension
case "${filename,,}" in
    *.jpg|*.jpeg|*.png|*.heic)
        # Silent processing for image files
        ;;
    *)
        log_message "Error: Not an image file: $INPUT_FILE"
        exit 0
        ;;
esac

# Get image dimensions
dimensions=$(magick identify -format "%w %h" "$INPUT_FILE" 2>/dev/null)
if [[ $? -ne 0 ]]; then
    log_message "Error: Could not read dimensions for $INPUT_FILE"
    exit 1
fi

width=$(echo $dimensions | cut -d' ' -f1)
height=$(echo $dimensions | cut -d' ' -f2)

# Extract filename without extension for output
name_no_ext="${filename%.*}"
extension="${filename##*.}"

OLD_DIR="$IMAGE_DIR/old_doNotTouch"
PROCESSED_DIR="$IMAGE_DIR/processed_doNotTouch"

mkdir -p "$OLD_DIR"
mkdir -p "$PROCESSED_DIR"

# Create output filename in the processed directory
output="$PROCESSED_DIR/framed_${filename}"

# Check if image is already very close to target dimensions or should be skipped
width_border_needed=$(( (1920 - width) / 2 ))
height_border_needed=$(( (1080 - height) / 2 ))
width_border_abs=${width_border_needed#-}  # Get absolute value
height_border_abs=${height_border_needed#-}  # Get absolute value

# Skip processing for images that are already good sizes
if [[ ($width -eq 1920 && $height -eq 1080) || 
      ($width -eq 1920 && $height -gt 1080 && $height -le 1920) || 
      ($height -eq 1080 && $width -gt 1920 && $width -le 2400) ||
      ($width -ge 1920 && $height -ge 1080 && $width -le 2400 && $height -le 1920) ]]; then
    cp "$INPUT_FILE" "$output"
    if [[ $? -ne 0 ]]; then
        log_message "Error: Failed to copy: $INPUT_FILE"
        exit 1
    fi
elif [[ $width_border_abs -lt 35 && $height_border_abs -lt 35 ]]; then
    # Image is very close to target size - just scale it to exact dimensions without borders
    magick "$INPUT_FILE" \
        -auto-orient \
        -resize "1920x1080!" \
        "$output"
    
    if [[ $? -ne 0 ]]; then
        log_message "Error: Failed to scale: $INPUT_FILE"
        exit 1
    fi
else
    # Standard processing for images that need significant resizing
    # Always use horizontal borders (left/right) since max width is 1280
    resize_bg="^1920x1080"
    crop_size="1920x1080+0+0"
    resize_fg="1920x1080"
    extent_size="1920x1080"
    border1="15x0"
    border2="3x0"
fi

# Apply the ImageMagick command with dynamic dimensions
if [[ -z "$crop_size" ]]; then
    # No cropping - just resize and composite
    magick "$INPUT_FILE" \
        -auto-orient \
        -resize "$resize_bg" \
        -gravity center \
        +repage \
        -blur '0x12' \
        -brightness-contrast '-20x0' \
        \( "$INPUT_FILE" \
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
    magick "$INPUT_FILE" \
        -auto-orient \
        -resize "$resize_bg" \
        -gravity center \
        -crop "$crop_size" \
        +repage \
        -blur '0x12' \
        -brightness-contrast '-20x0' \
        \( "$INPUT_FILE" \
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
    log_message "Error: Failed to frame: $INPUT_FILE"
    exit 1
fi

# Move original file to old directory (only after successful processing)
if ! mv "$INPUT_FILE" "$OLD_DIR/"; then
    log_message "Error: Failed to move original file to old directory"
fi

log_message "✓ Processed: $(basename "$INPUT_FILE")"