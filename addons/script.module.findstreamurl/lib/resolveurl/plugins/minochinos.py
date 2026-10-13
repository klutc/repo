"""
    Plugin for ResolveURL
    Handles minochinos.com - Bulgarian streaming site with JWPlayer + packed JS.

    Flow:
      1. Fetch embed page.
      2. Unpack eval(function(p,a,c,k,e,d){...}) block using jsunpack.
      3. Extract HLS m3u8 URL and optional subtitle URL.
"""

import re
import requests
import xbmc
from resolveurl.lib import helpers, jsunpack
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class MinochinosResolver(ResolveUrl):
    name = 'Minochinos'
    domains = ['minochinos.com']
    pattern = r'(?://|\.)(minochinos\.com)/embed/([0-9a-zA-Z]+)'

    _UA = common.FF_USER_AGENT

    def get_media_url(self, host, media_id):
        embed_url = self.get_url(host, media_id)

        s = requests.Session()
        s.headers.update({'User-Agent': self._UA})

        r = s.get(embed_url, headers={'Referer': 'https://zenoplay.to/'}, timeout=15, verify=False)
        html = r.text

        # --- Разпакетирай packed JS ---
        unpacked = ''

        # Стратегия 1: helpers.get_packed_data (търси eval(...) в HTML)
        try:
            unpacked = helpers.get_packed_data(html)
        except Exception:
            pass

        # Стратегия 2: директно намиране и jsunpack
        if not unpacked:
            m_pack = re.search(
                r'(eval\s*\(function\s*\(p,a,c,k,e,d\)[\s\S]+?)\s*</script>',
                html, re.IGNORECASE)
            if m_pack:
                block = m_pack.group(1)
                if jsunpack.detect(block):
                    try:
                        unpacked = jsunpack.unpack(block)
                    except Exception as e:
                        xbmc.log('Minochinos: jsunpack error: %s' % e, xbmc.LOGINFO)

        if not unpacked:
            raise ResolverError('Minochinos: could not unpack JS')

        xbmc.log('Minochinos: unpacked %d chars' % len(unpacked), xbmc.LOGINFO)

        # --- Намери HLS m3u8 URL ---
        video_url = ''
        # Търси ключ "hls" или директен m3u8 URL
        for pat in (
            r'"hls"\s*:\s*"(https?://[^"]+\.m3u8[^"]*)"',
            r'"(https?://[^"]+\.m3u8[^"]*)"',
            r"'(https?://[^']+\.m3u8[^']*)'",
        ):
            m = re.search(pat, unpacked)
            if m:
                video_url = m.group(1)
                break

        if not video_url:
            raise ResolverError('Minochinos: no m3u8 found')

        xbmc.log('Minochinos: video = %s' % video_url, xbmc.LOGINFO)

        # --- Намери subtitle URL ---
        # Търсим track обект с kind:"captions" или kind:"subtitles" в ЕДИН блок {}.
        # Thumbnail tracks (op=get_slides, .jpg) се пропускат.
        sub_url = ''
        for blk in re.finditer(r'\{([^{}]{10,500})\}', unpacked):
            b = blk.group(1)
            if not re.search(r'kind\s*:\s*["\'](?:captions|subtitles)["\']', b, re.IGNORECASE):
                continue
            f_m = re.search(r'file\s*:\s*["\']([^"\']+)["\']', b, re.IGNORECASE)
            if not f_m:
                continue
            sub_path = f_m.group(1)
            # Пропускай thumbnail/sprite URL-и
            if 'get_slides' in sub_path or sub_path.lower().endswith(('.jpg', '.png', '.webp')):
                continue
            sub_url = sub_path if sub_path.startswith('http') else 'https://minochinos.com' + sub_path
            xbmc.log('Minochinos: subtitle = %s' % sub_url, xbmc.LOGINFO)
            break

        play_headers = {'User-Agent': self._UA, 'Referer': embed_url}
        play_url = video_url + helpers.append_headers(play_headers)

        if sub_url:
            return play_url, sub_url
        return play_url

    def get_url(self, host, media_id):
        return 'https://minochinos.com/embed/{}'.format(media_id)
