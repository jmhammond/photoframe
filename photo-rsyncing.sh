#!/bin/bash
# Because I can't get the TUN to work (see https://github.com/tailscale/tailscale/issues/3602)
# Here I'm basically implementing DNS myself.

LOG_FILE="/volume1/scripts/photo-logging.log"

log_message() {
    local message="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $message" >> "$LOG_FILE"
}

send_error_email() {
    local error_message="$1"
    local subject="(photoframe) rsync error"
    local body="Error occurred while syncing photos to frames
Error Details: $error_message
Here are the last 20 lines from $LOG_FILE:

$(tail -n 20 "$LOG_FILE")

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

handle_error() {
    local error_msg="$1"
    log_message "ERROR: $error_msg"
    send_error_email "$error_msg"
    exit 1
}

log_message "Getting current Tailscale IP addresses..."

# Get IP addresses (`tailscale status` returns current IPs)
HOMESTEAD_IP=$(tailscale status | grep "homestead-frame" | awk '{print $1}')
GAMBLE_IP=$(tailscale status | grep "gamble-frame" | awk '{print $1}')
MOUNTS_IP=$(tailscale status | grep "mounts-photoframe" | awk '{print $1}')
PHOTO_IP=$(tailscale status | grep -E "^\s*[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\s+photoframe\s+" | awk '{print $1}')
HAMMOND_IP=$(tailscale status | grep "hammond-photoframe" | awk '{print $1}')

log_message "Found Tailscale IP addresses:"
log_message "  homestead-frame:     $HOMESTEAD_IP"
log_message "  gamble-frame:        $GAMBLE_IP"
log_message "  mounts-photoframe:   $MOUNTS_IP"
log_message "  photoframe:          $PHOTO_IP"
log_message "  hammond-photoframe:  $HAMMOND_IP"

# Check if all IPs were found
if [ -z "$HOMESTEAD_IP" ] || [ -z "$GAMBLE_IP" ] || [ -z "$MOUNTS_IP" ] || [ -z "$PHOTO_IP" ] || [ -z "$HAMMOND_IP" ]; then
    handle_error "Could not find all required servers in Tailscale status. Make sure all photo frame servers are online and connected to Tailscale"
fi

sync_photos() {
    local source="$1"
    local dest_ip="$2"
    local server_name="$3"
    
    log_message "Syncing $server_name ($dest_ip)..."
    if rsync -az --no-perms --no-owner --no-group --modify-window=1 "$source" john@"$dest_ip":/mnt/usb1/photoframe/; then
        log_message "✓ Successfully synced to $server_name"
    else
        handle_error "Failed to sync $source to $server_name ($dest_ip)"
    fi
}

log_message "Starting photoframe sync..."
log_message "=================================="

sync_photos "/volume1/homes/farm-frame/processed_doNotTouch/" "$HOMESTEAD_IP" "homestead-frame"
sync_photos "/volume1/mounts-frame-share/processed_doNotTouch/" "$MOUNTS_IP" "mounts-photoframe"
sync_photos "/volume1/homes/ict-frame/processed_doNotTouch/" "$PHOTO_IP" "photoframe"
sync_photos "/volume1/mom-and-dad-frame/processed_doNotTouch/" "$HAMMOND_IP" "hammond-photoframe"
sync_photos "/volume1/homes/gamble-frame/processed_doNotTouch/" "$GAMBLE_IP" "gamble-frame" 