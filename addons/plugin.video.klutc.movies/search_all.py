"""Search the three Klutc video add-ons using their existing site parsers."""
import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, urlsplit

import requests
import xbmcaddon
import xbmcvfs


_PARSERS = {}
_ADDON_IDS = (
    'plugin.video.filmizip',
    'plugin.video.filmi9',
    'plugin.video.zenoplay',
)


def _load_parser(addon_id):
    parser = _PARSERS.get(addon_id)
    if parser is not None:
        return parser
    addon_path = xbmcvfs.translatePath(xbmcaddon.Addon(addon_id).getAddonInfo('path'))
    parser_path = os.path.join(addon_path, 'parser.py')
    module_name = 'klutc_movies_parser_' + addon_id.replace('.', '_')
    spec = importlib.util.spec_from_file_location(module_name, parser_path)
    if spec is None or spec.loader is None:
        raise ImportError('Не мога да заредя парсера на ' + addon_id)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    _PARSERS[addon_id] = parser
    return parser


def _fetch(url, user_agent, referer):
    response = requests.get(url, headers={
        'User-Agent': user_agent,
        'Referer': referer,
    }, timeout=(10, 30))
    response.raise_for_status()
    response.encoding = 'utf-8'
    return response


def _search_filmizip(query, user_agent, page_url=''):
    parser = _load_parser('plugin.video.filmizip')
    url = page_url or parser.BASE + 'index.php?' + urlencode({
        'do': 'search', 'subaction': 'search', 'story': query,
    })
    response = _fetch(url, user_agent, parser.BASE)
    rows, next_page = parser.listing(response.text, url)
    return {'items': rows, 'next_page': next_page, 'search_url': url}


def _search_filmi9(query, user_agent, page_url=''):
    parser = _load_parser('plugin.video.filmi9')
    url = page_url or parser.search_url(query)
    response = _fetch(url, user_agent, parser.BASE)
    rows, next_page = parser.api_listing(response.json(), url)
    return {'items': rows, 'next_page': next_page, 'search_url': url}


def _search_zenoplay(query, user_agent, page_url=''):
    parser = _load_parser('plugin.video.zenoplay')
    url = page_url or parser.search_url(query)
    response = _fetch(url, user_agent, parser.BASE)
    rows, next_page = parser.listing(response.text, url)
    return {'items': rows, 'next_page': next_page, 'search_url': url}


def _mark_zenoplay_bg_audio(rows, parser, user_agent):
    """Match ZenoPlay's normal listing behavior and share its membership cache."""
    profile = xbmcvfs.translatePath(xbmcaddon.Addon('plugin.video.zenoplay').getAddonInfo('profile'))
    cache_path = os.path.join(profile, 'bg_audio_cache.json')
    try:
        with open(cache_path, 'r', encoding='utf-8') as cache_file:
            cache = json.load(cache_file)
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError, TypeError):
        cache = {}

    pending = [row for row in rows if row.get('url') and not row.get('bg_audio') and row['url'] not in cache]

    def read_membership(row):
        response = _fetch(row['url'], user_agent, parser.BASE)
        return row['url'], parser.is_bg_audio(response.text)

    changed = False
    if pending:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(read_membership, row) for row in pending]
            for future in as_completed(futures):
                try:
                    url, is_bg = future.result()
                    cache[url] = is_bg
                    changed = True
                except Exception:
                    # A failed metadata lookup must not hide otherwise valid search results.
                    continue
    for row in rows:
        row['bg_audio'] = bool(row.get('bg_audio') or cache.get(row.get('url'), False))
    if changed:
        try:
            os.makedirs(profile, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as cache_file:
                json.dump(cache, cache_file, ensure_ascii=False)
        except OSError:
            pass


_SEARCHERS = {
    'plugin.video.filmizip': _search_filmizip,
    'plugin.video.filmi9': _search_filmi9,
    'plugin.video.zenoplay': _search_zenoplay,
}


def _is_series(addon_id, row):
    path = urlsplit(str(row.get('url') or '')).path.lower()
    media_type = str(row.get('media_type') or '').lower()
    if addon_id == 'plugin.video.filmizip':
        return '/seriali/' in path or '/serial/' in path or '/series/' in path
    return media_type in ('tv', 'tvshow', 'series', 'episode') or '/tv-show/' in path or '/serial/' in path


def search_sources(addon_id, query, user_agent, media_type='movie', page_url=''):
    """Return normalized movie rows from one site's existing parser."""
    if addon_id not in _ADDON_IDS:
        raise ValueError('Непознат видео източник: ' + addon_id)
    if media_type not in ('movie', 'series'):
        raise ValueError('Непознат вид търсене: ' + str(media_type))
    result = _SEARCHERS[addon_id](query.strip(), user_agent, page_url)
    result['items'] = [row for row in result['items']
                       if isinstance(row, dict) and row.get('url')
                       and (_is_series(addon_id, row) == (media_type == 'series'))]
    if addon_id == 'plugin.video.zenoplay':
        parser = _load_parser(addon_id)
        _mark_zenoplay_bg_audio(result['items'], parser, user_agent)
    return result
