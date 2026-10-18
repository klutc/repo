"""Convert finite HLS WebVTT subtitle playlists into a local UTF-8 SRT."""
import hashlib
import gzip
import os
import re
import html
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, parse_qsl
import requests

STAMP = r'(?:\d{2,}:)?\d{2}:\d{2}[.,]\d{3}'
CUE = re.compile(r'('+STAMP+r')\s*-->\s*('+STAMP+r')[^\n]*\n(.*?)(?=\n\s*\n|\Z)', re.S)

def split_url(url):
    address, _, raw = url.partition('|')
    return address, dict(parse_qsl(raw))

def cues(text):
    result = []
    for match in CUE.finditer(text.replace('\r', '')):
        a, b, body = match.groups()
        def normalize(stamp):
            stamp = stamp.replace('.', ',')
            return stamp if stamp.count(':') == 2 else '00:' + stamp
        result.append((normalize(a), normalize(b), html.unescape(body.strip())))
    return result

def srt(blocks):
    rows = sorted(set(row for block in blocks for row in cues(block)))
    return '\n\n'.join('%d\n%s --> %s\n%s' % (i, a, b, text) for i, (a,b,text) in enumerate(rows, 1)) + '\n'

def download(video, subtitle, directory, progress=None, timeout=55):
    address, headers = split_url(video)
    subaddress, subheaders = split_url(subtitle or '')
    encoding = subheaders.pop('_encoding', 'utf-8')
    headers.update(subheaders)
    session = requests.Session()
    def get(url):
        response = session.get(url, headers=headers, timeout=(5,15))
        response.raise_for_status()
        content = response.content
        if content.startswith(b'\x1f\x8b'):
            content = gzip.decompress(content)
        try:
            return content.decode(encoding if url == subaddress else 'utf-8-sig').lstrip('\ufeff')
        except (LookupError, UnicodeDecodeError):
            return content.decode('utf-8-sig', errors='replace').lstrip('\ufeff')
    if not subaddress:
        if '.m3u8' not in address:
            return ''
        master = get(address)
        tracks = []
        for line in master.splitlines():
            if line.startswith('#EXT-X-MEDIA:') and 'TYPE=SUBTITLES' in line:
                attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', line))
                if attrs.get('URI'):
                    tracks.append(attrs)
        if not tracks:
            return ''
        track = next((t for t in tracks if t.get('LANGUAGE', '').lower() in ('bg','bul') or 'българ' in t.get('NAME','').lower()), tracks[0])
        subaddress = urljoin(address, track['URI'])
    key = hashlib.sha256(subaddress.split('?')[0].encode()).hexdigest()[:24]
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, key + '.bg.srt')
    if os.path.isfile(target) and time.time() - os.path.getmtime(target) < 86400:
        return target
    content = get(subaddress)
    if content.lstrip().startswith('#EXTM3U'):
        if '#EXT-X-ENDLIST' not in content:
            raise ValueError('Субтитрите са в непълен HLS списък.')
        urls = [urljoin(subaddress, l.strip()) for l in content.splitlines() if l.strip() and not l.startswith('#')]
        if not urls or len(urls) > 3000:
            raise ValueError('Невалиден списък със субтитри.')
        local = threading.local()
        end = time.monotonic() + timeout
        def segment(url):
            if time.monotonic() > end:
                raise ValueError('Времето за зареждане на субтитрите изтече.')
            if not hasattr(local, 'session'):
                local.session = requests.Session()
            r = local.session.get(url, headers=headers, timeout=(5,10))
            r.raise_for_status()
            text = r.content.decode('utf-8-sig')
            if not text.lstrip().startswith('WEBVTT'):
                raise ValueError('Невалиден сегмент със субтитри.')
            return text
        blocks = []
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(segment, u) for u in urls]
            try:
                for future in as_completed(futures):
                    blocks.append(future.result())
                    if progress and progress(int(len(blocks)*100/len(urls))):
                        raise ValueError('Зареждането е отказано.')
            except Exception:
                for f in futures:
                    f.cancel()
                raise
        content = srt(blocks)
    elif content.lstrip().startswith('WEBVTT'):
        content = srt([content])
    if not cues(content):
        raise ValueError('Не са намерени субтитри във файла.')
    temp = target + '.tmp'
    with open(temp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(temp, target)
    return target


def select(value, base=''):
    candidates=[]
    def visit(item,label=''):
        if isinstance(item,str):
            if item.startswith(('https://','http://')):
                language=label.lower();score=2 if any(x in language for x in ('bulgar','българ','bg','bul')) else 0
                candidates.append((score,item))
        elif isinstance(item,list):
            for child in item:visit(child,label)
        elif isinstance(item,dict):
            url=next((item[k] for k in ('file','src','url','file_path','sf') if isinstance(item.get(k),str)),None)
            if url:visit(urljoin(base,url),str(item.get('label') or item.get('language') or item.get('srclang') or label))
            else:
                for language,child in item.items():visit(child,str(language))
    visit(value)
    return max(candidates,key=lambda x:x[0])[1] if candidates else ''
