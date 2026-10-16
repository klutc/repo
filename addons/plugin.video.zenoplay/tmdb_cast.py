"""Fetch cast credits from TMDb for ZenoPlay titles."""
import hashlib
import json
import os
import time
from urllib.parse import urljoin

API = 'https://api.themoviedb.org/3/'
CACHE_TTL = 7 * 24 * 60 * 60


def _names(payload):
    rows = payload.get('cast', []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    rows = sorted(rows, key=lambda row: row.get('order', 10**6) if isinstance(row, dict) else 10**6)
    result, seen = [], set()
    for row in rows:
        name = row.get('name', '').strip() if isinstance(row, dict) else ''
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def lookup(session, media_type, tmdb_id, token, cache_directory):
    """Return a cached or live cast list. An empty token disables network lookup."""
    ident = str(tmdb_id or '').strip()
    token = str(token or '').strip()
    if not ident.isdigit() or not token:
        return []
    kind = 'tv' if media_type in ('tv', 'tvshow', 'episode', 'series') else 'movie'
    os.makedirs(cache_directory, exist_ok=True)
    cache_key = hashlib.sha256((kind + ':' + ident).encode('utf-8')).hexdigest()
    cache_path = os.path.join(cache_directory, 'tmdb-cast-' + cache_key + '.json')
    try:
        with open(cache_path, encoding='utf-8') as cached:
            data = json.load(cached)
        if time.time() - float(data.get('time', 0)) < CACHE_TTL:
            return data.get('actors', [])
    except (OSError, ValueError, TypeError, AttributeError):
        pass

    endpoint = 'tv/%s/aggregate_credits' % ident if kind == 'tv' else 'movie/%s/credits' % ident
    response = session.get(urljoin(API, endpoint),
                           headers={'Authorization': 'Bearer ' + token, 'accept': 'application/json'},
                           params={'language': 'bg-BG'}, timeout=(5, 12))
    response.raise_for_status()
    actors = _names(response.json())
    try:
        temp_path = cache_path + '.tmp'
        with open(temp_path, 'w', encoding='utf-8') as cached:
            json.dump({'time': time.time(), 'actors': actors}, cached, ensure_ascii=False)
        os.replace(temp_path, cache_path)
    except OSError:
        pass
    return actors
