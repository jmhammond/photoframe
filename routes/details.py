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
import logging

from modules.helper import helper

from .baseroute import BaseRoute
from modules import debug


class RouteDetails(BaseRoute):
    def setupex(self, displaymgr, drivermgr, colormatch, slideshow, servicemgr, settings):
        self.displaymgr = displaymgr
        self.drivermgr = drivermgr
        self.colormatch = colormatch
        self.slideshow = slideshow
        self.servicemgr = servicemgr
        self.settings = settings

        self.void = open(os.devnull, 'wb')

        self.addUrl('/details/<about>')

    def handle(self, app, about):
        if about == 'tvservice':
            result = {}
            result['resolution'] = self.displaymgr.available()
            result['status'] = self.displaymgr.current()
            return self.jsonify(result)
        elif about == 'current':
            image, mime = self.displaymgr.get()
            response = app.make_response(image)
            response.headers.set('Content-Type', mime)
            return response
        elif about == 'drivers':
            result = list(self.drivermgr.list().keys())
            return self.jsonify(result)
        elif about == 'timezone':
            result = helper.timezoneList()
            return self.jsonify(result)
        elif about == 'version':
            output = debug.subprocess_check_output(['git', 'log', '-n1'], stderr=self.void)
            lines = output.split('\n')
            infoDate = lines[2][5:].strip()
            infoCommit = lines[0][7:].strip()
            output = debug.subprocess_check_output(['git', 'status'], stderr=self.void)
            lines = output.split('\n')
            infoBranch = lines[0][10:].strip()
            return self.jsonify({'date': infoDate, 'commit': infoCommit, 'branch': infoBranch})
        elif about == 'color':
            return self.jsonify(self.slideshow.getColorInformation())
        elif about == 'sensor':
            return self.jsonify({'sensor': self.colormatch.hasSensor()})
        elif about == 'display':
            return self.jsonify({'display': self.displaymgr.isEnabled()})
        elif about == 'network':
            return self.jsonify({'network': helper.hasNetwork()})
        elif about == 'hardware':
            output = ''
            try:
                output = debug.subprocess_check_output(['/opt/vc/bin/vcgencmd', 'get_throttled'], stderr=self.void)
            except Exception:
                logging.exception('Unable to execute /opt/vc/bin/vcgencmd')
            if not output.startswith('throttled='):
                logging.error('Output from vcgencmd get_throttled has changed')
                output = 'throttled=0x0'
            try:
                h = int(output[10:].strip(), 16)
            except Exception:
                logging.exception('Unable to convert output from vcgencmd get_throttled')
            result = {
                'undervoltage': h & (1 << 0 | 1 << 16) > 0,
                'frequency': h & (1 << 1 | 1 << 17) > 0,
                'throttling': h & (1 << 2 | 1 << 18) > 0,
                'temperature': h & (1 << 3 | 1 << 19) > 0
            }
            return self.jsonify(result)
        elif about == 'messages':
            # This should be made more general purpose since other parts need similar service
            msgs = []
            images = self.servicemgr.getTotalImageCount
            timeneeded = images * self.settings.getUser('interval')
            timeavailable = self.settings.getUser('refresh') * 3600
            if timeavailable > 0 and timeneeded > timeavailable:
                msgs.append({
                    'level': 'WARNING',
                    'message': 'Change every %d seconds with %d images will take %dh, refresh keywords is %dh' % (
                        self.settings.getUser('interval'), images, timeneeded/3600, timeavailable/3600
                    ),
                    'link': None})

            return self.jsonify(msgs)
        self.setAbort(404)
