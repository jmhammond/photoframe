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
import os
import json
import logging
import random
from .path import path


class settings:
    DEPRECATED_USER = ['resolution']
    DEPRECATED_SYSTEM = ['colortemp-script', 'local-ip']

    def __init__(self):
        self.settings = {
            'oauth_token': None,
            'oauth_state': None,
            'tempfolder': '/tmp/',
            'colortemp': None,
            'cfg': None
        }
        self.userDefaults()

    def userDefaults(self):
        self.settings['cfg'] = {
            'width': 1920,
            'height': 1080,
            'depth': 32,
            'tvservice': 'DMT 82 DVI',
            'timezone': '',
            'interval': 60,					# Delay in seconds between images (minimum)
            'display-off': 22,				# What hour (24h) to disable display and sleep
            'display-on': 4,					# What hour (24h) to enable display and continue
            # After how many hours we should force reload of image lists from server (zero means when all is shown)
            'refresh': 0,
            'autooff-lux': 0.01,
            'autooff-time': 0,
            'powersave': '',
            'shutdown-pin': 3,
            'display-driver': 'none',
            'display-special': None,
            'imagesizing': 'blur',
            'force_orientation': 0,
            'randomize_images': 1,
            'enable-cache': 1,
            # wait = wait for network, ignore = try next (rely on cache or non-internet connections)
            'offline-behavior': 'wait',
            'decay_factor':0.003,
        }

    def load(self):
        if os.path.exists(path.CONFIGFILE):
            with open(path.CONFIGFILE) as f:
                try:
                    # A bit messy, but it should allow new defaults to be added
                    # to old configurations.
                    tmp = self.settings['cfg']
                    self.settings = json.load(f)
                    tmp2 = self.settings['cfg']
                    self.settings['cfg'] = tmp
                    self.settings['cfg'].update(tmp2)

                    if 'refresh-content' in self.settings['cfg']:
                        self.settings['cfg']['refresh'] = self.settings['cfg']['refresh-content']
                        self.settings['cfg'].pop('refresh-content', None)

                    # Remove deprecated fields
                    for field in settings.DEPRECATED_USER:
                        self.settings['cfg'].pop(field, None)
                    for field in settings.DEPRECATED_SYSTEM:
                        self.settings.pop(field, None)

                    # Also, we need to iterate the settings and make sure numbers and floats are
                    # that, and not strings (which the old version did)
                    for k in self.settings['cfg']:
                        self.settings['cfg'][k] = self.convertToNative(self.settings['cfg'][k])
                    # Lastly, correct the tvservice field, should be "TEXT NUMBER TEXT"
                    # This is a little bit of a cheat
                    parts = self.settings['cfg']['tvservice'].split(' ')
                    if (
                        len(parts) == 3 and
                        type(self.convertToNative(parts[1])) != int and
                        type(self.convertToNative(parts[2])) == int
                    ):
                        logging.debug('Reordering tvservice value due to old bug')
                        self.settings['cfg']['tvservice'] = "%s %s %s" % (parts[0], parts[2], parts[1])
                        self.save()
                except Exception:
                    logging.exception('Failed to load settings.json, corrupt file?')
                    return False
            # make sure old settings.json files are still compatible and get updated with new keys
            if "cachefolder" not in list(self.settings.keys()):
                self.settings["cachefolder"] = path.CACHEFOLDER
            return True
        else:
            return False

    def save(self):
        with open(path.CONFIGFILE, 'w') as f:
            json.dump(self.settings, f)

    def convertToNative(self, value):
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except Exception:
            return value

    def setUser(self, key, value):
        self.settings['cfg'][key] = self.convertToNative(value)

    def getUser(self, key=None):
        if key is None:
            return self.settings['cfg']

        if key in self.settings['cfg']:
            return self.settings['cfg'][key]
        logging.warning('Trying to access non-existent user config key "%s"' % key)
        try:
            a = 1 / 0
            a += 1
        except Exception:
            logging.exception('Where did this come from??')
        return None

    def addKeyword(self, keyword):
        if keyword is None:
            return False
        keyword = keyword.strip()
        if keyword not in self.settings['cfg']['keywords']:
            self.settings['cfg']['keywords'].append(keyword.strip())
            return True
        return False

    def removeKeyword(self, id):
        if id < 0 or id >= len(self.settings['cfg']['keywords']):
            return False
        self.settings['cfg']['keywords'].pop(id)
        if len(self.settings['cfg']['keywords']) == 0:
            self.addKeyword('')
        return True

    def getKeyword(self, id=None):
        if id is None:
            rnd = random.SystemRandom().randint(0, len(self.settings['cfg']['keywords'])-1)
            return rnd  # self.settings['cfg']['keywords'][rnd]
        elif id >= 0 and id < len(self.settings['cfg']['keywords']):
            return self.settings['cfg']['keywords'][id]
        else:
            return None

    def countKeywords(self):
        return len(self.settings['cfg']['keywords'])

    def set(self, key, value):
        self.settings[key] = self.convertToNative(value)

    def delete(self, key, userField=False):
        if userField:
            if key in self.settings['cfg']:
                del self.settings['cfg'][key]
        else:
            if key in self.settings:
                del self.settings[key]

    def get(self, key):
        if key == 'colortemp-script':
            return path.COLORMATCH
        if key in self.settings:
            return self.settings[key]
        logging.warning('Trying to access non-existent config key "%s"' % key)
        return None
