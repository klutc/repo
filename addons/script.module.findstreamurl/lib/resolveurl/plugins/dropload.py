"""
    Plugin for ResolveURL
    Copyright (C) 2022 shellc0de

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


class DropLoadResolver(ResolveGeneric):
    name = 'DropLoad'
    domains = ['dropload.io']
    pattern = r'(?://|\.)(dropload\.io)/(?:embed-|e/|d/)?([0-9a-zA-Z]+)'

    def get_media_url(self, host, media_id):
        certpass = '|Accept-Language=bg,en-US;q=0.9,en;q=0.8&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36'
        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        s = requests.Session()
        headers_new = {'user-agent': UA,
                       'Accept-Language': 'bg,en-US;q=0.9,en;q=0.8'}

        tsplit = self.get_url(host, media_id)

        r = s.get(tsplit, headers=headers_new)
        data = r.text

        find_srv01 = re.search('(srv\d\d)', data)
        srv01 = find_srv01.group(1)
        find_srv = re.search('(srv\d\d)\|sources', data)
        if find_srv:
            srv = find_srv.group(1)
        else:
            srv = srv01

        play_url = 'https://' + srv + '.dropload.io/hls2/'

        find_numbs = re.search('\|(\d\d\d\d\d)\|(\d\d)\|', data)
        if find_numbs:
            numb1 = find_numbs.group(2)
            numb2 = find_numbs.group(1)
        else:
            find_numb1 = re.search('\|(\d\d)\|', data)
            numb1 = find_numb1.group(1)
            find_numb2 = re.search('\|(\d\d\d\d\d)\|', data)
            numb2 = find_numb2.group(1)

        play_url = play_url + numb1 + '/' + numb2 + '/'

        find_token = re.search('\|master\|(.+?)\|', data)
        token = find_token.group(1)

        play_url = play_url + token + '/master.m3u8?t='

        check_tireta = re.search('\?t=.+?(--).+?s=', data)
        if check_tireta:
            tire = '--'
        else:
            tire = '-'

        find_btoken = re.search('\|sp.+?(\d\d\d\d\d)\|(.+?)\|m3u8', data)
        par_e = find_btoken.group(1)
        list_btoken = find_btoken.group(2).split('|')

        for t in range(0, len(list_btoken)):
            if t == 0:
                btoken = list_btoken[len(list_btoken) - 1]
            else:
                if t == 1:
                    btoken = btoken + tire + list_btoken[len(list_btoken) - (1 + t)]
                else:
                    btoken = btoken + '-' + list_btoken[len(list_btoken) - (1 + t)]

        play_url = play_url + btoken + '&s='

        find_par_s_f = re.search('\|(\d\d\d\d\d\d\d\d\d\d).+?(\d\d\d\d\d\d\d)', data)
        par_s = find_par_s_f.group(1)
        par_f = find_par_s_f.group(2)

        play_url = play_url + par_s + '&e=' + par_e + '&f=' + par_f

        find_p12 = re.search('p2\|p1', data)

        find_i = re.search(r'(&i=.+?)&', data)

        if find_i:
            param_i = find_i.group(1)
        else:
            param_i = '&i=0.0'

        if find_p12:
            play_url = play_url + '&srv=' + srv01 + param_i + '&sp=0' + '&p1=' + srv01 + '&p2=' + srv01
        else:
            play_url = play_url + param_i + '&sp=0'
        play_url = play_url

        return play_url



    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/embed-{media_id}.html')
