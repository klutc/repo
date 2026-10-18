import os
import json
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode, urlsplit

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
import resolveurl
from resolveurl import android_bridge
import native_resolver
import browser
import hosts
import bgplayer
import tmdb_cast
import subtitles as subtitle_loader
from movieinfo import MovieInfo
from labels import movie_label, source_label, movie_year, episode_metadata, bg_audio_label
from parser import BASE, categories, listing, collection_listing, metadata, is_bg_audio, providers, search_url, catalogue_url

HANDLE = int(sys.argv[1])
ROOT = sys.argv[0]
APP_NAME = 'ZenoPlay by Klutc'
ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
APP_ICON = os.path.join(ADDON_PATH, 'resources', 'icon.png')
DIRECTORY_OK = True
THUMBNAILS = False
AUTO_PLAY_URL = ''
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'})
RETURN_URL_PROPERTY = 'Klutc.ZenoPlay.ReturnUrl'


def consume_playback_return(url):
    window = xbmcgui.Window(10000)
    previous = window.getProperty(RETURN_URL_PROPERTY)
    if previous:
        window.clearProperty(RETURN_URL_PROPERTY)
    return bool(previous and previous == url)

def get_search_history():
    try:
        with open(os.path.join(PROFILE, 'search_history.json'), 'r', encoding='utf-8') as history_file:
            history = json.load(history_file)
        return [query for query in history if isinstance(query, str) and query.strip()][:10] if isinstance(history, list) else []
    except (OSError, ValueError, TypeError):
        return []

def save_search(query):
    query = query.strip()
    if not query:
        return
    history = [item for item in get_search_history() if item.casefold() != query.casefold()]
    history.insert(0, query)
    try:
        with open(os.path.join(PROFILE, 'search_history.json'), 'w', encoding='utf-8') as history_file:
            json.dump(history[:10], history_file, ensure_ascii=False)
    except OSError as error:
        xbmc.log('ZenoPlay search history: ' + str(error), xbmc.LOGWARNING)
BG_AUDIO_CACHE = {}
BG_AUDIO_CACHE_PATH = os.path.join(PROFILE, 'bg_audio_cache.json')


def mark_bg_audio(items):
    """Mark titles from any listing by reading and caching their genre chips."""
    global BG_AUDIO_CACHE
    if not BG_AUDIO_CACHE:
        try:
            with open(BG_AUDIO_CACHE_PATH, 'r', encoding='utf-8') as cache_file:
                BG_AUDIO_CACHE = json.load(cache_file)
        except (OSError, ValueError, TypeError):
            BG_AUDIO_CACHE = {}

    pending = [item for item in items
               if not item.get('bg_audio') and item.get('url') not in BG_AUDIO_CACHE]

    def read_membership(item):
        response = SESSION.get(item['url'], headers={'Referer': BASE}, timeout=(8, 20))
        response.raise_for_status()
        response.encoding = 'utf-8'
        return item['url'], is_bg_audio(response.text)

    changed = False
    if pending:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(read_membership, item) for item in pending]
            for future in as_completed(futures):
                try:
                    url, has_audio = future.result()
                    BG_AUDIO_CACHE[url] = has_audio
                    changed = True
                except Exception as error:
                    xbmc.log('ZenoPlay BG Audio lookup: ' + str(error), xbmc.LOGDEBUG)
    if changed:
        try:
            os.makedirs(PROFILE, exist_ok=True)
            with open(BG_AUDIO_CACHE_PATH, 'w', encoding='utf-8') as cache_file:
                json.dump(BG_AUDIO_CACHE, cache_file, ensure_ascii=False)
        except OSError as error:
            xbmc.log('ZenoPlay BG Audio cache: ' + str(error), xbmc.LOGDEBUG)

    for item in items:
        item['bg_audio'] = item.get('bg_audio') or BG_AUDIO_CACHE.get(item.get('url'), False)


def get(url):
    response = SESSION.get(url, timeout=(10, 30))
    response.raise_for_status()
    response.encoding = 'utf-8'
    if 'Just a moment...' in response.text or 'Attention Required! | Cloudflare' in response.text:
        raise ValueError('ZenoPlay изисква проверка в браузър или временно ограничава връзката.')
    return response.text


