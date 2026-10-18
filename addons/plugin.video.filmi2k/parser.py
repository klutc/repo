"""HTML parser for Filmi2K's WordPress catalogue and video posts."""
import json
import re
from urllib.parse import urlencode, urljoin, urlsplit

from bs4 import BeautifulSoup

BASE = 'https://www.filmi2k.com/'
SERIES = BASE + 'onlayn-seriali/'


def _soup(html):
    return BeautifulSoup(html, 'html.parser')


def _year(title, text=''):
    match = re.search(r'\b(19\d{2}|20\d{2})\b', title + ' ' + text)
    return int(match[1]) if match else 0


def _series(title, url):
    path = urlsplit(url).path.lower()
    return bool(re.search(r'\bs\d{1,2}\s*e\d{1,3}\b', title, re.I)
                or re.search(r'[-_]s\d{1,2}e\d{1,3}(?:[-_/]|$)', path)
                or '/onlayn-seriali/' in path or '/category/' in path and 'season' in path)


def categories(html):
    soup = _soup(html)
    result, seen = [], set()
    selectors = ('header a[href]', 'nav a[href]')
    for selector in selectors:
        for anchor in soup.select(selector):
            href = urljoin(BASE, anchor.get('href', ''))
            path = urlsplit(href).path
            name = anchor.get_text(' ', strip=True)
            if not name or href in seen or href.rstrip('/') == BASE.rstrip('/'):
                continue
            if path.startswith('/category/') or path.startswith('/tag/') or path.rstrip('/') == '/onlayn-seriali':
                seen.add(href)
                result.append((name, href))
    # Put the series catalogue first among the browsable sections.
    result.sort(key=lambda row:0 if urlsplit(row[1]).path.rstrip('/') == '/onlayn-seriali' else 1)
    return result


def _card(article, page_url):
    anchor = article.select_one('a[href]')
    image = article.select_one('img.video-main-thumb, img')
    if not anchor:
        return None
    url = urljoin(page_url, anchor.get('href', ''))
    raw_title = anchor.get('title') or (image.get('alt') if image else '')
    raw_title = raw_title or article.get_text(' ', strip=True)
    raw_title = re.sub(r'^HD\s+\d+%\s*', '', raw_title).strip()
    if not raw_title or not url.startswith(BASE):
        return None
    bg_audio = bool(re.search(r'\bBG Audio\b', raw_title, re.I)
                    or 'tag-filmi-bg-audio' in (article.get('class') or []))
    clean_title = re.sub(r'\s+BG Audio\s*$', '', raw_title, flags=re.I)
    year = _year(clean_title)
    if year:
        clean_title = re.sub(r'\s*\(' + str(year) + r'\)\s*$', '', clean_title).strip()
    originaltitle = clean_title.split('/', 1)[0].strip()
    title = clean_title.split('/', 1)[-1].strip() if '/' in clean_title else clean_title
    icon = urljoin(page_url, image.get('data-src') or image.get('src', '')) if image else ''
    is_series = _series(title, url)
    # A category entry on the serial index is a season page, not an episode.
    if urlsplit(page_url).path.rstrip('/') == '/onlayn-seriali' and '/category/' in urlsplit(url).path:
        is_series = True
    episode = re.search(r'(?i)\bS(\d{1,2})\s*E(\d{1,3})\b', title)
    return dict(name=title, title=title, url=url, icon=icon, fanart=icon,
                plot='', year=year, genres=[], countries=[], actors=[], duration=0,
                originaltitle=originaltitle, imdb='', rating=0, bg_audio=bg_audio,
                media_type='episode' if episode else 'tvshow' if is_series else 'movie')


def listing(html, url):
    soup = _soup(html)
    items, seen = [], set()
    for article in soup.select('article'):
        row = _card(article, url)
        if row and row['url'] not in seen:
            seen.add(row['url'])
            items.append(row)
    next_anchor = soup.select_one('.pagination a.next, .pagination a[rel="next"], a.next.page-numbers, a[rel="next"]')
    if not next_anchor:
        current = soup.select_one('.pagination a.current')
        current_item = current.parent if current and current.parent else None
        next_item = current_item.find_next_sibling('li') if current_item else None
        next_anchor = next_item.select_one('a[href]') if next_item else None
    return items, urljoin(url, next_anchor['href']) if next_anchor and next_anchor.get('href') else ''


def search_url(query):
    return BASE + '?' + urlencode({'s': query})


def source_rows(data):
    sources = data.get('sources') or []
    if isinstance(sources, str):
        sources = [sources]
    result = []
    for source in sources:
        if isinstance(source, dict):
            address = source.get('url') or source.get('embedURL') or ''
            label = source.get('name') or urlsplit(address).hostname or 'Видео'
        else:
            address, label = source, 'Видео'
        if isinstance(address, str) and address.startswith(('https://', 'http://')):
            result.append((address, label))
    return result


