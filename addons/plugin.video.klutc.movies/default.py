# -*- coding: utf-8 -*-
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode

import requests
import xbmcaddon
import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs

from search_all import search_sources

HANDLE = int(sys.argv[1])
ADDON_ID = 'plugin.video.klutc.movies'
ADDON = xbmcaddon.Addon(ADDON_ID)

SOURCES = [
    ('30001', 'plugin.video.filmizip', 'FilmiZip by Klutc'),
    ('30002', 'plugin.video.filmi9', 'Filmi9 by Klutc'),
    ('30003', 'plugin.video.zenoplay', 'ZenoPlay by Klutc'),
    ('30015', 'plugin.video.filmi2k', 'Filmi2K by Klutc'),
]
SOURCE_NAMES = {addon_id: name for _, addon_id, name in SOURCES}
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
HISTORY_PATH = os.path.join(PROFILE, 'search_history.json')
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'


def search_history(media_type):
    try:
        with open(HISTORY_PATH, 'r', encoding='utf-8') as history_file:
            data = json.load(history_file)
        if isinstance(data, list):
            # Older versions kept one shared list. Carry it forward into both
            # types so existing searches remain available after the upgrade.
            data = {'movie': data, 'series': data}
        values = data.get(media_type, []) if isinstance(data, dict) else []
        return [query for query in values if isinstance(query, str) and query.strip()][:10]
    except (OSError, ValueError, TypeError):
        return []


def _read_history_data():
    try:
        with open(HISTORY_PATH, 'r', encoding='utf-8') as history_file:
            data = json.load(history_file)
        if isinstance(data, list):
            return {'movie': data, 'series': data}
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_history_data(data):
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(HISTORY_PATH, 'w', encoding='utf-8') as history_file:
            json.dump(data, history_file, ensure_ascii=False)
    except OSError as error:
        xbmc.log('Klutc Movies search history: ' + str(error), xbmc.LOGWARNING)


def save_search(query, media_type):
    query = query.strip()
    if not query:
        return
    data = _read_history_data()
    history = [old for old in search_history(media_type) if old.casefold() != query.casefold()]
    history.insert(0, query)
    data[media_type] = history[:10]
    _write_history_data(data)


def update_search_history(action, query, media_type):
    data = _read_history_data()
    if action == 'history_clear':
        data[media_type] = []
    elif action == 'history_delete':
        data[media_type] = [old for old in data.get(media_type, [])
                            if not isinstance(old, str) or old.casefold() != query.casefold()]
    _write_history_data(data)
    xbmc.executebuiltin('Container.Refresh')


def show_search_results(query, media_type='movie', only_source=None, page_url=''):
    title_id = 30012 if media_type == 'series' else 30005
    xbmcplugin.setContent(HANDLE, 'tvshows' if media_type == 'series' else 'movies')
    progress = xbmcgui.DialogProgressBG()
    progress.create(ADDON.getLocalizedString(title_id), ADDON.getLocalizedString(30009))
    found = {}
    errors = {}
    sources = [source for source in SOURCES if not only_source or source[1] == only_source]
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        futures = {
            pool.submit(search_sources, addon_id, query, USER_AGENT, media_type, page_url if only_source == addon_id else ''): addon_id
            for _, addon_id, _ in sources
        }
        for completed, future in enumerate(as_completed(futures), 1):
            addon_id = futures[future]
            try:
                found[addon_id] = future.result()
            except Exception as error:
                errors[addon_id] = str(error)
                xbmc.log('Klutc Movies search (%s): %s' % (addon_id, error), xbmc.LOGWARNING)
            progress.update(int(completed * 100 / len(futures)), ADDON.getLocalizedString(30009))
    progress.close()

    count = 0
    for _, addon_id, source_name in sources:
        result = found.get(addon_id, {})
        for movie in result.get('items', []):
            title = str(movie.get('name') or movie.get('title') or '').strip()
            url = str(movie.get('url') or '').strip()
            if not title or not url:
                continue
            year = movie.get('year') or 0
            is_bg_audio = addon_id in ('plugin.video.zenoplay', 'plugin.video.filmi2k') and bool(movie.get('bg_audio'))
            display_title = '[BG] ' + title if is_bg_audio else title
            label = '%s (%s) — %s' % (display_title, year, source_name) if year else '%s — %s' % (display_title, source_name)
            item_params = {'action': 'detail', 'url': url, 'name': title}
            if is_bg_audio:
                item_params['bg_audio'] = '1'
            params = urlencode(item_params)
            target = 'plugin://%s/?%s' % (addon_id, params)
            item = xbmcgui.ListItem(label=label)
            icon = movie.get('icon') or ''
            item.setArt({'icon': icon, 'thumb': icon, 'poster': icon, 'fanart': movie.get('fanart') or ''})
            item.setInfo('video', {
                'title': display_title,
                'year': int(year) if str(year).isdigit() else 0,
                'plot': movie.get('plot') or '',
                'mediatype': movie.get('media_type') or 'movie',
            })
            if is_bg_audio:
                item.setProperty('FilmDisplayTitle', display_title)
            xbmcplugin.addDirectoryItem(HANDLE, target, item, isFolder=True)
            count += 1
        next_page = result.get('next_page')
        if next_page:
            params = urlencode({'action': 'search_more', 'type': media_type, 'query': query,
                                'source': addon_id, 'url': next_page})
            target = 'plugin://%s/?%s' % (ADDON_ID, params)
            item = xbmcgui.ListItem(label='%s — %s' % (ADDON.getLocalizedString(30011), source_name))
            icon = 'special://home/addons/%s/resources/icon.png' % addon_id
            item.setArt({'icon': icon, 'thumb': icon})
            xbmcplugin.addDirectoryItem(HANDLE, target, item, isFolder=True)
            count += 1

    xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
    if not count:
        message = ADDON.getLocalizedString(30008)
        if errors:
            message += '\n' + '\n'.join('%s: %s' % (SOURCE_NAMES[key], value) for key, value in errors.items())
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(title_id), message)
    elif errors:
        xbmcgui.Dialog().notification(ADDON.getLocalizedString(title_id), ADDON.getLocalizedString(30010), xbmcgui.NOTIFICATION_WARNING)


