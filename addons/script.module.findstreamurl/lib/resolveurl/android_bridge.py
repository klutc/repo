"""Android WebView hand-off for video hosts with browser-managed checks."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlsplit

import xbmc
import xbmcgui

HELPER_PACKAGE = 'org.klutc.myvidplaybridge'
HOST_DOMAINS = (
    'myvidplay.com', 'playmogo.com', 'upbolt.to', 'upbolt.com',
    'streamtape.com', 'strtape.cloud', 'streamtape.net', 'streamta.pe', 'streamtape.site',
    'strcloud.link', 'strtpe.link', 'streamtape.cc', 'scloud.online', 'stape.fun',
    'streamadblockplus.com', 'shavetape.cash', 'streamtape.to', 'streamta.site', 'streamadblocker.xyz',
    'embedorigin.cc', 'content.st', 'bysefujedu.com',
)
VIDSRC_DOMAINS = ('vidsrc-embed.ru', 'vidsrc.me', 'vidsrc.sh', 'vidsrcme.ru')


def supports_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    return parsed.scheme == 'https' and any(host == domain or host.endswith('.' + domain)
                                            for domain in HOST_DOMAINS)


def is_vidsrc_embed_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    return parsed.scheme == 'https' and any(host == domain or host.endswith('.' + domain)
                                            for domain in VIDSRC_DOMAINS)


def is_cloudflare_error(error):
    message = str(error).lower()
    return any(marker in message for marker in ('cloudflare', 'turnstile', 'cf-chl-', 'captcha-gate'))


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        expected = '/resolve/' + self.server.token
        if self.path != expected:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 32768:
                raise ValueError('Invalid callback size')
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            address = payload.get('url', '')
            headers = payload.get('headers', {})
            if not isinstance(address, str) or not address.startswith(('https://', 'http://')):
                raise ValueError('Invalid media URL')
            if not isinstance(headers, dict):
                headers = {}
            subtitle = payload.get('subtitle', '')
            subtitle_headers = payload.get('subtitle_headers', {})
            if not isinstance(subtitle, str):
                subtitle = ''
            if not isinstance(subtitle_headers, dict):
                subtitle_headers = {}
            self.server.result = (address, headers, subtitle, subtitle_headers)
            self.server.completed.set()
            self.send_response(200)
            self.send_header('Content-Length', '0')
            self.end_headers()
        except Exception as error:
            xbmc.log('Android WebView bridge callback: ' + str(error), xbmc.LOGWARNING)
            self.send_error(400)

    def log_message(self, fmt, *args):
        pass


def resolve(url, timeout=180):
    """Launch the companion WebView and wait for its media URL callback."""
    import secrets

    token = secrets.token_urlsafe(18)
    server = HTTPServer(('127.0.0.1', 0), _CallbackHandler)
    server.timeout = 1
    server.token = token
    server.completed = threading.Event()
    server.result = None
    callback = 'http://127.0.0.1:%d/resolve/%s' % (server.server_port, token)
    intent_uri = 'klutcmyvidplay://resolve?' + urlencode({'url': url, 'callback': callback})
    progress = xbmcgui.DialogProgress()
    progress.create('Video helper', 'Отваряне на видеоизточника в Android WebView…')
    try:
        xbmc.executebuiltin('StartAndroidActivity(%s,android.intent.action.VIEW,,%s)' % (HELPER_PACKAGE, intent_uri))
        started = time.monotonic()
        while not server.completed.is_set() and time.monotonic() - started < timeout:
            server.handle_request()
            percent = min(99, int((time.monotonic() - started) * 100 / timeout))
            progress.update(percent, 'Премини проверката, ако се появи. На Android TV натисни OK в центъра на плеъра.')
            if progress.iscanceled():
                raise ValueError('Зареждането на видеоизточника е отказано.')
        if not server.result:
            raise ValueError('Не получих видеоадрес от помощника. Провери дали MyVidPlay Bridge е инсталиран и дали страницата е заредила видеото.')
        address, headers, subtitle, subtitle_headers = server.result
        safe_headers = {str(k): str(v) for k, v in headers.items()
                        if str(k).lower() in ('user-agent', 'referer', 'origin', 'cookie')}
        safe_subtitle_headers = {str(k): str(v) for k, v in subtitle_headers.items()
                                 if str(k).lower() in ('user-agent', 'referer', 'origin', 'cookie')}
        video = address + ('|' + urlencode(safe_headers) if safe_headers else '')
        track = subtitle + ('|' + urlencode(safe_subtitle_headers) if safe_subtitle_headers else '')
        return video, track
    finally:
        progress.close()
        server.server_close()
