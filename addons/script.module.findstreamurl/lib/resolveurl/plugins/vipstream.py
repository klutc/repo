"""
    Plugin for ResolveURL
    Copyright (C) 2020 gujal

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

import re
import random
import string
import time
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError
import xbmcgui
import requests


class VipStreamResolver(ResolveUrl):
    name = 'VipStream'
    domains = ['vipstream.cc']
    pattern = r'(?://|\.)((?:vipstream)\.(?:cc))/([0-9a-zA-Z_?,-]+)'

    def get_media_url(self, host, media_id):
        web_url = self.get_url(host, media_id)
        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        s = requests.Session()
        headers_new = {'user-agent': UA}

        r = s.get(web_url, headers=headers_new)
        data = r.text

        match = re.search('sources.+?file:"(.+?)"', data)
        if match:
            play_url = match.group(1)
        else:
            play_url = ''

        return play_url

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://www.{host}/{media_id}.html')