def main():
    params = dict(parse_qsl(sys.argv[2].lstrip('?')))
    action = params.get('action', 'home')
    if action == 'search':
        media_type = params.get('type', 'movie')
        xbmcplugin.setContent(HANDLE, 'files')
        new_search = urlencode({'action': 'search_new', 'type': media_type})
        xbmcplugin.addDirectoryItem(HANDLE, 'plugin://%s/?%s' % (ADDON_ID, new_search),
                                    xbmcgui.ListItem(label=ADDON.getLocalizedString(30006)), isFolder=True)
        for query in search_history(media_type):
            target = 'plugin://%s/?%s' % (ADDON_ID, urlencode({'action': 'search_query', 'type': media_type, 'query': query}))
            item = xbmcgui.ListItem(label=query)
            delete_target = 'plugin://%s/?%s' % (ADDON_ID, urlencode({
                'action': 'history_delete', 'type': media_type, 'query': query,
            }))
            clear_target = 'plugin://%s/?%s' % (ADDON_ID, urlencode({
                'action': 'history_clear', 'type': media_type,
            }))
            item.addContextMenuItems([
                (ADDON.getLocalizedString(30013), 'RunPlugin(%s)' % delete_target),
                (ADDON.getLocalizedString(30014), 'RunPlugin(%s)' % clear_target),
            ])
            xbmcplugin.addDirectoryItem(HANDLE, target, item, isFolder=True)
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
        return
    if action in ('history_delete', 'history_clear'):
        media_type = params.get('type', 'movie')
        if media_type not in ('movie', 'series'):
            media_type = 'movie'
        update_search_history(action, params.get('query', ''), media_type)
        return
    if action in ('search_new', 'search_query', 'search_more'):
        media_type = params.get('type', 'movie')
        if media_type not in ('movie', 'series'):
            media_type = 'movie'
        if action == 'search_new':
            title_id = 30012 if media_type == 'series' else 30005
            query = xbmcgui.Dialog().input(ADDON.getLocalizedString(title_id)).strip()
            if query:
                save_search(query, media_type)
                results_url = 'plugin://%s/?%s' % (ADDON_ID, urlencode({
                    'action': 'search_query', 'type': media_type, 'query': query,
                }))
                # Keep a stable search_query URL in Kodi's directory history.
                # Schedule the navigation after this plugin request has ended;
                # Container.Update called here races Kodi's directory callback
                # and can be discarded as "updating in progress".
                xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
                xbmc.executebuiltin(
                    'AlarmClock(KlutMoviesSearch,Container.Update(%s,replace),00:00:01,silent)' % results_url
                )
            else:
                xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)
            return
        else:
            query = params.get('query', '').strip()
        if query:
            save_search(query, media_type)
            show_search_results(query, media_type,
                                params.get('source') if action == 'search_more' else None,
                                params.get('url', '') if action == 'search_more' else '')
        else:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    xbmcplugin.setContent(HANDLE, 'videos')
    for media_type, label_id in (('movie', 30005), ('series', 30012)):
        search_item = xbmcgui.ListItem(label=ADDON.getLocalizedString(label_id))
        search_item.setArt({'icon': ADDON.getAddonInfo('icon'), 'thumb': ADDON.getAddonInfo('icon')})
        target = 'plugin://%s/?%s' % (ADDON_ID, urlencode({'action': 'search', 'type': media_type}))
        xbmcplugin.addDirectoryItem(HANDLE, target, search_item, isFolder=True)
    for string_id, addon_id, name in SOURCES:
        target = 'plugin://%s/' % addon_id
        item = xbmcgui.ListItem(label=ADDON.getLocalizedString(int(string_id)))
        icon = 'special://home/addons/%s/resources/icon.png' % addon_id
        item.setArt({'icon': icon, 'thumb': icon})
        item.setInfo('video', {'title': name, 'plot': ADDON.getLocalizedString(30004)})
        item.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(HANDLE, target, item, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=True)
    if xbmc.getSkinDir() == 'skin.confluence':
        # Keep the hub menu in List even after returning from a thumbnail view.
        xbmc.sleep(100)
        xbmc.executebuiltin('Container.SetViewMode(50)')


if __name__ == '__main__':
    main()
