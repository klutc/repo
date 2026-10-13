"""
    Plugin for ResolveURL
    Handles vidsrc-embed.ru (ZenoPlay: /embed/movie/{tmdb}, /embed/tv/{tmdb}/{S}-{E}).
    Separate from vidsrc.py (that one is api.vidsrc.top / play.vidsrc.top only).

    Chain without a browser (11 requests, 25.09.2026):
      1. embed page (vidsrc-embed.ru -> 301 vidsrc.sh) -> data-api
      2. vs_src.php -> src on cloudorchestranova.com
      3. inner page -> window.CFG.playerUrl
      4. player page -> window.CONFIG (movie: api; tv: streamBase + season/episode)
         CONFIG.turnstile set -> ResolverError (no challenge solving)
      5. api.php (Referer/Origin cloudorchestranova) -> data.stream_urls = base64(nonce||ChaCha20) + vs.wasm_url
      6. wasm.php -> key read from the WASM by resolveurl.lib.vsdec (key AND layout change every 5 min;
         unknown structure -> VsDecError -> ResolverError, never a silent guess)
      7. generate.php on the stream host -> JWT (4 h, bound to the client IP /24) -> master m3u8
    Returns master url|User-Agent&Referer&Origin. Segments are TS served as page-N.html (text/html).
"""

import base64
import json
import re
import requests
import xbmc
from six.moves import urllib_parse
from resolveurl.lib import helpers, vsdec
from resolveurl.resolver import ResolveUrl, ResolverError


