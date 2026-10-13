"""
    Plugin for ResolveURL
    Copyright (C) 2020 gujal

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import re
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError
from six.moves import urllib_error
import requests
import xbmcgui
import codecs


class StreamTapeResolver(ResolveUrl):
    name = 'VidSrc'
    domains = ['api.vidsrc.top', 'play.vidsrc.top']
    pattern = r'(?://|\.)((?:api|play)\.vidsrc\.(?:top|top/myadmin))/([0-9a-zA-Z_?,-=.]+)'

    def get_media_url(self, host, media_id):
        if re.search('myadmin', media_id):
            link = self.get_play_url(host, media_id)
        else:
            link = self.get_url(host, media_id)
            link = link.replace('?', '?number=')

        UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'

        headers = {
            'User-Agent': UA,
            'referer': 'https://'+host+'/api.php'+media_id
        }

        s = requests.Session()

        r = s.get(link, headers=headers)
        data = r.text.replace('\/', '/').replace(' ', '')

        match_url = re.search('Link:</strong>(.+?)</p>', data)

        if match_url:
            play_url = match_url.group(1)

            match_sub = re.search('Subtitles:</strong>(.+?)</p>', data)

            if match_sub:
                sub_url = match_sub.group(1)
            else:
                sub_url = ''
        else:
            match_url = re.search('iframesrc=".+?file=(.+?)"', data)
            if match_url:
                sp_url = match_url.group(1).split('&subtitle')

                play_url = sp_url[0]
                play_url = play_url.replace('%3A', ':').replace('%2F', '/').replace('%3D', '=').replace('%3F', '?').replace('%26', '&')

                if len(sp_url) == 2:
                    sub_url_temp = sp_url[1]
                    sub_url_temp = sub_url_temp.replace('%3A', ':').replace('%2F', '/').replace('%3D', '=').replace('%3F', '?').replace('%26', '&')

                    pattern = r'http.*'
                    match_sub = re.search(pattern, sub_url_temp)

                    if match_sub:
                        sub_url = match_sub.group(0)
                    else:
                        sub_url = ''
                else:
                    sub_url = ''
            else:
                play_url = ''
                sub_url = ''



        play_sub = [play_url, sub_url]
        return play_sub

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/script.php{media_id}')

    def get_play_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/{media_id}')
