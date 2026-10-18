"""Host-specific public player APIs used by Filmi2K."""
from urllib.parse import urlsplit, urljoin, urlencode


def playmate(session, url):
    parsed = urlsplit(url)
    if parsed.hostname not in ('playmate.to', 'www.playmate.to'):
        raise ValueError('Unsupported PlayM host')
    page = session.get(url, timeout=(10,20))
    page.raise_for_status()
    code = parsed.path.rstrip('/').split('/')[-1]
    root = parsed.scheme + '://' + parsed.netloc
    response = session.post(urljoin(root, '/api/s'), json={'c':code,'d':'desktop'},
                            headers={'Referer':url, 'Origin':root}, timeout=(10,20))
    response.raise_for_status()
    data = response.json()
    video = data.get('sx', '')
    if not isinstance(video, str) or not video.startswith(('https://', 'http://')):
        raise ValueError('PlayM не върна видеоадрес.')
    captions = []
    for track in data.get('kx', []):
        address = track.get('sf', '')
        if not address or not track.get('ss'):
            continue
        language = str(track.get('sl', '')).lower()
        score = 2 if language in ('bg','bul','bulgarian','български') else (1 if language == str(data.get('lx', '')).lower() else 0)
        captions.append((score, urljoin(url,address)))
    subtitle = max(captions,key=lambda t:t[0])[1] if captions else ''
    headers = {'User-Agent':session.headers['User-Agent'], 'Referer':url, 'Origin':root}
    return video + '|' + urlencode(headers), subtitle
