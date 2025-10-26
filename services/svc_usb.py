# This file is part of photoframe (https://github.com/mrworf/photoframe).
#
# photoframe is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# photoframe is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with photoframe.  If not, see <http://www.gnu.org/licenses/>.
#

from .base import BaseService
import subprocess
import os
import logging
import json
import random
import math
import time
import heapq

from modules.helper import helper
from modules.network import RequestResult
from modules import debug


class USB_Photos(BaseService):
    SERVICE_NAME = 'USB-Photos'
    SERVICE_ID = 4

    SUPPORTED_FILESYSTEMS = ['exfat', 'vfat', 'ntfs', 'ext2', 'ext3', 'ext4']
    SUBSTATE_NOT_CONNECTED = 404

    INDEX = 0

    class StorageUnit:
        def __init__(self):
            self.device = None
            self.uuid = None
            self.size = 0
            self.fs = None
            self.hotplug = False
            self.mountpoint = None
            self.freshness = 0
            self.label = None

        def setLabel(self, label):
            self.label = label
            return self

        def setDevice(self, device):
            self.device = device
            return self

        def setUUID(self, uuid):
            self.uuid = uuid
            return self

        def setSize(self, size):
            self.size = int(size)
            return self

        def setFilesystem(self, fs):
            self.fs = fs
            return self

        def setHotplug(self, hotplug):
            self.hotplug = hotplug
            return self

        def setMountpoint(self, mountpoint):
            self.mountpoint = mountpoint
            return self

        def setFreshness(self, freshness):
            self.freshness = int(freshness)
            return self

        def getName(self):
            if self.label is None:
                return self.device
            return self.label

    def __init__(self, configDir, id, name):
        BaseService.__init__(self, configDir, id, name, needConfig=False, needOAuth=False)
        self._dir_cache = {}
        self._cache_timestamps = {}

    def _ensure_cache_initialized(self):
        """Ensure cache dictionaries are initialized"""
        if not hasattr(self, '_dir_cache'):
            self._dir_cache = {}
            logging.debug("Initialized _dir_cache")
        if not hasattr(self, '_cache_timestamps'):
            self._cache_timestamps = {}
            logging.debug("Initialized _cache_timestamps")

    def _get_dir_mtime(self, path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0

    def _is_cache_valid(self, path, current_mtime):
        self._ensure_cache_initialized()
        if path not in self._cache_timestamps:
            logging.debug(f"Cache miss - no timestamp for {path}")
            return False
        
        cache_info = self._cache_timestamps[path]
        cache_created = cache_info['created']
        cached_mtime = cache_info['dir_mtime']
        
        import datetime
        
        # Check 1: Daily 3am expiry using cache creation time
        cache_time = datetime.datetime.fromtimestamp(cache_created)
        now = datetime.datetime.now()
        
        cache_date = cache_time.date()
        next_day_3am = datetime.datetime.combine(
            cache_date + datetime.timedelta(days=1), 
            datetime.time(3, 0, 0)
        )
        
        if now >= next_day_3am:
            logging.debug(f"Cache invalidated for {path} - past 3am cutoff ({next_day_3am})")
            return False
        
        # Check 2: Directory modification time
        if current_mtime != cached_mtime:
            logging.debug(f"Cache invalidated for {path} - directory modified (was {cached_mtime}, now {current_mtime})")
            return False
        
        logging.debug(f"Cache is valid for {path}")
        return True

    def _cache_directory_scan(self, path):
        """Cache directory contents - always scan both files and dirs"""
        self._ensure_cache_initialized()  
        if not os.path.exists(path):
            return [], []
        
        current_mtime = self._get_dir_mtime(path)
        
        # Check if cache is valid
        if self._is_cache_valid(path, current_mtime):
            if path in self._dir_cache:
                logging.debug(f"Using cached directory scan for {path}")
                return self._dir_cache[path]
        
        logging.debug(f"Performing fresh directory scan for {path}")
        
        files = []
        dirs = []
        
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    if entry.name.startswith("."):
                        continue
                    
                    if entry.is_file():
                        files.append((entry.stat().st_mtime, entry.name))
                    elif entry.is_dir():
                        dirs.append((entry.stat().st_mtime, entry.name))
        except OSError:
            return [], []
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x[0], reverse=True)
        dirs.sort(key=lambda x: x[0], reverse=True)
        
        self._cache_timestamps[path] = {
            'created': time.time(),        # When cache was created (for 3am expiry)
            'dir_mtime': current_mtime     # Directory's mtime (for change detection)
        }
        
        self._dir_cache[path] = (files, dirs)
        
        logging.debug(f"Cached directory scan for {path}: {len(files)} files, {len(dirs)} dirs")
        
        return files, dirs

    def invalidate_cache(self):
        """Manually invalidate cache"""
        self._dir_cache.clear()
        self._cache_timestamps.clear()
        logging.debug("Directory cache invalidated")

    def weighted_random_selection(self, files, max_images):
        """Weighted selection favoring newer files (assumes files are pre-sorted newest-first).
        Uses proper sampling without replacement so older files still appear.
        """
        if len(files) <= max_images:
            return list(files)

        # Get decay factor from settings, but respect explicit 0
        from modules.settings import settings
        settings_mgr = settings()
        settings_mgr.load()
        raw_decay = settings_mgr.getUser('decay_factor')
        try:
            decay_factor = 0.0005 if raw_decay is None else float(raw_decay)
        except (TypeError, ValueError):
            decay_factor = 0.0005

        # No weighting: uniform sample without replacement over the full set
        if decay_factor <= 0:
            return random.sample(list(files), max_images)

        # Compute weights newest-first
        weights = [math.exp(-i * decay_factor) for i in range(len(files))]

        # Weighted sampling without replacement (Efraimidis–Spirakis)
        # Generate a key per item and take the top-k by key
        keys = []
        for idx, w in enumerate(weights):
            if w <= 0:
                w = 1e-12  # guard against zero/negative due to numeric issues
            u = random.random()
            # Equivalent stable variant: key = math.log(u) / w and take smallest
            key = u ** (1.0 / w)
            keys.append((key, files[idx]))

        selected = [name for _, name in heapq.nlargest(max_images, keys, key=lambda kv: kv[0])]
        return selected

    def preSetup(self):
        USB_Photos.INDEX = 1 # there's only one USB drive in any of my systems. 
        self.usbDir = "/mnt/usb%d" % USB_Photos.INDEX
        self.baseDir = os.path.join(self.usbDir, "photoframe")

        self.device = None
        if not os.path.exists(self.baseDir):
            self.mountStorageDevice()
        elif len(os.listdir(self.baseDir)) == 0:
            self.unmountBaseDir()
            self.mountStorageDevice()
        else:
            self.checkForInvalidKeywords()
            for device in self.detectAllStorageDevices(onlyMounted=True):
                if device.mountpoint == self.usbDir:
                    self.device = device
                    logging.info("USB-Service has detected device '%s'" % self.device.device)
                    break
            if self.device is None:
                # Service should still be working fine
                logging.warning("Unable to determine which storage device is mounted to '%s'" % self.usbDir)

    def helpKeywords(self):
        return "Place photo albums in /photoframe/{album_name} on your usb-device.\n" \
               "Use the {album_name} as keyword (CasE-seNsitiVe!).\nIf you want to display all albums simply write " \
               "'ALLALBUMS' as keyword.\nAlternatively, place images directly inside the '/photoframe/' directory."

    def validateKeywords(self, keyword):
        if keyword != 'ALLALBUMS' and keyword != '_PHOTOFRAME_':
            if keyword not in self.getAllAlbumNames():
                return {'error': 'No such album "%s"' % keyword, 'keywords': keyword}

        return BaseService.validateKeywords(self, keyword)

    def getKeywords(self):
        if not os.path.exists(self.baseDir):
            return []

        keywords = list(self._STATE['_KEYWORDS'])
        if "ALLALBUMS" in keywords:
            # No, you can't have an album called /photoframe/ALLALBUMS ...
            keywords.remove("ALLALBUMS")
            albums = self.getAllAlbumNames()
            keywords.extend([a for a in albums if a not in keywords])

            if "ALLALBUMS" in albums:
                logging.error("You should not have a album called 'ALLALBUMS'!")

        if len(keywords) == 0 and len(self.getBaseDirImages()) != 0 and "_PHOTOFRAME_" not in keywords:
            keywords.append("_PHOTOFRAME_")
            # _PHOTOFRAME_ can be manually deleted via web interface if other keywords are specified!

        self._STATE['_KEYWORDS'] = keywords
        self.saveState()
        return keywords

    def checkForInvalidKeywords(self):
        index = len(self._STATE['_KEYWORDS'])-1
        for keyword in reversed(self._STATE['_KEYWORDS']):
            if keyword == "_PHOTOFRAME_":
                if len(self.getBaseDirImages()) == 0:
                    logging.debug(
                        "USB-Service: removing keyword '%s' because there are "
                        "no images directly inside the basedir!" % keyword)
                    self.removeKeywords(index)
            elif keyword not in self.getAllAlbumNames():
                logging.info("USB-Service: removing invalid keyword: %s" % keyword)
                self.removeKeywords(index)
            index -= 1
        self.saveState()

    def updateState(self):
        self.subState = None
        if not os.path.exists(self.baseDir):
            if not self.mountStorageDevice():
                self._CURRENT_STATE = BaseService.STATE_NO_IMAGES
                self.subState = USB_Photos.SUBSTATE_NOT_CONNECTED
                return self._CURRENT_STATE
        if len(self.getAllAlbumNames()) == 0 and len(self.getBaseDirImages()) == 0:
            self._CURRENT_STATE = BaseService.STATE_NO_IMAGES
            return self._CURRENT_STATE

        return BaseService.updateState(self)

    def explainState(self):
        if self._CURRENT_STATE == BaseService.STATE_NO_IMAGES:
            if self.subState == USB_Photos.SUBSTATE_NOT_CONNECTED:
                return "No storage device (e.g. USB-stick) has been detected"
            else:
                return 'Place images and/or albums inside a "photoframe"-directory on your storage device'
        return None

    def getMessages(self):
        # display a message indicating which storage device is being used or
        # an error messing if no suitable storage device could be found
        if self.device and os.path.exists(self.baseDir):
            msgs = [
                {
                    'level': 'SUCCESS',
                    'message': 'Storage device "%s" is connected' % self.device.getName(),
                    'link': None
                }
            ]
            msgs.extend(BaseService.getMessages(self))
        else:
            msgs = [
                {
                    'level': 'ERROR',
                    'message': 'No storage device could be found that contains the "/photoframe/"-directory! '
                               'Try to reboot or manually mount the desired storage device to "%s"' % self.usbDir,
                    'link': None
                }
            ]
        return msgs

    def detectAllStorageDevices(self, onlyMounted=False, onlyUnmounted=False, reverse=False):
        candidates = []
        for root, dirs, files in os.walk('/sys/block/'):
            for device in dirs:
                result = debug.subprocess_check_output(['udevadm', 'info', '--query=property', '/sys/block/' + device])
                if result and 'ID_BUS=usb' in result:
                    values = {}
                    for line in result.split('\n'):
                        line = line.strip()
                        if line == '':
                            continue
                        k, v = line.split('=', 1)
                        values[k] = v
                    if 'DEVNAME' in values:
                        # Now, locate the relevant partition
                        result = debug.subprocess_check_output(['lsblk', '-bOJ', values['DEVNAME']])
                        if result is not None:
                            partitions = json.loads(result)['blockdevices'][0]['children']
                            for partition in partitions:
                                if partition['fstype'] in USB_Photos.SUPPORTED_FILESYSTEMS:
                                    # Final test
                                    if (partition['mountpoint'] is None and onlyMounted) \
                                      or (partition['mountpoint'] is not None and onlyUnmounted):
                                        continue

                                    # Convert this into candidate info
                                    candidate = USB_Photos.StorageUnit()
                                    candidate.setDevice(os.path.join(
                                        os.path.dirname(values['DEVNAME']), partition['name']))
                                    if partition['label'] is not None and partition['label'].strip() != '':
                                        candidate.setLabel(partition['label'].strip())
                                    candidate.setUUID(partition['uuid'])
                                    candidate.setSize(partition['size'])
                                    candidate.setFilesystem(partition['fstype'])
                                    candidate.setHotplug(partition['hotplug'] == '1')
                                    candidate.setMountpoint(partition['mountpoint'])
                                    candidate.setFreshness(values['USEC_INITIALIZED'])
                                    candidates.append(candidate)
        # Return a list with the freshest device first (ie, last mounted)
        candidates.sort(key=lambda x: x.freshness, reverse=True)
        return candidates

    def mountStorageDevice(self):
        if not os.path.exists(self.usbDir):
            cmd = ["mkdir", self.usbDir]
            try:
                debug.subprocess_check_output(cmd, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                logging.exception('Unable to create directory: %s' % cmd[-1])
                logging.error('Output: %s' % repr(e.output))

        candidates = self.detectAllStorageDevices(onlyUnmounted=True)

        # unplugging/replugging usb-stick causes system to detect it as a new storage device!
        for candidate in candidates:
            cmd = ['sudo', '-n', 'mount', candidate.device, self.usbDir]
            try:
                debug.subprocess_check_output(cmd, stderr=subprocess.STDOUT)
                logging.info("USB-device '%s' successfully mounted to '%s'!" % (cmd[-2], cmd[-1]))
                if os.path.exists(self.baseDir):
                    self.device = candidate
                    # Invalidate cache when new device is mounted
                    self.invalidate_cache()
                    self.checkForInvalidKeywords()
                    return True
            except subprocess.CalledProcessError as e:
                logging.warning('Unable to mount storage device "%s" to "%s"!' % (candidate.device, self.usbDir))
                logging.warning('Output: %s' % repr(e.output))
            self.unmountBaseDir()

        logging.debug("unable to mount any storage device to '%s'" % (self.usbDir))
        return False

    def unmountBaseDir(self):
        cmd = ['sudo', '-n', 'umount', self.usbDir]
        try:
            debug.subprocess_check_output(cmd, stderr=subprocess.STDOUT)
            # Invalidate cache when device is unmounted
            self.invalidate_cache()
        except subprocess.CalledProcessError:
            logging.debug("unable to UNMOUNT '%s'" % self.usbDir)

    # All images directly inside '/photoframe' directory will be displayed without any keywords
    def getBaseDirImages(self):
        if not os.path.exists(self.baseDir):
            return []
        
        files, _ = self._cache_directory_scan(self.baseDir)
        return [filename for _, filename in files]

    def getAllAlbumNames(self):
        if not os.path.exists(self.baseDir):
            return []
        
        _, dirs = self._cache_directory_scan(self.baseDir)
        return [dirname for _, dirname in dirs]

    def selectImageFromAlbum(self, destinationDir, supportedMimeTypes, displaySize, randomize):
        if self.device is None:
            return BaseService.createImageHolder(self) \
              .setError('No external storage device detected! '
                        'Please connect a USB-stick!\n\n Place albums inside /photoframe/{album_name} directory and '
                        'add each {album_name} as keyword.\n\nAlternatively, put images directly inside the '
                        '"/photoframe/"-directory on your storage device.')

        result = BaseService.selectImageFromAlbum(self, destinationDir, supportedMimeTypes, displaySize, randomize)
        if result is not None:
            return result

        if os.path.exists(self.usbDir):
            return BaseService.createImageHolder(self) \
              .setError('No images could be found on storage device "%s"!\n\n'
                        'Please place albums inside /photoframe/{album_name} directory and add each {album_name} '
                        'as keyword.\n\nAlternatively, put images directly inside the '
                        '"/photoframe/"-directory on your storage device.' % self.device.getName())
        else:
            return BaseService.createImageHolder(self) \
              .setError('No external storage device detected! Please connect a USB-stick!\n\n'
                        'Place albums inside /photoframe/{album_name} directory and add each {album_name} as keyword.'
                        '\n\nAlternatively, put images directly inside the "/photoframe/"-directory '
                        'on your storage device.')

    def getImagesFor(self, keyword):
        if not os.path.isdir(self.baseDir):
            return []
        
        images = []
        if keyword == "_PHOTOFRAME_":
            # Use cached base directory files (already sorted by date)
            files, _ = self._cache_directory_scan(self.baseDir)
            file_names = [filename for _, filename in files]
            images = self.getAlbumInfo(self.baseDir, file_names, pre_sorted=True)
        else:
            album_path = os.path.join(self.baseDir, keyword)
            if os.path.isdir(album_path):
                # Cache album directory contents
                files, _ = self._cache_directory_scan(album_path)
                file_names = [filename for _, filename in files]
                images = self.getAlbumInfo(album_path, file_names, pre_sorted=True)
            else:
                logging.warning(
                  "The album '%s' does not exist. Did you unplug "
                  "the storage device associated with '%s'?!" % (album_path, self.device)
                )
        return images

    def getAlbumInfo(self, path, files, pre_sorted=False):
        images = []
        max_images = 200
        
        if pre_sorted:
            # Files are already sorted by modification time, apply weighted selection
            selected_files = self.weighted_random_selection(files, max_images)
        else:
            # Fallback to random selection for compatibility
            selected_files = random.sample(files, min(max_images, len(files)))
        
        for filename in selected_files:
            fullFilename = os.path.join(path, filename)
            
            # Quick existence check first
            if not os.path.exists(fullFilename):
                logging.warning('File %s does not exist, skipping', fullFilename)
                continue
                
            item = BaseService.createImageHolder(self)
            item.setId(self.hashString(fullFilename))
            item.setUrl(fullFilename).setSource(fullFilename)
            item.setMimetype(helper.getMimetype(fullFilename))
            item.setFilename(filename)
            item.allowCache(False)  # Disable caching for USB images
            images.append(item)
            
        return images

    def requestUrl(self, url, destination=None, params=None, data=None, usePost=False):
        # pretend to download the file (for compatability with 'selectImageFromAlbum' of baseService)
        # instead just cache a scaled version of the file and return {status: 200}
        result = RequestResult()

        filename = url
        recSize = None

        if destination is None or not os.path.isfile(filename):
            result.setResult(RequestResult.SUCCESS).setHTTPCode(400)
        elif recSize is not None and helper.scaleImage(filename, destination, recSize):
            result.setFilename(destination)
            result.setResult(RequestResult.SUCCESS).setHTTPCode(200)
        elif helper.copyFile(filename, destination):
            result.setFilename(destination)
            result.setResult(RequestResult.SUCCESS).setHTTPCode(200)
        else:
            result.setResult(RequestResult.SUCCESS).setHTTPCode(418)
        return result