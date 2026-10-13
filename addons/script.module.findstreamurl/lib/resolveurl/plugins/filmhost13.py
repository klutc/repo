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


class StreamTapeResolver(ResolveUrl):
    name = 'FilmHost13'
    domains = ['filmhost13.xyz']
    pattern = r'(?://|\.)((?:filmhost13)\.(?:xyz))/(?:video)/([0-9a-zA-Z_-]+)'

    def get_media_url(self, host, media_id):
        link = self.get_url(host, media_id)
        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        headers_new1 = {'User-Agent': UA, 'referer': 'https://' + host + '/'}

        s = requests.Session()
        r_sub = s.get(link, headers=headers_new1)
        data_sub = r_sub.text

        matchsub = re.search('playerjsSubtitle = "\[bg\](.+?),', data_sub)
        if matchsub:
            subtitles = matchsub.group(1).replace('\/', '/')
        else:
            matchsub2 = re.search('playerjsSubtitle = "\[bg\](.+?)"', data_sub)
            if matchsub2:
                subtitles = matchsub2.group(1).replace('\/', '/')
            else:
                subtitles = ''

        newlink_id_parse = link.split('/')
        newlink_id = newlink_id_parse[len(newlink_id_parse) - 1]
        newlink3 = 'https://filmhost13.xyz/player/index.php?data=' + newlink_id + '&do=getVideo'

        values = {'hash': newlink_id, 'r': 'https://' + host + '/'}
        headers_new1 = {'user-agent': UA,
                        'origin': 'https://filmhost13.xyz',
                        'x-requested-with': 'XMLHttpRequest'}

        r_new2 = s.post(newlink3, data=values, headers=headers_new1)
        data2 = r_new2.text

        matchplay = re.search('"securedLink":"(.+?)"', data2)
        if matchplay:
            play_url = matchplay.group(1).replace('\/', '/'), subtitles
        else:
            matchplay = re.search('"videoSource":"(.+?)"', data2)
            if matchplay:
                play_url = matchplay.group(1).replace('\/', '/'), subtitles
            else:
                play_url = '', ''

        return play_url

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/video/{media_id}')