def fill_info(item, data):
    tag = item.getVideoInfoTag()
    data = dict(data, year=movie_year(data))
    title = data.get('name') or data.get('title', '')
    tag.setTitle(title)
    item.setProperty('FilmDisplayTitle', bg_audio_label(movie_label(title, data.get('year', 0)), data))
    item.setProperty('FilmYear', str(data['year']) if data.get('year') else '—')
    tag.setPlot(data.get('plot', ''))
    if data.get('year'):
        tag.setYear(int(data['year']))
    if data.get('genres'):
        tag.setGenres(data['genres'])
    if data.get('originaltitle'):
        tag.setOriginalTitle(data['originaltitle'])
    if data.get('tvshowtitle'):
        tag.setTvShowTitle(data['tvshowtitle'])
    if data.get('season') is not None:
        tag.setSeason(int(data['season']))
    if data.get('episode') is not None:
        tag.setEpisode(int(data['episode']))
    tag.setMediaType(data.get('media_type', 'movie'))
    if data.get('imdb'):
        tag.setUniqueIDs({'imdb': data['imdb']}, 'imdb')
    if data.get('rating'):
        tag.setRating(float(data['rating']))
    icon = data.get('icon') or APP_ICON
    item.setArt({'thumb': icon, 'poster': icon, 'fanart': data.get('fanart', '')})


def add(name, action, url='', data=None, source='', source_name='', **extra):
    data = data or {}
    params = dict(action=action, url=url, name=name, source=source, episode=extra.get('episode', ''))
    if data.get('bg_audio'):
        params['bg_audio'] = '1'
    params.update(extra)
    year = movie_year(data)
    flagged_name = bg_audio_label(name, data)
    label = source_label(flagged_name, year, source_name) if action == 'play' else movie_label(flagged_name, year) if action in ('detail', 'episode') else name
    item = xbmcgui.ListItem(label=label)
    item_data = dict(data, name=name)
    if action == 'episode':
        item_data.update(media_type='episode', season=extra.get('season'), episode=extra.get('episode'), tvshowtitle=data.get('originaltitle') or name)
        label = 'S%02dE%02d — %s' % (int(extra.get('season') or 0), int(extra.get('episode') or 0), flagged_name)
        item.setLabel(label)
    fill_info(item, item_data)
    if action == 'play':
        item.setProperty('IsPlayable', 'true')
    if action in ('detail', 'episode'):
        item.setProperty('ZenoPlayMovie', 'true')
        context = ROOT + '?' + urlencode(dict(action='info', url=url, name=name))
        item.addContextMenuItems([('Media Info', 'RunPlugin(' + context + ')')])
    item_url = ROOT + '?' + urlencode(params)
    xbmcplugin.addDirectoryItem(HANDLE, item_url, item, action != 'play')
    return item_url


def info_dialog(data, name, allow_sources=True, action_label='Пусни филма'):
    data = dict(data, name=name)
    dialog = MovieInfo('ZenoPlayInfo.xml', ADDON_PATH, 'Default', '720p', movie=data,
                       allow_sources=allow_sources, action_label=action_label)
    dialog.doModal()
    proceed = dialog.proceed
    del dialog
    return proceed


def fetch_detail(url):
    data = metadata(get(url), url)
    if (ADDON.getSetting('tmdb_cast_enabled') == 'true' and
            ADDON.getSetting('tmdb_read_token').strip() and data.get('tmdb')):
        try:
            media_type = 'tv' if data.get('panel_type') in ('tv', 'episode') else data.get('media_type', 'movie')
            data['actors'] = tmdb_cast.lookup(SESSION, media_type, data['tmdb'],
                                              ADDON.getSetting('tmdb_read_token'),
                                              os.path.join(PROFILE, 'metadata'))
        except Exception as error:
            xbmc.log('ZenoPlay TMDb cast: ' + str(error), xbmc.LOGDEBUG)
    return data


def browse(url):
    global THUMBNAILS
    path = urlsplit(url).path.rstrip('/')
    is_collection_index = path == '/collections' or bool(re.fullmatch(r'/collections/page/\d+', path))
    if is_collection_index:
        xbmcplugin.setContent(HANDLE, 'files')
        xbmcplugin.setProperty(HANDLE, 'ZenoPlayCatalog', 'false')
        collection_rows, next_page = collection_listing(get(url), url)
        for label, target in collection_rows:
            add(label, 'browse', target)
        if next_page:
            add('Следваща страница >>', 'browse', next_page)
        THUMBNAILS = False
        if not collection_rows:
            xbmcgui.Dialog().notification(APP_NAME, 'Няма намерени колекции.', xbmcgui.NOTIFICATION_INFO)
        return

    xbmcplugin.setContent(HANDLE, 'tvshows' if '/tv-shows/' in url else 'movies')
    xbmcplugin.setProperty(HANDLE, 'ZenoPlayCatalog', 'true')
    items, next_page = listing(get(url), url)
    mark_bg_audio(items)
    for item in items:
        add(item['name'], 'detail', item['url'], item)
    if next_page:
        add('Следваща страница >>', 'browse', next_page)
    THUMBNAILS = True
    if not items:
        xbmcgui.Dialog().notification(APP_NAME, 'Няма намерени заглавия.', xbmcgui.NOTIFICATION_INFO)


