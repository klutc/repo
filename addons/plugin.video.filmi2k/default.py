import sys
import os
import json
import xbmcvfs
import xbmcaddon
import traceback
from urllib.parse import parse_qsl, urlencode, urlsplit
import requests
import xbmc
import xbmcgui
import xbmcplugin
import resolveurl
import native_resolver
import browser
import hosts
from catalog import Catalog
from movieinfo import MovieInfo
from labels import movie_label, source_label, movie_year, episode_metadata
import subtitles as subtitle_loader
from parser import BASE, categories, listing, detail, source_rows, search_url

HANDLE = int(sys.argv[1])
ROOT = sys.argv[0]
APP_NAME = 'Filmi2K by Klutc'
ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
APP_ICON = os.path.join(ADDON_PATH,'resources','icon.png')
DIRECTORY_OK = True
THUMBNAILS = False
AUTO_PLAY_URL = ''
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'})
RETURN_URL_PROPERTY = 'Klutc.Filmi2K.ReturnUrl'


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
        xbmc.log('Filmi2K search history: ' + str(error), xbmc.LOGWARNING)

def get(url):
    response = SESSION.get(url, timeout=(10, 30))
    response.raise_for_status()
    response.encoding = 'utf-8'
    if 'Just a moment...' in response.text:
        raise ValueError('Сайтът изисква проверка през браузър. Опитайте по-късно.')
    return response.text

def fill_info(item, data):
    tag = item.getVideoInfoTag()
    data=dict(data,year=movie_year(data))
    title=data.get('name') or data.get('title','')
    tag.setTitle(title)
    item.setProperty('FilmDisplayTitle',movie_label(title,data.get('year',0)))
    item.setProperty('FilmYear',str(data['year']) if data.get('year') else '—')
    tag.setPlot(data.get('plot',''))
    if data.get('year'):tag.setYear(int(data['year']))
    if data.get('genres'):tag.setGenres(data['genres'])
    if data.get('duration'):tag.setDuration(int(data['duration']))
    if data.get('originaltitle'):tag.setOriginalTitle(data['originaltitle'])
    if data.get('tvshowtitle'):tag.setTvShowTitle(data['tvshowtitle'])
    if data.get('season') is not None:tag.setSeason(int(data['season']))
    if data.get('episode') is not None:tag.setEpisode(int(data['episode']))
    tag.setMediaType(data.get('media_type','movie'))
    if data.get('imdb'):tag.setUniqueIDs({'imdb':data['imdb']},'imdb')
    if data.get('rating'):tag.setRating(float(data['rating']))
    icon = data.get('icon') or APP_ICON
    item.setArt({'thumb':icon,'poster':icon,'fanart':data.get('fanart','')})


def add(name, action, url='', icon='', plot='', year=0, genres=None, fanart='', duration=0, originaltitle='', title='', imdb='', rating=0, media_type='movie', source_name='', **extra):
    params = dict(action=action, url=url, name=name, icon=icon)
    params.update(extra)
    year=movie_year(dict(name=name,year=year,originaltitle=originaltitle))
    display=source_label(name,year,source_name) if action=='play' else movie_label(name,year) if action=='detail' else name
    if action == 'detail' and extra.get('bg_audio'):
        display = '[BG] ' + display
    item = xbmcgui.ListItem(label=display)
    fill_info(item,dict(name=name,icon=icon,plot=plot,year=year,genres=genres or [],fanart=fanart,duration=duration,originaltitle=originaltitle,imdb=imdb,rating=rating,media_type=media_type))
    if action == 'play':
        item.setProperty('IsPlayable', 'true')
    if action == 'detail':
        item.setProperty('Filmi2KMovie','true')
        context = ROOT + '?' + urlencode(dict(action='info',url=url,name=name))
        item.addContextMenuItems([('Media Info','RunPlugin(' + context + ')')])
    item_url = ROOT + '?' + urlencode(params)
    xbmcplugin.addDirectoryItem(HANDLE, item_url, item, action != 'play')
    return item_url


def catalog():
    return Catalog(os.path.join(PROFILE,'metadata'),SESSION.headers['User-Agent'])


