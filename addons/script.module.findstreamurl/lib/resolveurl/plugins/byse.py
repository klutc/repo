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

import json
from six.moves import urllib_parse
from resolveurl.lib import helpers
from resolveurl.lib.aesgcm import python_aesgcm
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class ByseResolver(ResolveUrl):
    name = 'Byse'
    domains = [
        'f16px.com', 'bysesayeveum.com', 'bysetayico.com', 'bysevepoin.com', 'bysezejataos.com',
        'bysekoze.com', 'bysesukior.com', 'bysejikuar.com', 'bysefujedu.com', 'bysedikamoum.com',
        'bysebuho.com', "byse.sx", 'filemoon.sx', 'filemoon.to', 'filemoon.in', 'filemoon.link', 'filemoon.nl',
        'filemoon.wf', 'cinegrab.com', 'filemoon.eu', 'filemoon.art', 'moonmov.pro', '96ar.com',
        'kerapoxy.cc', 'furher.in', '1azayf9w.xyz', '81u6xl9d.xyz', 'smdfs40r.skin', 'c1z39.com',
        'bf0skv.org', 'z1ekv717.fun', 'l1afav.net', '222i8x.lol', '8mhlloqo.fun', 'f51rm.com',
        'xcoic.com', 'boosteradx.online', 'streamlyplayer.online', 'bysewihe.com'
    ]
    pattern = r'(?://|\.)((?:filemoon|cinegrab|moonmov|kerapoxy|furher|1azayf9w|81u6xl9d|f16px|' \
              r'smdfs40r|bf0skv|z1ekv717|l1afav|222i8x|8mhlloqo|96ar|xcoic|f51rm|c1z39|boosteradx|' \
              r'byse(?:sayeveum|tayico|vepoin|zejataos|koze|sukior|jikuar|fujedu|dikamoum|buho|wihe)?)' \
              r'\.(?:sx|to|s?k?in|link|nl|wf|com|eu|art|pro|cc|xyz|org|fun|net|lol|online))' \
              r'/(?:(?:e|d|download)/)?([0-9a-zA-Z]+)'

    def get_media_url(self, host, media_id):
        web_url = self.get_url(host, media_id)
        ref = urllib_parse.urljoin(web_url, '/')
        headers = {
            'User-Agent': common.FF_USER_AGENT,
            'Referer': ref,
            'Origin': 'https://' + host,
        }
        fp_data = self.fp(16, 0.6, 0.9)

        # --- Try new embed endpoint first (/embed/playback) ---
        html = None
        embed_api = 'https://{}/api/videos/{}/embed/playback'.format(host, media_id)
        embed_hdrs = dict(headers)
        embed_hdrs.update({
            'X-Embed-Origin': 'https://filmizip.com',
            'X-Embed-Referer': 'https://filmizip.com/',
            'X-Embed-Parent': 'https://filmizip.com',
        })
        try:
            resp = self.net.http_POST(embed_api, headers=embed_hdrs, form_data=fp_data, jdata=True).content
            html = json.loads(resp)
            # Verify it's a valid embed response (has playback or sources)
            if not isinstance(html, dict) or (not html.get('playback') and not html.get('sources')):
                html = None
        except Exception:
            html = None

        # --- Fall back to old /playback endpoint ---
        if html is None:
            try:
                resp = self.net.http_POST(web_url, headers=headers, form_data=fp_data, jdata=True).content
                html = json.loads(resp)
            except Exception as e:
                raise ResolverError('Byse request failed: %s' % e)

        sources = html.get('sources')
        if sources:
            sources = [(x.get('label'), x.get('url')) for x in sources]
            uri = helpers.pick_source(helpers.sort_sources_list(sources))
            if uri.startswith('/'):
                uri = urllib_parse.urljoin(web_url, uri)
            url = helpers.get_redirect_url(uri, headers=headers)
            return url + helpers.append_headers(headers)

        pd = html.get('playback')
        if pd:
            iv = self.ft(pd.get('iv'))
            version = pd.get('version')
            key_parts = pd.get('key_parts', [])
            if version is not None and key_parts:
                key = self.xn_versioned(key_parts, version)
            else:
                key = self.xn(key_parts)
            pl = self.ft(pd.get('payload'))
            cipher = python_aesgcm.new(key)
            ct = cipher.open(iv, pl)
            if ct is None:
                raise ResolverError('Playback decryption failed')
            ct = json.loads(ct.decode('latin-1'))
            sources = ct.get('sources')
            if sources:
                sources = [(x.get('label'), x.get('url')) for x in sources]
                uri = helpers.pick_source(helpers.sort_sources_list(sources))
                # Return with subtitle track if present
                tracks = ct.get('tracks', [])
                sub_url = ''
                for track in tracks:
                    if track.get('kind') in ('subtitles', 'captions') and track.get('src'):
                        sub_url = track['src']
                        break
                # tracks[] is often empty — fall back to EXT-X-MEDIA in master m3u8
                if not sub_url:
                    try:
                        import requests as _req
                        import re as _re
                        r_m3u8 = _req.get(uri,
                                          headers={'User-Agent': common.FF_USER_AGENT,
                                                   'Referer': 'https://' + host + '/'},
                                          timeout=8, verify=False)
                        if r_m3u8.ok:
                            ms = _re.search(
                                r'#EXT-X-MEDIA:TYPE=SUBTITLES[^\n]*URI="([^"]+)"',
                                r_m3u8.text)
                            if ms:
                                sub_url = ms.group(1)
                    except Exception:
                        pass
                play_url = uri + helpers.append_headers(headers)
                if sub_url:
                    return play_url, sub_url
                return play_url

        raise ResolverError('Video Link Not Found')

    def get_url(self, host, media_id):
        redirect_domains = ['boosteradx.online', 'byse.sx']
        if host in redirect_domains:
            host = 'streamlyplayer.online'
        return self._default_get_url(host, media_id, 'https://{host}/api/videos/{media_id}/playback')

    def _embed_url(self, host, media_id):
        """Embed-mode page URL (used as Referer for the player page)."""
        return 'https://{}/e/{}'.format(host, media_id)

    @staticmethod
    def ft(e):
        t = e.replace('-', '+').replace('_', '/')
        return helpers.b64decode(t, binary=True)

    def xn(self, e):
        t = list(map(self.ft, e))
        return b''.join(t)

    @staticmethod
    def xn_versioned(key_parts, version):
        """Select key_parts by version using the server's Ga() index table.

        Ga()[v] = [v, 31-v]  (1-based) → 0-based [v-1, 30-v]
        The two selected parts are decoded and concatenated to form the AES-256 key.
        Falls back to concatenating all parts if version is out of range.
        """
        decoded = [ByseResolver.ft(kp) for kp in key_parts]
        try:
            v = int(str(version).strip())
        except (ValueError, TypeError):
            v = None
        if (v is not None and 1 <= v <= 20
                and len(decoded) > 30 - v and len(decoded) > v - 1):
            k1 = decoded[v - 1]
            k2 = decoded[30 - v]
            combined = k1 + k2
            if len(combined) in (16, 32):   # valid AES-128 or AES-256 key
                return combined
        # Fallback: original concatenation (works for old-format responses)
        return b''.join(decoded)

    @staticmethod
    def fp(x, y, z):
        from binascii import hexlify
        from hashlib import sha256
        from os import urandom
        from time import time
        from random import uniform
        v_id = hexlify(urandom(x)).decode()
        d_id = hexlify(urandom(x)).decode()
        ctime = int(time())
        t_data = {
            'viewer_id': v_id,
            'device_id': d_id,
            'confidence': round(uniform(y, z), 2),
            'iat': ctime,
            'exp': ctime + 600
        }
        t_bdata = helpers.b64urlencode(json.dumps(t_data), strip=True)
        t_sig = helpers.b64urlencode(sha256(t_bdata.encode()).digest(), strip=True)
        token = '{0}.{1}'.format(t_bdata, t_sig)
        t_data.update({'token': token})
        t_data.pop('iat')
        t_data.pop('exp')
        return {'fingerprint': t_data}
