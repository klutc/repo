"""
    Plugin for ResolveURL
    Copyright (C) 2025 gujal

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
import requests
import xbmc
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class AbstreamResolver(ResolveUrl):
    name = 'Abstream'
    domains = ['abstream.to']
    pattern = r'(?://|\.)(abstream\.to)/(?:embed-)?([0-9a-zA-Z]+)'

    _UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
           'AppleWebKit/537.36 (KHTML, like Gecko) '
           'Chrome/124.0.0.0 Safari/537.36')

    def get_media_url(self, host, media_id):
        embed_url = self.get_url(host, media_id)

        s = requests.Session()
        s.headers.update({'User-Agent': self._UA})

        # Fetch the embed page.
        # filmizip.com е пръв — запазва съществуващото поведение за filmi9.
        # Ако отговорът не съдържа m3u8, опитваме zenoplay.to като fallback.
        _referers = ['https://filmizip.com/', 'https://zenoplay.to/']
        html = None
        _last_status = None
        for _ref in _referers:
            _r = s.get(embed_url, headers={'Referer': _ref}, timeout=15, verify=False)
            _last_status = _r.status_code
            if _r.ok:
                _candidate = _r.text
                if re.search(r'\.m3u8', _candidate):
                    html = _candidate
                    break
                if html is None:
                    html = _candidate   # запази като последен успешен отговор
        if html is None:
            raise ResolverError('Abstream embed page failed (status %s)' % _last_status)

        # Extract the HLS m3u8 URL — try the tight pattern first, then a loose fallback
        m = re.search(r'sources\s*:\s*\[\{file:"([^"]+\.m3u8[^"]*)"', html)
        if not m:
            # Some player setups use spaces or other properties before "file"
            m = re.search(r'["\']?file["\']?\s*:\s*"([^"]+\.m3u8[^"]*)"', html)
        if not m:
            raise ResolverError('No m3u8 source found on abstream.to')
        m3u8_url = m.group(1)
        xbmc.log('Abstream: m3u8_url = [%s]' % m3u8_url, xbmc.LOGINFO)

        sub_playlist_url = ''

        # ── Approach 1: EXT-X-MEDIA:TYPE=SUBTITLES inside the master m3u8 ───
        # This is the canonical place for HLS subtitle tracks.
        r2 = s.get(m3u8_url, headers={'Referer': embed_url}, timeout=10, verify=False)
        if r2.ok:
            ms = re.search(r'#EXT-X-MEDIA:TYPE=SUBTITLES[^\n]*URI="([^"]+)"', r2.text)
            if ms:
                raw_uri = ms.group(1)
                # Resolve relative URIs against the m3u8 base path
                if raw_uri.startswith('http'):
                    sub_playlist_url = raw_uri
                else:
                    from six.moves.urllib_parse import urljoin
                    base = m3u8_url.split('?')[0].rsplit('/', 1)[0] + '/'
                    sub_playlist_url = urljoin(base, raw_uri)
                xbmc.log('Abstream: subtitle from m3u8 EXT-X-MEDIA = %s' % sub_playlist_url,
                         xbmc.LOGDEBUG)
        else:
            xbmc.log('Abstream: m3u8 fetch failed: %s' % r2.status_code, xbmc.LOGDEBUG)

        # ── Approach 2: JWPlayer tracks array in the embed page HTML ─────────
        # Fallback for hosts that don't embed subtitles in the m3u8.
        # Only accept absolute URLs — relative paths like /srt/empty.srt are placeholders.
        if not sub_playlist_url:
            for block in re.finditer(r'\{[^{}]{0,800}\}', html, re.DOTALL):
                blk = block.group(0)
                if not re.search(r'(?:captions|subtitles)', blk, re.IGNORECASE):
                    continue
                fm = re.search(r'["\']?file["\']?\s*:\s*["\']([^"\']+)["\']', blk)
                if fm and fm.group(1).startswith('http'):
                    sub_playlist_url = fm.group(1)
                    xbmc.log('Abstream: subtitle from HTML tracks = %s' % sub_playlist_url,
                             xbmc.LOGDEBUG)
                    break

        # Build Kodi-compatible play URL with pipe headers
        play_headers = {
            'User-Agent': self._UA,
            'Referer': 'https://abstream.to/',
        }
        play_url = m3u8_url + helpers.append_headers(play_headers)
        xbmc.log('Abstream: sub_playlist_url = [%s]' % sub_playlist_url, xbmc.LOGINFO)

        if sub_playlist_url:
            return play_url, sub_playlist_url   # tuple → PLAY() downloads subtitles
        return play_url

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id,
                                     template='https://abstream.to/embed-{media_id}.html')
