package org.klutc.myvidplaybridge;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public final class MainActivity extends Activity {
    private final AtomicBoolean delivered = new AtomicBoolean(false);
    private WebView webView;
    private String callback;
    private String userAgent;
    private String referer;
    private volatile String mediaUrl;
    private volatile Map<String, String> mediaHeaders;
    private volatile String subtitleUrl = "";
    private volatile Map<String, String> subtitleHeaders;
    private final AtomicBoolean deliveryScheduled = new AtomicBoolean(false);

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        String target = getIntent().getData() == null ? null : getIntent().getData().getQueryParameter("url");
        callback = getIntent().getData() == null ? null : getIntent().getData().getQueryParameter("callback");
        if (!isAllowedTarget(target) || !isLocalCallback(callback)) {
            finish();
            return;
        }
        referer = target;

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(Color.BLACK);
        TextView hint = new TextView(this);
        hint.setText("Видеоизточник: премини проверката, ако се появи. Натисни OK в центъра на плеъра. Kodi ще продължи автоматично.");
        hint.setTextColor(Color.WHITE);
        hint.setTextSize(16);
        hint.setPadding(20, 14, 20, 14);
        hint.setGravity(Gravity.CENTER_VERTICAL);
        layout.addView(hint, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        webView = new WebView(this);
        layout.addView(webView, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(layout);

        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setMediaPlaybackRequiresUserGesture(false);
        userAgent = webView.getSettings().getUserAgentString();
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, true);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override public android.webkit.WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                inspectRequest(request.getUrl().toString(), request.getRequestHeaders());
                return null;
            }

            @Override public android.webkit.WebResourceResponse shouldInterceptRequest(WebView view, String address) {
                inspectRequest(address, null);
                return null;
            }
        });
        webView.loadUrl(target);
    }

    private boolean isAllowedTarget(String value) {
        if (value == null) return false;
        try {
            URI uri = new URI(value);
            String host = uri.getHost();
            if (!"https".equalsIgnoreCase(uri.getScheme()) || host == null) return false;
            host = host.toLowerCase();
            if (host.equals("filmizip.com") && "/player.html".equals(uri.getPath())) return true;
            String[] domains = {
                    "myvidplay.com", "playmogo.com", "upbolt.to", "upbolt.com",
                    "streamtape.com", "strtape.cloud", "streamtape.net", "streamta.pe", "streamtape.site",
                    "strcloud.link", "strtpe.link", "streamtape.cc", "scloud.online", "stape.fun",
                    "streamadblockplus.com", "shavetape.cash", "streamtape.to", "streamta.site", "streamadblocker.xyz",
                    "vidsrc-embed.ru", "vidsrc.me", "vidsrc.sh", "vidsrcme.ru",
                    "embedorigin.cc", "content.st", "bysefujedu.com"
            };
            for (String domain : domains) {
                if (host.equals(domain) || host.endsWith("." + domain)) return true;
            }
            return false;
        } catch (Exception ignored) { return false; }
    }

    private boolean isLocalCallback(String value) {
        if (value == null) return false;
        try {
            URI uri = new URI(value);
            String path = uri.getPath();
            return "http".equalsIgnoreCase(uri.getScheme()) && "127.0.0.1".equals(uri.getHost()) &&
                    uri.getPort() > 0 && path != null && path.matches("/resolve/[A-Za-z0-9_-]{20,64}");
        } catch (Exception ignored) { return false; }
    }

    private void inspectRequest(String address, Map<String, String> headers) {
        if (delivered.get()) return;
        String path = address.toLowerCase().split("\\?", 2)[0];
        if (path.endsWith(".vtt") || path.endsWith(".srt") || path.endsWith(".ass")) {
            if (subtitleUrl.isEmpty()) {
                subtitleUrl = address;
                subtitleHeaders = headers;
            }
            return;
        }
        if (looksLikeVideo(address, headers)) {
            mediaUrl = address;
            mediaHeaders = headers;
            if (deliveryScheduled.compareAndSet(false, true)) {
                webView.postDelayed(() -> deliver(mediaUrl, mediaHeaders, subtitleUrl, subtitleHeaders), 2500);
            }
        }
    }

    private boolean looksLikeVideo(String address, Map<String, String> headers) {
        String lower = address.toLowerCase();
        String path = lower.split("\\?", 2)[0];
        if (path.endsWith(".m3u8") || path.endsWith(".mp4") || path.endsWith(".m4v") || path.endsWith(".mpd")) return true;
        String range = headers == null ? null : headers.get("Range");
        return range != null && !path.matches(".*\\.(jpg|jpeg|png|webp|gif|css|js|vtt|srt|ts|m4s)$");
    }

    private void deliver(String address, Map<String, String> headers, String subtitle, Map<String, String> subHeaders) {
        if (address == null || address.isEmpty()) return;
        if (!delivered.compareAndSet(false, true)) return;
        new Thread(() -> {
            HttpURLConnection connection = null;
            try {
                JSONObject payload = new JSONObject();
                payload.put("url", address);
                payload.put("subtitle", subtitle == null ? "" : subtitle);
                JSONObject requestHeaders = new JSONObject();
                if (headers != null) {
                    for (Map.Entry<String, String> entry : headers.entrySet()) {
                        String key = entry.getKey();
                        if (key.equalsIgnoreCase("user-agent") || key.equalsIgnoreCase("referer") || key.equalsIgnoreCase("origin"))
                            requestHeaders.put(key, entry.getValue());
                    }
                }
                if (!requestHeaders.has("User-Agent")) requestHeaders.put("User-Agent", userAgent);
                if (!requestHeaders.has("Referer")) requestHeaders.put("Referer", referer);
                String cookie = CookieManager.getInstance().getCookie(address);
                if (cookie != null && !cookie.isEmpty()) requestHeaders.put("Cookie", cookie);
                payload.put("headers", requestHeaders);
                JSONObject subtitleRequestHeaders = new JSONObject();
                if (subHeaders != null) {
                    for (Map.Entry<String, String> entry : subHeaders.entrySet()) {
                        String key = entry.getKey();
                        if (key.equalsIgnoreCase("user-agent") || key.equalsIgnoreCase("referer") || key.equalsIgnoreCase("origin"))
                            subtitleRequestHeaders.put(key, entry.getValue());
                    }
                }
                if (subtitle != null && !subtitle.isEmpty()) {
                    if (!subtitleRequestHeaders.has("User-Agent")) subtitleRequestHeaders.put("User-Agent", userAgent);
                    if (!subtitleRequestHeaders.has("Referer")) subtitleRequestHeaders.put("Referer", referer);
                    String subtitleCookie = CookieManager.getInstance().getCookie(subtitle);
                    if (subtitleCookie != null && !subtitleCookie.isEmpty()) subtitleRequestHeaders.put("Cookie", subtitleCookie);
                }
                payload.put("subtitle_headers", subtitleRequestHeaders);
                connection = (HttpURLConnection) new URL(callback).openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                byte[] body = payload.toString().getBytes("UTF-8");
                connection.setFixedLengthStreamingMode(body.length);
                try (OutputStream output = connection.getOutputStream()) { output.write(body); }
                int status = connection.getResponseCode();
                if (status >= 200 && status < 300) runOnUiThread(this::finish);
            } catch (Exception ignored) {
                delivered.set(false);
            } finally {
                if (connection != null) connection.disconnect();
            }
        }, "myvidplay-kodi-callback").start();
    }

    @Override public boolean dispatchKeyEvent(KeyEvent event) {
        int keyCode = event.getKeyCode();
        if (event.getAction() == KeyEvent.ACTION_DOWN &&
                (keyCode == KeyEvent.KEYCODE_DPAD_CENTER || keyCode == KeyEvent.KEYCODE_ENTER ||
                keyCode == KeyEvent.KEYCODE_NUMPAD_ENTER) && event.getRepeatCount() == 0 && webView != null) {
            tapWebViewCenter();
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    private void tapWebViewCenter() {
        float x = webView.getWidth() / 2f;
        float y = webView.getHeight() / 2f;
        long downTime = SystemClock.uptimeMillis();
        MotionEvent down = MotionEvent.obtain(downTime, downTime, MotionEvent.ACTION_DOWN, x, y, 0);
        webView.dispatchTouchEvent(down);
        down.recycle();
        long upTime = SystemClock.uptimeMillis();
        MotionEvent up = MotionEvent.obtain(downTime, upTime, MotionEvent.ACTION_UP, x, y, 0);
        webView.dispatchTouchEvent(up);
        up.recycle();
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
