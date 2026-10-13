"""
    Plugin for ResolveURL — PlayerP2P / VidPlay
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

    Handles:
      https://vidz.playerp2p.com/#VIDEO_ID
      https://vidstream.uns.bio/#VIDEO_ID

    Both use AES-128-CBC to protect the /api/v1/video?id= response (hex-encoded).
    Key/IV are derived from the player JS for https: protocol with a hash-based URL:
      Key = TextEncoder("kiemtienmua911ca")   → 16 bytes
      IV  = TextEncoder("1234567890oiuytr")   → 16 bytes  (when window.location.hash != "")
"""

import json
import re
from six.moves import urllib_parse
from resolveurl.lib.pyaes import AESModeOfOperationCBC
from resolveurl.lib.pyaes.util import strip_PKCS7_padding
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class PlayerP2PResolver(ResolveUrl):
    name = 'PlayerP2P'
    domains = ['vidz.playerp2p.com', 'vidstream.uns.bio']
    pattern = (r'(?://|\.)((?:vidz\.playerp2p\.com|vidstream\.uns\.bio))'
               r'/#([0-9a-zA-Z]+)')

    # AES-128-CBC key and IV — derived from the obfuscated player JS
    # (valid for https: protocol with hash-based video URLs)
    _KEY = b'kiemtienmua911ca'
    _IV  = b'1234567890oiuytr'

    def get_media_url(self, host, media_id):
        web_url = 'https://{}/#{}' .format(host, media_id)
        api_url = 'https://{}/api/v1/video?id={}'.format(host, media_id)
        headers = {
            'User-Agent': common.FF_USER_AGENT,
            'Referer': web_url,
            'Origin': 'https://' + host,
        }
        resp = self.net.http_GET(api_url, headers=headers).content
        resp = resp.strip()

        if not re.match(r'^[0-9a-fA-F]+$', resp):
            raise ResolverError('Unexpected PlayerP2P API response')

        # Hex → bytes
        ciphertext = bytes.fromhex(resp)

        # AES-128-CBC decrypt block-by-block, then strip PKCS7 padding
        aes = AESModeOfOperationCBC(self._KEY, iv=self._IV)
        plaintext = b''
        for i in range(0, len(ciphertext), 16):
            plaintext += aes.decrypt(ciphertext[i:i + 16])
        plaintext = strip_PKCS7_padding(plaintext)

        try:
            data = json.loads(plaintext.decode('utf-8', errors='replace'))
        except Exception:
            raise ResolverError('PlayerP2P JSON parse failed')

        source = data.get('source', '')
        if not source:
            raise ResolverError('No source URL in PlayerP2P response')

        # Append Kodi-style pipe headers so the CDN lets Kodi play the stream.
        # verifypeer=false is needed for bare-IP HTTPS CDN endpoints.
        play_headers = {
            'User-Agent': common.FF_USER_AGENT,
            'Referer': web_url,
            'Origin': 'https://' + host,
            'verifypeer': 'false',
        }
        source = urllib_parse.quote(source, safe='/:?=&!') + helpers.append_headers(play_headers)

        # Bulgarian subtitle (optional)
        sub_url = ''
        subtitle = data.get('subtitle') or {}
        if isinstance(subtitle, dict) and subtitle:
            bg = (subtitle.get('bg') or subtitle.get('Bulgarian')
                  or subtitle.get('bulgarian')
                  or next(iter(subtitle.values()), ''))
            if bg:
                if bg.startswith('/'):
                    bg = 'https://{}{}'.format(host, bg)
                sub_url = bg.split('#')[0]   # strip fragment like #bg

        if sub_url:
            return source, sub_url
        return source

    def get_url(self, host, media_id):
        return 'https://{}/#{}' .format(host, media_id)
