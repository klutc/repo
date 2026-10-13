"""Load the site's own player in an isolated Chrome process, using CDP."""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from urllib.parse import urlsplit, urlencode, urljoin
from urllib.request import urlopen

class Connection:
    def __init__(self, url):
        p = urlsplit(url)
        self.sock = socket.create_connection((p.hostname, p.port), timeout=3)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(('GET %s HTTP/1.1\r\nHost: %s:%s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (p.path, p.hostname, p.port, key)).encode())
        self.buffer = b''
        while b'\r\n\r\n' not in self.buffer:
            self.buffer += self.sock.recv(4096)
        head, self.buffer = self.buffer.split(b'\r\n\r\n', 1)
        if b' 101 ' not in head:
            raise ValueError('Chrome WebSocket connection failed')
        self.counter = 0

    def read(self, size):
        while len(self.buffer) < size:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ValueError('Chrome connection closed')
            self.buffer += chunk
        value, self.buffer = self.buffer[:size], self.buffer[size:]
        return value

    def frame(self, payload, opcode=1):
        n = len(payload)
        head = bytes([128 | opcode])
        head += bytes([128 | n]) if n < 126 else (bytes([254]) + struct.pack('!H', n) if n < 65536 else bytes([255]) + struct.pack('!Q', n))
        mask = os.urandom(4)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, method, params=None, session=''):
        self.counter += 1
        message = dict(id=self.counter, method=method, params=params or {})
        if session:
            message['sessionId'] = session
        self.frame(json.dumps(message).encode())
        return self.counter

    def receive(self):
        parts = []
        while True:
            first, second = self.read(2)
            self.sock.settimeout(5)
            size = second & 127
            if size == 126:
                size = struct.unpack('!H', self.read(2))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8))[0]
            mask = self.read(4) if second & 128 else None
            data = self.read(size)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            opcode = first & 15
            if opcode == 8:
                raise ValueError('Chrome connection closed')
            if opcode == 9:
                self.frame(data, 10)
                continue
            if opcode == 10:
                continue
            parts.append(data)
            if first & 128:
                return json.loads(b''.join(parts))


CAPTION_SCRIPT = """(()=>{let tracks=[];try{if(typeof jwplayer==='function'){const p=jwplayer();const c=p.getConfig();tracks.push(...(c.tracks||[]));for(const item of p.getPlaylist()||[])tracks.push(...(item.tracks||[]));}}catch(e){}for(const t of document.querySelectorAll('video track'))tracks.push({file:t.src,kind:t.kind,label:t.label,language:t.srclang});return {url:location.href,tracks:tracks.map(t=>({file:t.file||t.src||t.url,kind:t.kind,label:t.label||t.name,language:t.language||t.srclang,default:t.default}))}})()"""

def choose_caption(snapshot):
    if not isinstance(snapshot, dict):
        return ''
    candidates = []
    for track in snapshot.get('tracks', []):
        if track.get('kind') not in ('captions', 'subtitles') or not track.get('file'):
            continue
        url = urljoin(snapshot.get('url', ''), track['file'])
        if not url.startswith(('http://', 'https://')) or '/empty.' in url:
            continue
        language = (str(track.get('language') or '') + ' ' + str(track.get('label') or '')).lower()
        rank = 2 if any(x in language for x in ('bulgar', 'българ', 'bul', 'bg')) else (1 if track.get('default') else 0)
        candidates.append((rank, url))
    return max(candidates, key=lambda x:x[0])[1] if candidates else ''

