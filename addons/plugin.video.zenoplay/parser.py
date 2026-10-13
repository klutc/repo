import re
from urllib.parse import quote_plus, urljoin, urlsplit
from bs4 import BeautifulSoup

BASE = 'https://zenoplay.to/'
AJAX = urljoin(BASE, 'wp-admin/admin-ajax.php')


def categories(html):
    soup = BeautifulSoup(html, 'html.parser')
    rows, seen = [], set()
    for a in soup.select('.menu a[href], .mobile-menu a[href], .genre-menu a[href]'):
        href = urljoin(BASE, a.get('href', ''))
        path = urlsplit(href).path
        label = a.get_text(' ', strip=True)
        if not label or href in seen:
            continue
        if path in ('/movies/', '/tv-shows/', '/collections/') or path.startswith(('/genre/', '/year/')):
            seen.add(href)
            rows.append((label, href))
    return rows


def listing(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    rows, seen = [], set()
    for card in soup.select('a.media-card[href]'):
        href = urljoin(url, card.get('href', ''))
        path = urlsplit(href).path
        if not (path.startswith('/movie/') or path.startswith('/tv-show/')) or href in seen:
            continue
        seen.add(href)
        title = card.select_one('.media-title')
        image = card.select_one('.poster-box img, img')
        year = card.select_one('.media-year')
        kind = card.select_one('.media-kind')
        title_text = title.get_text(' ', strip=True) if title else card.get('aria-label', '')
        year_text = year.get_text(' ', strip=True) if year else ''
        match = re.search(r'\b(19\d{2}|20\d{2})\b', year_text)
        rows.append(dict(name=title_text, title=title_text, url=href,
                         icon=urljoin(url, (image.get('data-src') or image.get('src', ''))) if image else '',
                         year=int(match[1]) if match else 0, plot='', genres=[],
                         media_type='tvshow' if kind and 'tv' in kind.get_text(' ', strip=True).lower() else 'movie'))
    next_link = soup.select_one('a.next[href], a[rel="next"][href], .pagination a[aria-label*="Next"][href]')
    return rows, urljoin(url, next_link['href']) if next_link else ''


def metadata(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    title_node = soup.select_one('.detail-info h1, .detail-title, h1')
    title = title_node.get_text(' ', strip=True) if title_node else ''
    panel = soup.select_one('[data-player-panel]')
    episode = panel is not None and panel.get('data-media-type') == 'episode'
    show_title = panel.get('data-show-title', '') if panel else ''
    if episode:
        name = show_title or re.split(r'\s+[–-]\s+Сезон\s+\d+', title, maxsplit=1, flags=re.I)[0]
        media_type = 'episode'
    else:
        name = title
        media_type = 'tvshow' if urlsplit(url).path.startswith('/tv-show/') else 'movie'
    summary = soup.select_one('.detail-overview, .detail-description, .detail-plot')
    poster = soup.select_one('.detail-poster img, img.detail-poster')
    if not poster:
        poster = soup.select_one('meta[property="og:image"]')
    icon = (poster.get('content') if poster and poster.name == 'meta' else
            urljoin(url, poster.get('data-src') or poster.get('src', '')) if poster else '')
    meta = soup.select_one('.detail-meta')
    meta_text = meta.get_text(' ', strip=True) if meta else ''
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', meta_text)
    genre = []
    for group in soup.select('.taxonomy-group'):
        label = group.select_one('.taxonomy-group-title, .taxonomy-label')
        if label and 'genre' not in label.get_text(' ', strip=True).lower():
            continue
        links = [a.get_text(' ', strip=True) for a in group.select('a[href*="/genre/"]')]
        if links:
            genre = links
            break
    tmdb = panel.get('data-tmdb-id', '') if panel else ''
    post_id = panel.get('data-post-id', '') if panel else ''
    token = panel.get('data-player-token', '') if panel else ''
    try:
        season = int(panel.get('data-season-number')) if episode and panel.get('data-season-number') else None
        epno = int(panel.get('data-episode-number')) if episode and panel.get('data-episode-number') else None
    except (ValueError, TypeError):
        season, epno = None, None
    original = ''
    for key in ('data-original-title', 'data-originaltitle'):
        original = (soup.select_one('[%s]' % key) or {}).get(key, '')
        if original:
            break
    imdb_match = re.search(r'(?:imdb(?:_id)?["\'=:\s]+|/title/)(tt\d{5,10})', html, re.I)
    imdb = imdb_match.group(1) if imdb_match else ''
    episodes = []
    if media_type == 'tvshow':
        for row in soup.select('a.episode-card[href]'):
            try:
                season_no = int(row.get('data-season-number', '0'))
                episode_no = int(row.get('data-episode-number', '0'))
            except ValueError:
                continue
            if season_no and episode_no:
                episodes.append(dict(url=urljoin(url, row['href']), season=season_no, episode=episode_no,
                                     title=row.get('data-title') or row.get_text(' ', strip=True),
                                     plot=row.get('data-overview', '')))
    return dict(name=name, title=title or name, url=url, plot=summary.get_text(' ', strip=True) if summary else '',
                icon=icon, year=int(year_match[1]) if year_match else 0, genres=genre,
                fanart='', originaltitle=original or show_title or name, imdb=imdb,
                rating=0, media_type=media_type, tmdb=tmdb, post_id=post_id, token=token,
                season=season, episode=epno, episodes=episodes, panel_type=panel.get('data-media-type', '') if panel else '')


def providers(data, session):
    if not data.get('post_id') or not data.get('token'):
        raise ValueError('ZenoPlay не предостави token за видеоизточниците.')
    response = session.post(AJAX, data={'action': 'zenoplay_player_sources',
                                       'post_id': data['post_id'], 'token': data['token']},
                            headers={'Referer': data['url'], 'Origin': BASE,
                                     'X-Requested-With': 'XMLHttpRequest'}, timeout=(8, 20))
    response.raise_for_status()
    payload = response.json()
    if not payload.get('success'):
        message = (payload.get('data') or {}).get('message') or 'ZenoPlay отказа достъп до източниците.'
        raise ValueError(message)
    rows = (payload.get('data') or {}).get('providers') or []
    result, seen = [], set()
    key = 'tv' if data.get('panel_type') == 'tv' else 'movie' if data.get('panel_type') == 'movie' else 'tv'
    for row in rows:
        if not isinstance(row, dict) or row.get('enabled') is False:
            continue
        address = row.get(key) or row.get('url') or ''
        if not address and key == 'tv':
            address = row.get('movie') or ''
        if not address:
            continue
        for token, value in (('{tmdb_id}', data.get('tmdb', '')),
                             ('{season}', data.get('season') or ''),
                             ('{episode}', data.get('episode') or '')):
            address = address.replace(token, str(value))
        address = urljoin(BASE, address)
        if not address.startswith(('https://', 'http://')) or address in seen:
            continue
        seen.add(address)
        result.append((address, str(row.get('name') or row.get('title') or urlsplit(address).hostname or 'Източник')))
    # BG Player is the preferred source and should stay at the top for both
    # movies and episodes. Keep the site's relative order for every other host.
    result.sort(key=lambda row: (row[1].strip().casefold() != 'bg player',))
    return result


def search_url(query):
    return BASE + '?s=' + quote_plus(query.strip())


def catalogue_url(path):
    return urljoin(BASE, path.lstrip('/'))
