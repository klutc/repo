"""Portable HTTP resolvers: no subprocesses, browser or platform-specific APIs."""
import base64
import codecs
import json
import re
import requests
from urllib.parse import urljoin, urlsplit, urlencode
from bs4 import BeautifulSoup

class UnsupportedHost(ValueError):
    pass


def fetch(session,url,referer=''):
    response=session.get(url,headers={'Referer':referer} if referer else {},timeout=(10,25))
    response.raise_for_status()
    response.encoding='utf-8'
    return response.text,response.url


def play_url(session,url,referer):
    if not isinstance(url,str) or not url.startswith(('http://','https://')):
        raise ValueError('Плейърът не върна валиден видеоадрес.')
    return url+'|'+urlencode({'User-Agent':session.headers['User-Agent'],'Referer':referer})


def caption(tracks,base):
    candidates=[]
    for row in tracks or []:
        if not isinstance(row,dict) or row.get('kind') not in ('captions','subtitles'):continue
        file=row.get('file') or row.get('src') or row.get('url')
        if not file or '/empty.' in file:continue
        language=str(row.get('label') or row.get('language') or '').lower()
        score=2 if language in ('bg','bul','bulgarian','български') else 1 if row.get('default') else 0
        candidates.append((score,urljoin(base,file)))
    return max(candidates,key=lambda row:row[0])[1] if candidates else ''


def decode_voe(encoded,script):
    # The site's loader applies ROT13, removes delimiters, then decodes two
    # Base64 layers with a character shift and reversal between them.
    tables=re.findall(r'''\[(?:\s*(?:'[^']{2}'|"[^"]{2}")\s*,?){1,12}\s*\]''',script)
    for table in tables:
        value=codecs.decode(encoded,'rot_13')
        for token in re.findall(r'''["']([^"']{2})["']''',table):value=value.replace(token,'')
        try:
            layer=base64.b64decode(value).decode('latin1')
            layer=''.join(chr(ord(ch)-3) for ch in layer)[::-1]
            data=json.loads(base64.b64decode(layer))
            if isinstance(data,dict) and any(data.get(k) for k in ('source','file','direct_access_url')):return data
        except (ValueError,TypeError,UnicodeError):continue
    raise ValueError('VOE промени формата на плейъра; директното зареждане не успя.')


def voe(session,url,referer,prefer_mp4=False):
    visited=set()
    for _ in range(5):
        if url in visited:raise ValueError('VOE връща циклично пренасочване.')
        visited.add(url)
        html,current=fetch(session,url,referer)
        redirect=re.search(r"window\.location\.href\s*=\s*['\"](https?://[^'\"]+)['\"]",html)
        if redirect:
            referer=current;url=redirect[1];continue
        soup=BeautifulSoup(html,'html.parser')
        for node in soup.select('script[type="application/json"]'):
            try:data=json.loads(node.string or node.get_text())
            except ValueError:continue
            if not isinstance(data,list) or not data or not isinstance(data[0],str):continue
            loader=node.find_next('script',src=True)
            if not loader:continue
            code,_=fetch(session,urljoin(current,loader['src']),current)
            decoded=decode_voe(data[0],code)
            video=decoded.get('source') or decoded.get('file') or decoded.get('direct_access_url')
            direct=decoded.get('direct_access_url')
            if prefer_mp4 and isinstance(direct,str) and direct.startswith(('http://','https://')):
                try:
                    with session.get(direct,headers={'Referer':current,'Range':'bytes=0-1023'},timeout=(10,15),stream=True) as response:
                        response.raise_for_status()
                        prefix=next(response.iter_content(1024),b'')
                        if b'ftyp' in prefix[:64]:video=direct
                except requests.RequestException:
                    pass
            return play_url(session,video,current),caption(decoded.get('captions'),current)
        raise ValueError('VOE не предоставя достъпен плейър за това видео.')
    raise ValueError('VOE върна прекалено много пренасочвания.')


def vidmoly(session,url,referer):
    html,current=fetch(session,url,referer)
    source=re.search(r"sources\s*:\s*\[\s*\{\s*file\s*:\s*(['\"])(.*?)\1",html,re.S)
    if not source:raise ValueError('VIDM не върна видеоадрес; възможно е ограничение от хоста.')
    tracks=[]
    for block in re.findall(r'\{[^{}]{0,1500}\}',html,re.S):
        kind=re.search(r"['\"]?kind['\"]?\s*:\s*['\"](captions|subtitles)['\"]",block)
        file=re.search(r"['\"]?file['\"]?\s*:\s*(['\"])(.*?)\1",block,re.S)
        if not kind or not file:continue
        label=re.search(r"['\"]?label['\"]?\s*:\s*(['\"])(.*?)\1",block,re.S)
        tracks.append(dict(kind=kind[1],file=file[2],label=label[2] if label else ''))
    return play_url(session,urljoin(current,source[2]),current),caption(tracks,current)


def resolve(session,url,referer,progress=None,cache_directory='',prefer_mp4=False):
    host=(urlsplit(url).hostname or '').lower()
    if host.startswith('www.'):host=host[4:]
    if host in ('myvidplay.com','playmogo.com'):
        # MyVidPlay is a DoodStream embed alias. Resolve it explicitly instead
        # of letting ResolveURL's catch-all ReelTube resolver inspect it; the
        # generic resolver order can differ between Kodi platforms.
        match=re.search(r'/(?:e|d)/([0-9a-zA-Z]+)(?:/|$)',urlsplit(url).path)
        if not match:raise ValueError('MyVidPlay връзката няма валиден идентификатор.')
        try:
            from resolveurl.plugins.doodstream import DoodStreamResolver
            result=DoodStreamResolver().get_media_url(host,match[1],subs=True)
        except Exception as error:
            raise ValueError('MyVidPlay/DoodStream не успя да зареди видеото: '+str(error)) from error
        if not result or not result[0]:raise ValueError('MyVidPlay/DoodStream не върна видео адрес.')
        return result
    if host=='voe.sx' or host.startswith('voe-unblock.'):return voe(session,url,referer,prefer_mp4=prefer_mp4)
    if host in ('vidmoly.biz','vidmoly.me','vidmoly.to','vidmoly.net'):return vidmoly(session,url,referer)
    if host in ('vsembed.su','vsembed.ru','vsembed.com'):
        import vsembed
        return vsembed.resolve(session,url,referer,progress=progress)
    if re.fullmatch(r'byse[a-z]*\.(?:com|sx)',host) or host in ('filemoon.sx','filemoon.to','filemoon.in','streamlyplayer.online'):
        import byse_native
        return byse_native.resolve(session,url,referer,progress=progress,cache_directory=cache_directory)
    if host in ('upbolt.to','upbolt.com'):
        response=session.get(url,headers={'Referer':referer},timeout=(10,25))
        if response.status_code==403 and ('_cf_chl_opt' in response.text or 'challenge-platform' in response.text):
            raise ValueError('Upbolt блокира достъпа с проверка на Cloudflare. Директният плейър на Kodi не може да я изпълни; изберете друг източник.')
    raise UnsupportedHost(host)
