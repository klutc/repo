import re
from urllib.parse import urljoin, urlencode
from bs4 import BeautifulSoup
BASE = 'https://filmizip.com/'

def categories(html):
    soup = BeautifulSoup(html, 'html.parser')
    return [(a.get_text(' ', strip=True), urljoin(BASE, a['href']))
            for a in soup.select('.side-block__menu a[href]')
            if a['href'] not in ('/favorites/', '/actors.html', '/keywords.html', '/films.html', '/series.html')]

def listing(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    items, seen = [], set()
    for card in soup.select('#dle-content .poster'):
        a = card if card.name == 'a' else card.select_one('a[href]')
        title, image = card.select_one('.poster__title'), card.select_one('img')
        if not a or not title:
            continue
        link = urljoin(url, a.get('href', ''))
        if link in seen:
            continue
        seen.add(link)
        info = card.select_one('.poster__info')
        text = info.get_text(' ', strip=True) if info else ''
        year = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        items.append(dict(name=title.get_text(' ', strip=True), url=link,
                          icon=urljoin(url, (image.get('data-src') or image.get('src', ''))) if image else '',
                          plot=text, year=int(year[0]) if year else 0))
    nextpage = soup.select_one('a[aria-label="Next page"]')
    return items, urljoin(url, nextpage['href']) if nextpage else ''


def metadata(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    plot = soup.select_one('.page__text')
    poster = soup.select_one('.pmovie__poster img')
    title = soup.select_one('h1')
    original = soup.select_one('.pmovie__original-title')
    quality = soup.select_one('.pmovie__quality')
    year_link = soup.select_one('.pmovie__quality a[href*="/year/"]')
    year = re.search(r'\b(19\d{2}|20\d{2})\b', year_link.get_text() if year_link else '')
    genres = []
    for row in soup.select('.pmovie__header-row'):
        label = row.select_one('.pmovie__header-label')
        if label and label.get_text(strip=True).rstrip(':') == 'Жанр':
            genres = [a.get_text(strip=True) for a in row.select('.pmovie__header-data a')]
    backdrop = re.search(r'var\s+backdrop\s*=\s*[\"\']([^\"\']+)', html)
    duration = re.search(r'(\d+)\s*мин', quality.get_text(' ',strip=True) if quality else '')
    originaltitle = original.get_text(strip=True).lstrip('/').strip() if original else ''
    imdb_link = soup.select_one('a[href*="imdb.com/title/tt"]')
    imdb_match = re.search(r'/title/(tt\d{7,10})', imdb_link.get('href', '')) if imdb_link else None
    if original:
        original.extract()
    return dict(plot=plot.get_text(' ',strip=True) if plot else '',
                icon=urljoin(url,poster['src']) if poster else '',
                title=title.get_text(' ',strip=True) if title else '',
                originaltitle=originaltitle,imdb=imdb_match.group(1) if imdb_match else '',
                year=int(year[0]) if year else 0,genres=genres,
                fanart=urljoin(url,backdrop[1]) if backdrop else '',
                duration=int(duration[1])*60 if duration else 0)

def detail(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    plot = soup.select_one('.page__text')
    image = soup.select_one('.pmovie__poster img')
    sources = [(a['data-link'], a.get_text(strip=True)) for a in soup.select('.pmovie__player-controls [data-link]')]
    episodes = [(a['data-tv_link'], a.get('data-source', '').split(','), a.get('data-abr', '').split(','))
                for a in soup.select('[data-tv_link]') if 'disabled' not in a.get('class', [])]
    news = re.search(r'/(\d+)-', url)
    token = re.search(r"dle_login_hash\s*=\s*['\"]([^'\"]+)", html)
    if not news or not token:
        raise ValueError('Липсват данни за плейъра.')
    result = metadata(html, url)
    result.update(sources=sources, episodes=episodes, news=news[1], token=token[1])
    return result

def player_url(data, source, episode=''):
    params = dict(link=source, news_id=data['news'], user_hash=data['token'])
    if episode:
        params['tv'] = episode
    return urljoin(BASE, 'player.html') + '?' + urlencode(params)

def embed(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    frame = soup.select_one('iframe[src]')
    if not frame:
        raise ValueError('Видеоизточникът не е наличен.')
    target = urljoin(url, frame['src'])
    if not target.startswith(('https://', 'http://')):
        raise ValueError('Невалиден видеоадрес.')
    return target