def show(data, name, auto_play=False):
    global DIRECTORY_OK, AUTO_PLAY_URL
    if data['media_type'] == 'tvshow':
        if not data['episodes']:
            raise ValueError('Не са намерени епизоди за този сериал.')
        xbmcplugin.setContent(HANDLE, 'episodes')
        for row in data['episodes']:
            add(name, 'episode', row['url'], data, season=row['season'], episode=row['episode'], plot=row.get('plot') or data['plot'])
        return
    sources = providers(data, SESSION)
    if not sources:
        raise ValueError('ZenoPlay не върна активни видеоизточници за това заглавие.')
    xbmcplugin.setContent(HANDLE, 'files')
    first_play_url = ''
    for address, label in sources:
        item_url = add(name, 'play', data['url'], data, source=address, source_name=label)
        if not first_play_url:
            first_play_url = item_url
    if auto_play:
        AUTO_PLAY_URL = first_play_url


def resolve(source, page_url, source_name, episode=''):
    SESSION.headers['Referer'] = page_url
    host = urlsplit(source).hostname or ''
    if host.lower().removeprefix('www.') in ('galaxicon.org', 'playtube.tv', 'rollo.uno'):
        return bgplayer.resolve(SESSION, source, page_url)
    if xbmc.getCondVisibility('System.Platform.Android') and android_bridge.supports_url(source):
        return android_bridge.resolve(source)
    if urlsplit(source).path.lower().endswith(('.m3u8', '.mp4', '/master.txt')):
        return source + '|' + urlencode({'User-Agent': SESSION.headers['User-Agent'], 'Referer': page_url}), ''
    if host in ('playmate.to', 'www.playmate.to'):
        return hosts.playmate(SESSION, source)
    try:
        return native_resolver.resolve(SESSION, source, page_url, cache_directory=os.path.join(PROFILE, 'resolver'),
                                       prefer_mp4=xbmc.getCondVisibility('System.Platform.Android') and ADDON.getSetting('voe_mp4') != 'false')
    except native_resolver.UnsupportedHost:
        try:
            return resolveurl.resolve(source)
        except Exception as error:
            if (xbmc.getCondVisibility('System.Platform.Android') and
                    android_bridge.is_vidsrc_embed_url(source) and android_bridge.is_cloudflare_error(error)):
                return android_bridge.resolve(source)
            if xbmc.getCondVisibility('System.Platform.Android'):
                raise ValueError('Този видеоизточник не поддържа нативно възпроизвеждане на Android TV: ' + str(error)) from error
            return browser.resolve(source, page_url=page_url, source=source_name, episode=episode)


def play(p):
    data = fetch_detail(p['url'])
    rows = providers(data, SESSION)
    source = p.get('source', '')
    selected = next((row for row in rows if row[0] == source), None)
    if selected is None:
        raise ValueError('Видеоизточникът вече не е наличен.')
    progress = xbmcgui.DialogProgress()
    progress.create(APP_NAME, 'Зареждане на видеоизточника…')
    meta_window = xbmcgui.Window(10000)
    meta_window.clearProperty('findstreamurl.imdb')
    try:
        result = resolve(source, data['url'], selected[1], p.get('episode', ''))
    finally:
        progress.close()
    resolved_imdb = meta_window.getProperty('findstreamurl.imdb')
    meta_window.clearProperty('findstreamurl.imdb')
    if resolved_imdb:
        data['imdb'] = resolved_imdb
    if isinstance(result, (list, tuple)):
        video = result[0] if result else ''
        subtitles = result[1] if len(result) > 1 else ''
    else:
        video, subtitles = result, ''
    if not video:
        raise ValueError('Източникът не върна видеоадрес.')
    item = xbmcgui.ListItem(path=video)
    path = urlsplit(video.split('|')[0]).path.lower()
    if path.endswith('.mp4'):
        item.setMimeType('video/mp4')
        item.setContentLookup(False)
    elif path.endswith(('.m3u8', '/master.txt')):
        item.setMimeType('application/vnd.apple.mpegurl')
        item.setContentLookup(False)
    item.setArt({'thumb': data.get('icon', ''), 'poster': data.get('icon', '')})
    playback_data = episode_metadata(data, p.get('episode', ''), source, data['url'])
    if p.get('episode'):
        playback_data.update(season=data.get('season'), episode=data.get('episode'), media_type='episode')
    fill_info(item, playback_data)
    sub_progress = xbmcgui.DialogProgress()
    sub_progress.create(APP_NAME, 'Зареждане на български субтитри…')
    try:
        directory = os.path.join(PROFILE, 'subtitles')
        local = subtitle_loader.download(video, subtitle_loader.select(subtitles, source), directory)
        if local:
            item.setSubtitles([local])
    except Exception as error:
        xbmc.log('ZenoPlay subtitles: ' + str(error), xbmc.LOGWARNING)
    finally:
        sub_progress.close()
    xbmcgui.Window(10000).setProperty(RETURN_URL_PROPERTY, data['url'])
    xbmcplugin.setResolvedUrl(HANDLE, True, item)