class VidSrcEmbedResolver(ResolveUrl):
    name = 'VidSrcEmbed'
    domains = ['vidsrc-embed.ru', 'vidsrc.sh']
    pattern = r'(?://|\.)(vidsrc-embed\.ru|vidsrc\.sh)/embed/((?:movie|tv)/[0-9a-zA-Z/_-]+)'

    _UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    _CO = 'https://cloudorchestranova.com'
    _T = 15
    _CHALLENGE = re.compile(r'challenges\.cloudflare\.com|turnstile|cf-chl|captcha|Just a moment', re.I)

    # imdb id from api.php (data.imdb_id) for the add-on's ListItem metadata, without changing the
    # resolve() contract: Window(10000) property. ZenoPlay clears it before resolve, reads and clears after.
    IMDB_PROP = 'findstreamurl.imdb'

    @classmethod
    def _publish_imdb(cls, raw):
        v = str(raw or '').strip()
        if v and not v.startswith('tt'):
            v = 'tt' + v
        if not re.match(r'^tt\d+$', v):
            return ''
        try:
            import xbmcgui
            xbmcgui.Window(10000).setProperty(cls.IMDB_PROP, v)
            xbmc.log('VidSrcEmbed: imdb = %s' % v, xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('VidSrcEmbed: imdb property not set: %s' % e, xbmc.LOGINFO)
            return ''
        return v

    def _get(self, s, step, url, **kw):
        kw.setdefault('timeout', self._T)
        try:
            r = s.get(url, **kw)
        except requests.exceptions.RequestException as e:
            raise ResolverError('VidSrcEmbed: %s at step %s (%s)' % (type(e).__name__, step, urllib_parse.urlparse(url).hostname))
        if r.headers.get('cf-mitigated'):
            raise ResolverError('VidSrcEmbed: Cloudflare challenge at step %s - not bypassed' % step)
        if r.status_code != 200:
            raise ResolverError('VidSrcEmbed: HTTP %d at step %s (%s)' % (r.status_code, step, urllib_parse.urlparse(r.url).hostname))
        if 'html' in r.headers.get('Content-Type', ''):
            m = self._CHALLENGE.search(r.text)
            if m:
                raise ResolverError('VidSrcEmbed: challenge sign %r at step %s - not bypassed' % (m.group(0), step))
        return r

    def get_media_url(self, host, media_id):
        embed_url = self.get_url(host, media_id)
        co = self._CO
        ref = {'Referer': co + '/', 'Origin': co}

        s = requests.Session()
        s.headers.update({'User-Agent': self._UA})

        # 1 embed -> data-api
        r = self._get(s, '1 embed', embed_url, headers={'Referer': 'https://zenoplay.to/'})
        embed_url = r.url
        m = re.search(r'data-api="([^"]+)"', r.text)
        if not m:
            raise ResolverError('VidSrcEmbed: data-api not found in embed page')
        # 2 vs_src.php -> cloudorchestranova
        r = self._get(s, '2 vs_src', urllib_parse.urljoin(embed_url, m.group(1).replace('&amp;', '&')),
                      headers={'Referer': embed_url})
        src = urllib_parse.urljoin(embed_url, r.json().get('src') or '')
        if 'cloudorchestranova.com' not in src:
            raise ResolverError('VidSrcEmbed: vs_src.src is not cloudorchestranova: %s' % src[:100])
        # 3 inner -> window.CFG
        r = self._get(s, '3 inner', src, headers={'Referer': embed_url})
        m = re.search(r'window\.CFG = (\{.*?\});?</script>', r.text)
        if not m:
            raise ResolverError('VidSrcEmbed: window.CFG not found')
        cfg = json.loads(m.group(1))
        inner_url = r.url
        # 4 player -> window.CONFIG
        r = self._get(s, '4 player', urllib_parse.urljoin(co, cfg['playerUrl']), headers={'Referer': inner_url})
        m = re.search(r'window\.CONFIG = (\{.*?\});?</script>', r.text)
        if not m:
            raise ResolverError('VidSrcEmbed: window.CONFIG not found')
        conf = json.loads(m.group(1))
        if conf.get('turnstile'):
            raise ResolverError('VidSrcEmbed: CONFIG.turnstile is active - not bypassed')
        if conf.get('mediaType') == 'tv' and conf.get('streamBase'):
            api = conf['streamBase'] + '&season=%s&episode=%s&stream_urls' % (conf.get('season'), conf.get('episode'))
        else:
            api = conf.get('api')
        if not api:
            raise ResolverError('VidSrcEmbed: no api/streamBase in CONFIG')
        # 5 api.php -> encrypted stream_urls + wasm
        r = self._get(s, '5 api', api, headers=dict(ref, Accept='application/json'))
        j = r.json()
        self._publish_imdb((j.get('data') or {}).get('imdb_id'))
        su = (j.get('data') or {}).get('stream_urls')
        vs = j.get('vs') or {}
        if isinstance(su, list):
            urls = su
        elif isinstance(su, str):
            if vs.get('wasm_url'):
                wasm = self._get(s, '6 wasm', vs['wasm_url'], headers=ref).content
            elif vs.get('wasm'):
                wasm = base64.b64decode(vs['wasm'])
            else:
                raise ResolverError('VidSrcEmbed: encrypted stream_urls without vs.wasm_url/vs.wasm')
            try:
                urls = vsdec.decrypt_stream_urls(wasm, su)
            except vsdec.VsDecError as e:
                raise ResolverError('VidSrcEmbed: VsDecError (WASM w=%s changed?): %s' % (vs.get('w'), e))
        else:
            raise ResolverError('VidSrcEmbed: stream_urls missing (status %s)' % j.get('status_code'))
        xbmc.log('VidSrcEmbed: w=%s stream urls=%d' % (vs.get('w'), len(urls)), xbmc.LOGINFO)

        # 7 generate.php -> token -> master (#EXTM3U), first working stream host
        for i, u in enumerate(urls):
            o = urllib_parse.urlparse(u)
            origin = '%s://%s' % (o.scheme, o.netloc)
            try:
                tk = self._get(s, '7 generate[%d]' % i, origin + '/generate.php', headers=ref).text.strip()
                if tk[:1] in '{[':
                    jj = json.loads(tk)
                    tk = jj if isinstance(jj, str) else (jj.get('token') or jj.get('data') or jj.get('string') or jj.get('result') or '')
                if tk:
                    full = u.replace('__TOKEN__', tk) if '__TOKEN__' in u else u + ('&' if '?' in u else '?') + 'token=' + tk
                else:
                    full = u
                mt = self._get(s, '8 master[%d]' % i, full, headers=ref).text
            except ResolverError as e:
                xbmc.log('VidSrcEmbed: stream host %d (%s): %s' % (i, o.netloc, e), xbmc.LOGINFO)
                continue
            if mt.lstrip().startswith('#EXTM3U'):
                xbmc.log('VidSrcEmbed: master from %s' % o.netloc, xbmc.LOGINFO)
                play_headers = {'User-Agent': self._UA, 'Referer': co + '/', 'Origin': co}
                return full + helpers.append_headers(play_headers)
            xbmc.log('VidSrcEmbed: stream host %d (%s): not #EXTM3U' % (i, o.netloc), xbmc.LOGINFO)

        raise ResolverError('VidSrcEmbed: no stream host returned a #EXTM3U master (%d tried)' % len(urls))

    def get_url(self, host, media_id):
        return self._default_get_url(host, media_id, template='https://{host}/embed/{media_id}')
