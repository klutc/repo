"""Native resolver for ZenoPlay's BG Player (FirePlayer) embeds."""
import html
import json
import re
from urllib.parse import urlencode, urlsplit


def _subtitle_track(page):
    """Return the best subtitle URL embedded in a FirePlayer page."""
    match = re.search(
        r'\bplayerjsSubtitle\s*=\s*("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')',
        page,
        re.S,
    )
    if not match:
        return ''
    raw = match.group(1)
    try:
        value = json.loads(raw) if raw.startswith('"') else raw[1:-1]
    except ValueError:
        value = raw[1:-1]
    value = html.unescape(value.replace(r'\/', '/'))
    tracks = re.findall(r'\[([^\]]+)\](https?://[^\s,"\']+)', value, re.I)
    if not tracks:
        return ''
    def score(track):
        label = track[0].strip().lower()
        return 1 if label in ('bg', 'bul', 'bulgarian', 'български') or 'bulgar' in label else 0
    return max(tracks, key=score)[1]


def resolve(session, url, page_url):
    """Ask FirePlayer for its HLS playlist without opening its browser player."""
    parts = urlsplit(url)
    host = (parts.hostname or '').lower()
    if host.startswith('www.'):
        host = host[4:]
    if host not in ('galaxicon.org', 'playtube.tv', 'rollo.uno'):
        raise ValueError('Това не е BG Player източник.')
    match = re.search(r'/video/([A-Za-z0-9_-]+)', parts.path)
    if not match:
        raise ValueError('BG Player адресът няма валиден идентификатор.')
    video_id = match.group(1)
    endpoint = 'https://%s/player/index.php?data=%s&do=getVideo' % (host, video_id)
    response = session.post(
        endpoint,
        data={'hash': video_id, 'r': page_url},
        headers={
            'Referer': url,
            'Origin': 'https://' + host,
            'X-Requested-With': 'XMLHttpRequest',
        },
        timeout=(10, 25),
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as error:
        raise ValueError('BG Player върна невалиден отговор.') from error
    if not isinstance(payload, dict):
        raise ValueError('BG Player върна невалиден отговор.')

    # FirePlayer returns a signed .m3u8 URL in addition to its extensionless
    # master.txt playlist. The signed URL is recognized by Kodi's HLS reader;
    # its child segments are absolute URLs from the same playlist.
    stream = payload.get('securedLink') or payload.get('videoSource')
    if not isinstance(stream, str) or not stream.startswith(('http://', 'https://')):
        raise ValueError('BG Player не върна HLS видеоадрес за това заглавие.')
    headers = urlencode({'User-Agent': session.headers.get('User-Agent', ''),
                         'Referer': url})
    # The provider page carries the subtitle declaration. These tracks are
    # supplied by BG Player itself; keep their request referer for Kodi's
    # downloader because some subtitle endpoints validate it.
    player = session.get(url, headers={'Referer': page_url}, timeout=(10, 25))
    player.raise_for_status()
    subtitle_url = _subtitle_track(player.text)
    subtitle = subtitle_url + '|' + urlencode({
        'User-Agent': session.headers.get('User-Agent', ''),
        'Referer': url,
    }) if subtitle_url else ''
    return stream + '|' + headers, subtitle
