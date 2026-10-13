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
    name = 'PlayHost'
    domains = ['playhost.cc', 'kinofen.xyz', 'ww2.playhost.cc', 'vip.playhost.cc']
    pattern = r'(?://|\.)((?:playhost|kinofen|ww2.playhost|vip.playhost)\.(?:cc|xyz))/(?:e|d|embed)/([0-9a-zA-Z_?,-]+)'

    def get_media_url(self, host, media_id):
        link = self.get_url(host, media_id)
        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        headers = {'User-Agent': UA}

        s = requests.Session()

        r = s.get(link, headers=headers)
        data = r.text.replace('\/', '/')

        match_api = re.search('apiURL":"(.+?)"', data)

        if match_api:
            match_query = re.search('apiQuery":"(.+?)"', data)
            if match_query:
                api_link = match_api.group(1) + 'api/?' + match_query.group(1)

                r_api = s.get(api_link, headers=headers)
                data_api = r_api.text.replace('\/', '/')

                match_url = re.search('"sources".+?"file":"(.+?)"', data_api)

                if match_url:
                    play_url = match_url.group(1)+'|User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36;sec-ch-ua-platform="Windows"'
                else:
                    play_url = ''

                match_sub = re.search('"tracks".+?"file":"(.+?)"', data_api)
                if match_sub:
                    sub_url = match_sub.group(1)
                else:
                    sub_url = ''
            else:
                play_url = ''
                sub_url = ''
        else:
            play_url = ''
            sub_url = ''

        play_sub = [play_url, sub_url]
        return play_sub

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/embed/{media_id}')