p = dict(parse_qsl(sys.argv[2].lstrip('?')))
action = p.get('action', 'home')
if action not in ('detail', 'episode', 'play'):
    xbmcgui.Window(10000).clearProperty(RETURN_URL_PROPERTY)
try:
    if action != 'info':
        xbmcplugin.setProperty(HANDLE, 'ZenoPlayCatalog', 'false')
    if action == 'home':
        add('Търсене', 'search')
        add('Филми', 'browse', catalogue_url('/movies/'))
        add('Сериали', 'browse', catalogue_url('/tv-shows/'))
        for label, url in categories(get(BASE)):
            add(label, 'browse', url)
    elif action == 'browse':
        browse(p['url'])
    elif action == 'search':
        add('Ново търсене…', 'search_new')
        for query in get_search_history():
            add(query, 'search_query', query=query)
    elif action == 'search_new':
        query = xbmcgui.Dialog().input('Търсене на филм или сериал')
        if query.strip():
            save_search(query)
            browse(search_url(query))
    elif action == 'search_query':
        query = p.get('query', '').strip()
        if query:
            save_search(query)
            browse(search_url(query))
    elif action in ('detail', 'episode'):
        data = fetch_detail(p['url'])
        data['bg_audio'] = data.get('bg_audio') or p.get('bg_audio') == '1'
        name = p.get('name') or data['name']
        if action == 'episode':
            data['season'] = int(p.get('season') or data.get('season') or 0) or None
            data['episode'] = int(p.get('episode') or data.get('episode') or 0) or None
        returned_from_playback = consume_playback_return(p['url'])
        auto_play = False
        if not returned_from_playback:
            if action == 'episode':
                action_label = 'Пусни епизода'
                auto_play = True
            elif data['media_type'] == 'tvshow':
                action_label = 'Епизоди'
            else:
                action_label = 'Пусни филма'
                auto_play = True
            if not info_dialog(data, name, action_label=action_label):
                DIRECTORY_OK = False
                auto_play = False
        if DIRECTORY_OK:
            show(data, name, auto_play=auto_play)
    elif action == 'info':
        info_dialog(fetch_detail(p['url']), p.get('name', ''), allow_sources=False)
    elif action == 'play':
        play(p)
except Exception as error:
    xbmc.log('ZenoPlay: ' + traceback.format_exc(), xbmc.LOGERROR)
    xbmcgui.Dialog().ok(APP_NAME, str(error))
    if action == 'play':
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
finally:
    if action not in ('play', 'info'):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=DIRECTORY_OK)
        if action in ('home', 'search') and xbmc.getSkinDir() == 'skin.confluence':
            # Kodi may carry the last category's thumbnail view to this menu.
            xbmc.sleep(100)
            xbmc.executebuiltin('Container.SetViewMode(50)')
        elif THUMBNAILS and xbmc.getSkinDir() == 'skin.confluence':
            # Let Kodi finish switching to the new container before selecting
            # its view; otherwise the command can affect the previous folder.
            xbmc.sleep(100)
            xbmc.executebuiltin('Container.SetViewMode(500)')
        if AUTO_PLAY_URL and DIRECTORY_OK:
            xbmc.executebuiltin('PlayMedia(' + AUTO_PLAY_URL + ')')
