"""
    Plugin for ResolveURL
    Handles morencius.com - VidHide player (ZenoPlay "Player 1" for TV shows).

    Flow:
      1. Fetch embed page (Referer zenoplay.to).
      2. Unpack eval(function(p,a,c,k,e,d){...}) block using jsunpack.
      3. var links={hls2,hls3,hls4}: hls2 first, then hls3; hls4 (/stream/ on morencius.com)
         only as a last resort - on 25.09.2026 it did not answer within 20 s.
      4. tracks: Bulgarian captions (.vtt) -> returned as (play_url, sub_url).
"""

import json
import re
import requests
import xbmc
from six.moves import urllib_parse
from resolveurl.lib import helpers, jsunpack
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class MorenciusResolver(ResolveUrl):
    name = 'Morencius'
    domains = ['morencius.com']
    pattern = r'(?://|\.)(morencius\.com)/embed/([0-9a-zA-Z]+)'

    _UA = common.FF_USER_AGENT
    _ORDER = ('hls2', 'hls3', 'hls4')

    def get_media_url(self, host, media_id):
        embed_url = self.get_url(host, media_id)
        origin = 'https://{}'.format(host)

        s = requests.Session()
        s.headers.update({'User-Agent': self._UA})

        r = s.get(embed_url, headers={'Referer': 'https://zenoplay.to/'}, timeout=15)
        html = r.text

        # --- Разпакетирай packed JS ---
        unpacked = ''
        try:
            unpacked = helpers.get_packed_data(html)
        except Exception:
            pass

        if 'links' not in unpacked:
            m_pack = re.search(
                r'(eval\s*\(function\s*\(p,a,c,k,e,d\)[\s\S]+?)\s*</script>',
                html, re.IGNORECASE)
            if m_pack and jsunpack.detect(m_pack.group(1)):
                try:
                    unpacked = jsunpack.unpack(m_pack.group(1))
                except Exception as e:
                    xbmc.log('Morencius: jsunpack error: %s' % e, xbmc.LOGINFO)

        if not unpacked:
            raise ResolverError('Morencius: could not unpack JS (HTTP %s)' % r.status_code)

        # --- var links={"hls2":...,"hls3":...,"hls4":...} ---
        links = {}
        m_links = re.search(r'var\s+links\s*=\s*(\{[^{}]*\})', unpacked)
        if m_links:
            try:
                links = json.loads(m_links.group(1))
            except ValueError:
                links = dict(re.findall(r'["\']?(hls\d)["\']?\s*:\s*["\']([^"\']+)["\']', m_links.group(1)))
        if not links:
            raise ResolverError('Morencius: var links not found')

        video_url = ''
        for key in self._ORDER:
            if links.get(key):
                video_url = urllib_parse.urljoin(origin + '/', links[key])
                xbmc.log('Morencius: %s = %s' % (key, video_url), xbmc.LOGINFO)
                break

        if not video_url:
            raise ResolverError('Morencius: no hls link (keys: %s)' % ','.join(sorted(links)))

        # --- Субтитри: track с kind captions/subtitles, Bulgarian ---
        sub_url = ''
        for blk in re.finditer(r'\{([^{}]{10,500})\}', unpacked):
            b = blk.group(1)
            if not re.search(r'kind\s*:\s*["\'](?:captions|subtitles)["\']', b, re.IGNORECASE):
                continue
            f_m = re.search(r'file\s*:\s*["\']([^"\']+)["\']', b, re.IGNORECASE)
            if not f_m:
                continue
            l_m = re.search(r'label\s*:\s*["\']([^"\']+)["\']', b, re.IGNORECASE)
            label = l_m.group(1) if l_m else ''
            sub_path = f_m.group(1)
            if 'bulgarian' in label.lower() or sub_path.lower().endswith('_bul.vtt'):
                sub_url = urllib_parse.urljoin(origin + '/', sub_path)
                xbmc.log('Morencius: subtitle = %s' % sub_url, xbmc.LOGINFO)
                break

        play_headers = {'User-Agent': self._UA, 'Referer': origin + '/', 'Origin': origin}
        play_url = video_url + helpers.append_headers(play_headers)

        if sub_url:
            return play_url, sub_url
        return play_url

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/embed/{media_id}')
