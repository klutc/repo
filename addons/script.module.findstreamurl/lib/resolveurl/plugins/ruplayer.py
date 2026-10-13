"""
    Plugin for ResolveURL
    Handles ruplayer.org and spxplayer.org (same FirePlayer under a new domain, 2026.09.25.03)
    - custom FirePlayer used on zenoplay.to and similar sites. API and embed go to the host of the link.

    Flow:
      1. Fetch embed page (https://ruplayer.org/video/{hash}) to get subtitle URL
         from the playerjsSubtitle JS variable.
      2. POST to /player/index.php?data={hash}&do=getVideo to get the HLS source.
      3. Return (m3u8_url + pipe-headers, subtitle_url) or just m3u8_url.
"""

import json
import re
import requests
import xbmc
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class RuplayerResolver(ResolveUrl):
    name = 'RuPlayer'
    domains = ['ruplayer.org', 'spxplayer.org']
    pattern = r'(?://|\.)(ruplayer\.org|spxplayer\.org)/video/([0-9a-f]+)'

    _UA = common.FF_USER_AGENT

    def get_media_url(self, host, media_id):
        embed_url = self.get_url(host, media_id)

        s = requests.Session()
        s.headers.update({'User-Agent': self._UA})

        # --- 1. Fetch embed page and extract subtitle URL ---
        sub_url = ''
        try:
            r_embed = s.get(embed_url,
                            headers={'Referer': 'https://zenoplay.to/'},
                            timeout=15, verify=False)
            html = r_embed.text

            # playerjsSubtitle = "[Bulgarian]https://cdn.example.com/sub.html"
            m_sub = re.search(r'var\s+playerjsSubtitle\s*=\s*"([^"]+)"', html)
            if m_sub:
                m_url = re.search(r'(https?://\S+)', m_sub.group(1))
                if m_url:
                    sub_url = m_url.group(1)
                    xbmc.log('RuPlayer: subtitle = %s' % sub_url, xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('RuPlayer: embed fetch error: %s' % e, xbmc.LOGINFO)

        # --- 2. Call API for video source ---
        api_url = 'https://{}/player/index.php?data={}&do=getVideo'.format(host, media_id)
        api_headers = {
            'Referer': embed_url,
            'Origin': 'https://{}'.format(host),
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        # r = document.referrer from within the iframe (zenoplay.to page)
        api_data = 'hash={}&r=https%3A%2F%2Fzenoplay.to%2F'.format(media_id)

        try:
            resp = s.post(api_url, headers=api_headers, data=api_data, timeout=15, verify=False)
            jdata = json.loads(resp.text)
        except Exception as e:
            raise ResolverError('RuPlayer API error: %s' % e)

        # securedLink is a time-limited signed m3u8; videoSource is the plain path
        video_url = jdata.get('securedLink') or jdata.get('videoSource')
        if not video_url:
            raise ResolverError('RuPlayer: no video source in API response')

        xbmc.log('RuPlayer: video = %s' % video_url, xbmc.LOGINFO)

        # securedLink е self-authenticated (md5+expires в URL-а) —
        # не са нужни pipe-headers. Sub-playlist и сегментите са
        # достъпни без Referer.
        if sub_url:
            return video_url, sub_url
        return video_url

    def get_url(self, host, media_id):
        return 'https://{}/video/{}'.format(host, media_id)