def _parse_duration(value):
    match = re.search(r'P(?:\d+D)?T(?:(\d+)H)?(?:(\d+)M)?', value or '')
    if not match:
        return 0
    hours, minutes = (int(x or 0) for x in match.groups())
    return (hours * 60 + minutes) * 60


def _jsonld(soup):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if isinstance(item.get('@graph'), list):
                    stack.extend(item['@graph'])
                if item.get('@type') in ('Article', 'VideoObject', 'Movie', 'TVEpisode'):
                    return item
    return {}


def detail(html, url):
    soup = _soup(html)
    title_tag = soup.select_one('h1')
    if not title_tag:
        raise ValueError('Заглавието не е намерено във Filmi2K.')
    title = title_tag.get_text(' ', strip=True)
    bg_audio = bool(re.search(r'\bBG Audio\b', title, re.I))
    clean_title = re.sub(r'\s+BG Audio\s*$', '', title, flags=re.I)
    player_meta = {m.get('itemprop'):m.get('content', '') for m in soup.select('.video-player meta[itemprop]')}
    if not player_meta.get('embedURL') and not soup.select_one('.video-player iframe[src]'):
        items, _ = listing(html, url)
        if items and '/category/' in urlsplit(url).path:
            return dict(name=title, title=title, originaltitle=title, url=url,
                        plot='', year=_year(title), icon='', fanart='', genres=[],
                        countries=[], actors=[], duration=0, imdb='', rating=0,
                        media_type='tvshow', sources=[], episodes=items, subtitles=[],
                        is_category=True)
        raise ValueError('Filmi2K не предостави видеоизточник за това заглавие.')
    schema = _jsonld(soup)
    entry = soup.select_one('.entry-content')
    text = entry.get_text('\n', strip=True) if entry else player_meta.get('description', '')
    plot = text.split('\nРежисьор:', 1)[0].strip()
    def field(pattern):
        match = re.search(r'(?:' + pattern + r')\s*:\s*([^\n]+)', text, re.I)
        return match.group(1).strip() if match else ''
    actors = [name.strip() for name in re.split(r'\s*,\s*', field('Актьори|Актьорски състав')) if name.strip()]
    country_text = re.split(r',\s*(?:Година|Времетраене)\s*:', field('Държава|Страна'), maxsplit=1, flags=re.I)[0]
    countries = [name.strip() for name in re.split(r'\s*,\s*', country_text) if name.strip()]
    genres = []
    for anchor in soup.select('.entry-content a[href*="/category/"]'):
        name = anchor.get_text(' ', strip=True)
        if name and name not in genres:
            genres.append(name)
    if not genres:
        sections = schema.get('articleSection', [])
        genres = [sections] if isinstance(sections, str) else sections if isinstance(sections, list) else []
    image = player_meta.get('thumbnailUrl') or ''
    if not image:
        og = soup.select_one('meta[property="og:image"]')
        image = og.get('content', '') if og else ''
    image = urljoin(BASE, image)
    embed = player_meta.get('embedURL') or ''
    if not embed:
        iframe = soup.select_one('.video-player iframe[src], .video-player source[src]')
        embed = urljoin(url, iframe.get('src', '')) if iframe else ''
    original = clean_title.split('/', 1)[0].strip()
    bg_title = clean_title.split('/', 1)[-1].strip() if '/' in clean_title else clean_title
    year = _year(clean_title, text)
    if year:
        bg_title = re.sub(r'\s*\(' + str(year) + r'\)\s*$', '', bg_title).strip()
    duration = _parse_duration(player_meta.get('duration', ''))
    if not duration:
        duration_match = re.search(r'Времетраене\s*:\s*(\d+)\s*минути', text, re.I)
        duration = int(duration_match[1]) * 60 if duration_match else 0
    sources = [(embed, urlsplit(embed).hostname or 'Видео')] if embed else []
    episode = re.search(r'(?i)\bS(\d{1,2})\s*E(\d{1,3})\b', title)
    is_series = _series(title, url)
    media_type = 'episode' if episode else 'tvshow' if is_series else 'movie'
    tvshowtitle = re.sub(r'(?i)[\s:/_-]*S\d{1,2}\s*E\d{1,3}.*$', '', original).strip()
    result = dict(name=bg_title, title=bg_title, originaltitle=original, url=url,
                  plot=plot, year=year, icon=image, fanart=image, genres=genres,
                  countries=countries, actors=actors, duration=duration,
                  imdb='', rating=0, media_type=media_type, sources=sources,
                  bg_audio=bg_audio,
                  episodes=[], subtitles=[])
    if episode:
        result.update(tvshowtitle=tvshowtitle, season=int(episode[1]), episode=int(episode[2]))
    return result


def metadata(html, url):
    return detail(html, url)