def browse(url):
    global THUMBNAILS
    xbmcplugin.setContent(HANDLE, 'movies')
    xbmcplugin.setProperty(HANDLE,'Filmi2KCatalog','true')
    items, nextpage = listing(get(url), url)
    progress=xbmcgui.DialogProgressBG()
    progress.create(APP_NAME,'Зареждане на информацията за филмите…')
    try:
        cache=catalog()
        for item in items:
            if item.get('plot'):cache.write(item['url'],item)
        cache.enrich(items,lambda percent:progress.update(percent))
        if cache.failures:
            xbmc.log('Filmi2K metadata: '+str(cache.failures),xbmc.LOGWARNING)
    finally:
        progress.close()
    for movie in items:
        add(action='detail', **movie)
    if nextpage:
        add('Следваща страница >>', 'browse', nextpage)
    THUMBNAILS = True
    if not items:
        xbmcgui.Dialog().notification(APP_NAME, 'Няма намерени заглавия.', xbmcgui.NOTIFICATION_INFO)


def info_dialog(data, name, allow_sources=True, action_label='Пусни филма'):
    data=dict(data,name=name)
    data['year']=movie_year(data)
    dialog=MovieInfo('Filmi2KInfo.xml',ADDON_PATH,'Default','720p',movie=data,allow_sources=allow_sources,action_label=action_label)
    dialog.doModal()
    proceed=dialog.proceed
    del dialog
    return proceed


def show(p):
    global DIRECTORY_OK
    data = detail(get(p['url']), p['url'])
    catalog().write(p['url'],{key:data[key] for key in ('plot','icon','year','genres','fanart','duration','title','originaltitle','imdb','rating','media_type')})
    returned_from_playback = consume_playback_return(p['url'])
    auto_play = False
    if not p.get('episode') and not returned_from_playback and not data.get('is_category'):
        has_episodes = bool(data['episodes'])
        action_label = 'Епизоди' if has_episodes else 'Пусни филма'
        if not info_dialog(data, p.get('name') or data['title'], action_label=action_label):
            DIRECTORY_OK = False
            return
        auto_play = not has_episodes
    xbmcplugin.setContent(HANDLE,'files')
    common={key:data[key] for key in ('plot','icon','year','genres','fanart','duration','originaltitle','imdb','rating','media_type')}
    if data['episodes'] and not p.get('episode'):
        for episode in data['episodes']:
            episode_url=episode.get('url')
            if not episode_url:continue
            add(episode.get('name') or episode.get('title') or 'Епизод', 'detail',episode_url,
                icon=episode.get('icon',''),plot=episode.get('plot',''),year=episode.get('year',0),
                originaltitle=episode.get('originaltitle',''),media_type='episode')
        return
    sources=data['sources']
    if p.get('episode'):
        row=next((e for e in data['episodes'] if str(e.get('episodeNumber'))==p['episode']),None)
        if row:sources=source_rows(row)
    if not sources:
        raise ValueError('Няма налични видеоизточници.')
    first_play_url = ''
    for source, label in sources:
        item_url = add(p.get('name') or data.get('title',''), 'play', p['url'], source=source, source_name=label, episode=p.get('episode', ''), **common)
        if not first_play_url:
            first_play_url = item_url
    if auto_play:
        global AUTO_PLAY_URL
        AUTO_PLAY_URL = first_play_url


