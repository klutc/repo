"""
    Plugin for ResolveUrl
    Copyright (C) 2023 shellc0de, gujal

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import json
import re
from six.moves import urllib_parse
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError
import requests
import xbmcgui

#https://iceyfile.com/video/embed/4fc40f2ced640989/640x320/Wall.To.Wall.2025.720p.WEBRip.x264.AAC.mp4
class IceyFileResolver(ResolveUrl):
    name = 'IceyFile'
    domains = ['iceyfile.com', 'iceyfile.net']
    pattern = r'(?://|\.)((?:iceyfile)\.(?:com|net))/(video)/(embed)/([0-9a-zA-Z]+)/([0-9a-zA-Zx]+)/([0-9a-zA-Z$:/.]+)'

    def get_media_url(self, host, media_id):
        web_url = self.get_url(host, media_id)

        if web_url.endswith('/'):
            web_url = web_url[:-1]

        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        s = requests.Session()

        headers = {'user-agent': UA}

        r = s.get(web_url, headers=headers, allow_redirects=False)

        data = r.text

        match = re.search(r'<source src="(.+?)"', data, re.DOTALL)

        if match:
            play_url = match.group(1)
        else:
            play_url = 'http://notreeltube'

        return play_url

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='{host}/{media_id}')
