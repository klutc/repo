"""Android WebView hand-off for browser-only MyVidPlay checks."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

import xbmc
import xbmcgui

HELPER_PACKAGE = 'org.klutc.myvidplaybridge'


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
            self.server.result = (address, headers)
            self.server.completed.set()
            self.send_response(200)
            self.send_header('Content-Length', '0')
            self.end_headers()
        except Exception as error:
            xbmc.log('Filmi2K Android bridge callback: ' + str(error), xbmc.LOGWARNING)
            self.send_error(400)

    def log_message(self, fmt, *args):
        pass


def resolve(url, timeout=120):
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
    progress.create('Filmi2K', 'Отваряне на MyVidPlay в Android WebView…')
    try:
        xbmc.executebuiltin('StartAndroidActivity(%s,android.intent.action.VIEW,,%s)' % (HELPER_PACKAGE, intent_uri))
        started = time.monotonic()
        while not server.completed.is_set() and time.monotonic() - started < timeout:
            server.handle_request()
            percent = min(99, int((time.monotonic() - started) * 100 / timeout))
            progress.update(percent, 'Ако се появи проверка, изпълни я и натисни Play в прозореца на MyVidPlay.')
            if progress.iscanceled():
                raise ValueError('Зареждането на MyVidPlay е отказано.')
        if not server.result:
            raise ValueError('Не получих видеоадрес от помощника. Провери дали MyVidPlay Bridge е инсталиран и дали страницата е заредила видеото.')
        address, headers = server.result
        safe_headers = {str(k): str(v) for k, v in headers.items()
                        if str(k).lower() in ('user-agent', 'referer', 'origin', 'cookie')}
        return address + ('|' + urlencode(safe_headers) if safe_headers else ''), ''
    finally:
        progress.close()
        server.server_close()