def resolve(wrapper, progress=None, timeout=55, page_url='', source='', episode=''):
    executable = next((shutil.which(x) for x in ('google-chrome', 'chromium', 'chromium-browser') if shutil.which(x)), None)
    if not executable:
        raise ValueError('Този източник изисква инсталиран Chrome или Chromium.')
    profile = tempfile.mkdtemp(prefix='filmizip-chrome-')
    proc = connection = None
    try:
        args = [executable, '--headless=new', '--disable-gpu', '--mute-audio', '--no-first-run', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank']
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            args.insert(1, '--no-sandbox')
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        port_file = os.path.join(profile, 'DevToolsActivePort')
        while not os.path.exists(port_file):
            if time.monotonic() > deadline or proc.poll() is not None:
                raise ValueError('Chrome не успя да стартира.')
            time.sleep(.1)
        with open(port_file) as f:
            port = int(f.readline())
        with urlopen('http://127.0.0.1:%d/json' % port, timeout=3) as r:
            target = next(t for t in json.load(r) if t.get('type') == 'page')
        connection = Connection(target['webSocketDebuggerUrl'])
        sessions = {''}
        headers = {}
        media = None
        caption = ''
        caption_requests = {}
        caption_deadline = 0
        def enable(session=''):
            connection.send('Target.setAutoAttach', dict(autoAttach=True, waitForDebuggerOnStart=False, flatten=True), session)
            connection.send('Runtime.enable', session=session)
            connection.send('Network.enable', session=session)
        enable()
        connection.send('Page.navigate', dict(url=page_url or wrapper))
        last_click = 0
        script = """(()=>{document.querySelector('.captcha-gate__play')?.click(); document.querySelector('.video-responsive .play')?.click(); try{if(typeof jwplayer==='function') jwplayer().play()}catch(e){}; return navigator.userAgent})()"""
        agent = ''
        if page_url:
            script = """(()=>{if(typeof jQuery==='function'&&document.querySelector('.pmovie__player')&&!window.__filmizipStarted){const source=SOURCE,episode=EPISODE;if(episode) document.querySelector('[data-tv_link=\"'+episode+'\"]')?.click();document.querySelector('[data-link=\"'+source+'\"]')?.click();document.querySelector('.video-responsive .play')?.click();window.__filmizipStarted=!!document.querySelector('.pmovie__player iframe');}document.querySelector('.captcha-gate__play')?.click();try{if(typeof jwplayer==='function')jwplayer().play()}catch(e){}return navigator.userAgent})()""".replace('SOURCE', json.dumps(source)).replace('EPISODE', json.dumps(episode))
        while time.monotonic() < deadline:
            if media and time.monotonic() >= caption_deadline:
                return media, caption
            if progress and progress(int(100 * (1 - (deadline-time.monotonic())/timeout))):
                raise ValueError('Зареждането е отказано.')
            if time.monotonic() - last_click > 2:
                for session in list(sessions):
                    connection.send('Runtime.evaluate', dict(expression=script, returnByValue=True), session)
                last_click = time.monotonic()
            connection.sock.settimeout(.5)
            try:
                msg = connection.receive()
            except socket.timeout:
                continue
            method, data = msg.get('method'), msg.get('params', {})
            if os.environ.get('FILMIZIP_DEBUG') and method == 'Network.responseReceived':
                r=data['response'];print(r['status'],r['url'][:160],flush=True)
            if os.environ.get('FILMIZIP_DEBUG') and 'exceptionDetails' in msg.get('result', {}):
                print(msg,flush=True)
            session = msg.get('sessionId', '')
            if method == 'Target.attachedToTarget':
                child = data['sessionId']
                sessions.add(child)
                enable(child)
            elif method == 'Target.detachedFromTarget':
                sessions.discard(data['sessionId'])
            elif method == 'Network.requestWillBeSent':
                headers[(session, data['requestId'])] = data['request'].get('headers', {})
            elif method == 'Network.responseReceived':
                response = data['response']
                url = response['url']
                if urlsplit(url).hostname == 'upbolt.to' and response['status'] == 403:
                    raise ValueError('Upbolt отказва достъп (HTTP 403 / Cloudflare). Източникът изисква проверка в браузър; изберете друг източник.')
                if response['status'] == 200 and ('master.m3u8' in urlsplit(url).path or urlsplit(url).path.endswith('.mp4')):
                    raw = headers.get((session, data['requestId']), {})
                    play_headers = {k: v for k, v in raw.items() if k.lower() in ('referer', 'origin', 'user-agent')}
                    if not any(k.lower() == 'user-agent' for k in play_headers) and agent:
                        play_headers['User-Agent'] = agent
                    if not media:
                        media = url + '|' + urlencode(play_headers)
                        caption_deadline = min(deadline, time.monotonic() + 4)
                    request = connection.send('Runtime.evaluate', dict(expression=CAPTION_SCRIPT, returnByValue=True), session)
                    caption_requests[request] = session
            elif msg.get('id') in caption_requests:
                snapshot = msg.get('result', {}).get('result', {}).get('value', {})
                selected = choose_caption(snapshot)
                if selected:
                    return media, selected
            elif isinstance(msg.get('result', {}).get('result', {}).get('value'), str):
                agent = msg['result']['result']['value']
        if media:
            return media, caption
        raise ValueError('Плейърът не върна видеоадрес. Възможна е проверка в браузър или недостъпен източник.')
    finally:
        if connection:
            connection.sock.close()
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        shutil.rmtree(profile, ignore_errors=True)
