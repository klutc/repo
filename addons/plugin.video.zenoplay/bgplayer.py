"""Native resolver for ZenoPlay's BG Player (FirePlayer) embeds."""
import re
from urllib.parse import urlencode, urlsplit


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
    return stream + '|' + headers, ''
