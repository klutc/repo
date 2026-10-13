from resolveurl.plugins.__resolve_generic__ import ResolveGeneric
from resolveurl.lib import helpers
from resolveurl.resolver import ResolverError
import re
import requests
import xbmcgui


class ZZReelTubeResolver(ResolveGeneric):
    name = 'ZZReelTube'
    domains = ['*']
    pattern = r'.*'

    def get_media_url(self, host, media_id):
        UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36'

        s = requests.Session()

        headers = {'user-agent': UA}

        try:
            # Fast-fail: skip well-known media hosts that never redirect to reeltube
            _known = ('vidmoly', 'abstream', 'playerp2p', 'uns.bio', 'byse',
                      'filemoon', 'youtube', 'vimeo', 'dailymotion')
            if any(k in host for k in _known):
                raise ResolverError('Known media host: not a reeltube redirect')

            r = s.get(host, headers=headers, allow_redirects=False)
            location = r.headers.get('location', '')

            if not location or 'reeltube' not in location:
                raise ResolverError('Not a reeltube redirect')

            if re.search(r'/watch/', location):
                links = [location]
            else:
                r = s.get(location, headers=headers)
                data = r.text

                pattern = r'<div class="video-thumb">(.*?)</div>'
                mydivs = re.findall(pattern, data, re.DOTALL)

                links = []
                for mydiv in mydivs:
                    pattern = r'<a href="(.*?)"'
                    match_link = re.search(pattern, mydiv, re.DOTALL)
                    if match_link:
                        links.append(match_link.group(1))

            check_ep = 0
            for link in links:
                r = s.get(link, headers=headers)
                data = r.text

                pattern = r'<div class="embed-responsive(.*?)</div>'
                mydiv = re.findall(pattern, data, re.DOTALL)[0]

                pattern = r'src="(.*?)"'
                match_url = re.search(pattern, mydiv, re.DOTALL)

                if match_url:
                    playurl = match_url.group(1)
                    if not re.search('http', playurl):
                        playurl = 'https:' + playurl
                if check_ep != 0:
                    play_url = play_url + '$$' + playurl
                else:
                    play_url = playurl
                check_ep = 1

            return play_url

        except ResolverError:
            raise
        except Exception as e:
            raise ResolverError('ZZReelTube failed: %s' % e)

