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

from resolveurl.plugins.__resolve_generic__ import ResolveGeneric
from resolveurl.lib import helpers
import re
import requests
import xbmcgui



class VudeoResolver(ResolveGeneric):
    name = 'Vudeo'
    domains = ['vudeo.net', 'vudeo.io', 'vudeo.co']
    pattern = r'(?://|\.)(vudeo\.(?:net|[ic]o))/(?:embed-)?([0-9a-zA-Z-]+)'

    def get_media_url(self, host, media_id):
        certpass = '|verifypeer=false&User-Agent=Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/76.0.3809.100 Safari/537.36&Referer=https://' + host + '/'

        link = self.get_url(host, media_id)

        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        headers = {'User-Agent': UA}

        s = requests.Session()

        r = s.get(link, headers=headers)

        data = r.text.replace('\/', '/')

        match_url = re.search(r'''sources:\s*\["(?P<url>[^"]+)''', data)

        if match_url:
            play_url = match_url.group(1) + certpass
        else:
            play_url = ''

        sub_url = ''

        play_sub = [play_url, sub_url]
        return play_sub

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/embed-{media_id}.html')