def play(p):
    data = detail(get(p['url']), p['url'])
    source_data=data
    if p.get('episode'):
        source_data=next((e for e in data['episodes'] if str(e.get('episodeNumber'))==p['episode']),None)
        if source_data is None:raise ValueError('Епизодът не е намерен.')
    sources=source_rows(source_data) if p.get('episode') else data['sources']
    selected=next((s for s in sources if s[0]==p.get('source')),None)
    if selected is None:raise ValueError('Видеоизточникът вече не е наличен.')
    host,label=selected
    SESSION.headers['Referer']=p['url']
    progress = xbmcgui.DialogProgress()
    slow_host=(urlsplit(host).hostname or '').lower()
    message='Подготовка на плейъра… Първото зареждане може да отнеме няколко минути.' if slow_host.startswith(('byse','filemoon')) else 'Зареждане на видеоизточника…'
    progress.create(APP_NAME, message)
    def update(percent):
        progress.update(percent)
        return progress.iscanceled()
    try:
        try:
            if urlsplit(host).path.endswith(('.m3u8','.mp4','/master.txt')):
                result=(host+'|'+urlencode({'User-Agent':SESSION.headers['User-Agent'],'Referer':p['url']}),'')
            elif urlsplit(host).hostname in ('playmate.to', 'www.playmate.to'):
                result = hosts.playmate(SESSION, host)
            else:
                try:
                    result = native_resolver.resolve(SESSION, host, p['url'], progress=update, cache_directory=os.path.join(PROFILE,'resolver'))
                except native_resolver.UnsupportedHost:
                    result = resolveurl.resolve(host)
            if not result:
                raise ValueError('Не е намерен видеоадрес.')
        except Exception as error:
            if progress.iscanceled():raise
            if xbmc.getCondVisibility('System.Platform.Android'):
                if isinstance(error,requests.exceptions.SSLError):
                    message='Неуспешна проверка на HTTPS сертификата. Проверете датата на телевизора и обновете Kodi.'
                elif isinstance(error,requests.exceptions.HTTPError):
                    message='Видео хостът отказа заявката (HTTP '+str(error.response.status_code)+').'
                elif isinstance(error,requests.exceptions.RequestException):
                    message='Няма връзка с видео хоста. Проверете мрежата и DNS на телевизора.'
                else:message=str(error) or 'Източникът не върна видеоадрес.'
                raise ValueError(message+' Изберете друг източник или опитайте отново.') from error
            xbmc.log('Filmi2K: trying browser player for ' + host.split('?')[0], xbmc.LOGINFO)
            result = browser.resolve(host, progress=update)
    finally:
        progress.close()
    if isinstance(result, (list, tuple)):
        video = result[0] if result else ''
        subtitles = result[1] if len(result) > 1 else ''
    else:
        video, subtitles = result, ''
    if not video:
        raise ValueError('Източникът не се поддържа или временно не работи. Изберете друг.')
    item = xbmcgui.ListItem(path=video)
    if urlsplit(video.split('|')[0]).path.endswith('.mp4'):
        item.setMimeType('video/mp4')
        item.setContentLookup(False)
    elif urlsplit(video.split('|')[0]).path.endswith(('.m3u8', '/master.txt')):
        item.setMimeType('application/vnd.apple.mpegurl')
        item.setContentLookup(False)
    item.setArt({'thumb': p.get('icon', ''), 'poster': p.get('icon', '')})
    title=data.get('title') or p.get('name','')
    if p.get('episode'):title='Епизод '+p['episode']+' — '+title
    video_metadata=episode_metadata(data,p.get('episode',''),host,p.get('url',''))
    fill_info(item,dict(video_metadata,name=title))
    progress = xbmcgui.DialogProgress()
    progress.create(APP_NAME, 'Зареждане на български субтитри…')
    try:
        directory = os.path.join(xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile')), 'subtitles')
        track = subtitle_loader.select(subtitles,host) or subtitle_loader.select(source_data.get('subtitles',[]),host)
        local = subtitle_loader.download(video, track, directory, progress=update)
        if local:
            item.setSubtitles([local])
    except Exception as error:
        xbmc.log('Filmi2K subtitles: ' + str(error), xbmc.LOGWARNING)
        xbmcgui.Dialog().notification(APP_NAME, 'Субтитрите не се заредиха: ' + str(error), xbmcgui.NOTIFICATION_WARNING)
    finally:
        progress.close()
    xbmcgui.Window(10000).setProperty(RETURN_URL_PROPERTY, p['url'])
    xbmcplugin.setResolvedUrl(HANDLE, True, item)

p = dict(parse_qsl(sys.argv[2].lstrip('?')))
action = p.get('action', 'home')
if action not in ('detail', 'play'):
    xbmcgui.Window(10000).clearProperty(RETURN_URL_PROPERTY)
try:
    if action != 'info':
        xbmcplugin.setProperty(HANDLE,'Filmi2KCatalog','false')
    if action == 'home':
        add('Търсене', 'search')
        add('Последно добавени', 'browse', BASE + '?filter=latest')
        for name, url in categories(get(BASE)):
            add(name, 'browse', url)
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
            browse(search_url(query.strip()))
    elif action == 'search_query':
        query = p.get('query', '').strip()
        if query:
            save_search(query)
            browse(search_url(query))
    elif action == 'detail':
        show(p)
    elif action == 'info':
        info_dialog(catalog().fetch(p['url']),p.get('name',''),allow_sources=False)
    elif action == 'play':
        play(p)
except Exception as error:
    xbmc.log('Filmi2K: ' + traceback.format_exc(), xbmc.LOGERROR)
    xbmcgui.Dialog().ok(APP_NAME, str(error))
    if action == 'play':
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
finally:
    if action not in ('play','info'):
        xbmcplugin.endOfDirectory(HANDLE,succeeded=DIRECTORY_OK)
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
