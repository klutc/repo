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
]
SOURCE_NAMES = {addon_id: name for _, addon_id, name in SOURCES}
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
HISTORY_PATH = os.path.join(PROFILE, 'search_history.json')
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'


def search_history():
    try:
        with open(HISTORY_PATH, 'r', encoding='utf-8') as history_file:
            data = json.load(history_file)
        return [query for query in data if isinstance(query, str) and query.strip()][:10] if isinstance(data, list) else []
    except (OSError, ValueError, TypeError):
        return []


def save_search(query):
    query = query.strip()
    if not query:
        return
    history = [old for old in search_history() if old.casefold() != query.casefold()]
    history.insert(0, query)
    try:
        os.makedirs(PROFILE, exist_ok=True)
        with open(HISTORY_PATH, 'w', encoding='utf-8') as history_file:
            json.dump(history[:10], history_file, ensure_ascii=False)
    except OSError as error:
        xbmc.log('Klutc Movies search history: ' + str(error), xbmc.LOGWARNING)


def show_search_results(query):
    xbmcplugin.setContent(HANDLE, 'movies')
    progress = xbmcgui.DialogProgressBG()
    progress.create(ADDON.getLocalizedString(30005), ADDON.getLocalizedString(30009))
    found = {}
    errors = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(search_sources, addon_id, query, USER_AGENT): addon_id
            for _, addon_id, _ in SOURCES
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
    for _, addon_id, source_name in SOURCES:
        result = found.get(addon_id, {})
        for movie in result.get('items', []):
            title = str(movie.get('name') or movie.get('title') or '').strip()
            url = str(movie.get('url') or '').strip()
            if not title or not url:
                continue
            year = movie.get('year') or 0
            is_bg_audio = addon_id == 'plugin.video.zenoplay' and bool(movie.get('bg_audio'))
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
            params = urlencode({'action': 'browse', 'url': next_page})
            target = 'plugin://%s/?%s' % (addon_id, params)
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
        xbmcgui.Dialog().ok(ADDON.getLocalizedString(30005), message)
    elif errors:
        xbmcgui.Dialog().notification(ADDON.getLocalizedString(30005), ADDON.getLocalizedString(30010), xbmcgui.NOTIFICATION_WARNING)


def main():
    params = dict(parse_qsl(sys.argv[2].lstrip('?')))
    action = params.get('action', 'home')
    if action == 'search':
        xbmcplugin.setContent(HANDLE, 'files')
        xbmcplugin.addDirectoryItem(HANDLE, 'plugin://%s/?action=search_new' % ADDON_ID,
                                    xbmcgui.ListItem(label=ADDON.getLocalizedString(30006)), isFolder=True)
        for query in search_history():
            target = 'plugin://%s/?%s' % (ADDON_ID, urlencode({'action': 'search_query', 'query': query}))
            xbmcplugin.addDirectoryItem(HANDLE, target, xbmcgui.ListItem(label=query), isFolder=True)
        xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
        return
    if action in ('search_new', 'search_query'):
        if action == 'search_new':
            query = xbmcgui.Dialog().input(ADDON.getLocalizedString(30007)).strip()
        else:
            query = params.get('query', '').strip()
        if query:
            save_search(query)
            show_search_results(query)
        else:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    xbmcplugin.setContent(HANDLE, 'videos')
    search_item = xbmcgui.ListItem(label=ADDON.getLocalizedString(30005))
    search_item.setArt({'icon': ADDON.getAddonInfo('icon'), 'thumb': ADDON.getAddonInfo('icon')})
    xbmcplugin.addDirectoryItem(HANDLE, 'plugin://%s/?action=search' % ADDON_ID, search_item, isFolder=True)
    for string_id, addon_id, name in SOURCES:
        target = 'plugin://%s/' % addon_id
        item = xbmcgui.ListItem(label=ADDON.getLocalizedString(int(string_id)))
        icon = 'special://home/addons/%s/resources/icon.png' % addon_id
        item.setArt({'icon': icon, 'thumb': icon})
        item.setInfo('video', {'title': name, 'plot': ADDON.getLocalizedString(30004)})
        item.setProperty('IsPlayable', 'false')
        xbmcplugin.addDirectoryItem(HANDLE, target, item, isFolder=True)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=True)


if __name__ == '__main__':
    main()
