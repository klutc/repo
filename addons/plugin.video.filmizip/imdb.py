"""Resolve IMDb IDs from IMDb's public title suggestion endpoint."""
import re
from urllib.parse import quote


def _normalise(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').casefold()).strip()


def find_id(session, title, year, is_tv=False):
    title = str(title or '').strip()
    try:
        year = int(year or 0)
    except (TypeError, ValueError):
        year = 0
    if not title or not year:
        return ''

    query = title.casefold().replace(' ', '_')
    if not is_tv:
        query += '_' + str(year)
    query = quote(query, safe='_')
    endpoint = 'https://v2.sg.media-imdb.com/suggestion/%s/%s.json' % (query[0], query)
    response = session.get(endpoint, timeout=(3, 5))
    response.raise_for_status()
    rows = response.json().get('d', [])
    expected_title = _normalise(title)
    allowed_types = ('TV series', 'TV mini-series') if is_tv else ('feature', 'TV movie')
    for row in rows:
        if not isinstance(row, dict) or row.get('q') not in allowed_types:
            continue
        if _normalise(row.get('l')) != expected_title:
            continue
        try:
            candidate_year = int(row.get('y') or 0)
        except (TypeError, ValueError):
            continue
        if candidate_year != year:
            continue
        imdb = str(row.get('id') or '')
        if re.fullmatch(r'tt\d{7,10}', imdb):
            return imdb
    return ''
