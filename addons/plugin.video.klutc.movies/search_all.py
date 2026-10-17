"""Search the three Klutc video add-ons using their existing site parsers."""
import importlib.util
import os
from urllib.parse import urlencode

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


def _search_filmizip(query, user_agent):
    parser = _load_parser('plugin.video.filmizip')
    url = parser.BASE + 'index.php?' + urlencode({
        'do': 'search', 'subaction': 'search', 'story': query,
    })
    response = _fetch(url, user_agent, parser.BASE)
    rows, next_page = parser.listing(response.text, url)
    return {'items': rows, 'next_page': next_page, 'search_url': url}


def _search_filmi9(query, user_agent):
    parser = _load_parser('plugin.video.filmi9')
    url = parser.search_url(query)
    response = _fetch(url, user_agent, parser.BASE)
    rows, next_page = parser.api_listing(response.json(), url)
    return {'items': rows, 'next_page': next_page, 'search_url': url}


def _search_zenoplay(query, user_agent):
    parser = _load_parser('plugin.video.zenoplay')
    url = parser.search_url(query)
    response = _fetch(url, user_agent, parser.BASE)
    rows, next_page = parser.listing(response.text, url)
    return {'items': rows, 'next_page': next_page, 'search_url': url}


_SEARCHERS = {
    'plugin.video.filmizip': _search_filmizip,
    'plugin.video.filmi9': _search_filmi9,
    'plugin.video.zenoplay': _search_zenoplay,
}


def search_sources(addon_id, query, user_agent):
    """Return normalized movie rows from one site's existing parser."""
    if addon_id not in _ADDON_IDS:
        raise ValueError('Непознат видео източник: ' + addon_id)
    result = _SEARCHERS[addon_id](query.strip(), user_agent)
    result['items'] = [row for row in result['items'] if isinstance(row, dict) and row.get('url')]
    return result
