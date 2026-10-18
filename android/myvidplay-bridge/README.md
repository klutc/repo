# MyVidPlay Bridge for Kodi

Android WebView companion prototype for Kodi video add-ons. Kodi launches an allowed provider page in WebView so the user can complete visible browser checks and press Play. The helper observes direct `.mp4`, `.m4v`, and `.m3u8` requests and returns the URL and relevant cookies to the add-on's loopback callback.

This is a prototype. MyVidPlay/DoodStream can change its player, require manual verification, or bind media URLs to browser cookies. In those cases the helper may not be able to hand a playable URL back to Kodi.

Build with Android SDK platform 30, Build Tools 30.0.2, Android Gradle Plugin 4.2.2, Gradle 6.9.4, and JDK 11:

```sh
gradle assembleDebug
```

Install `releases/MyVidPlayBridge-0.6.0.apk` on Android TV or phone. Package: `org.klutc.myvidplaybridge`. Filmi2K, Filmi9, FilmiZip and ZenoPlay use it for MyVidPlay, Upbolt, StreamTape, EMBE, CONT and FMoon/Byse links on Android. FilmiZip opens its own player page in the helper to preserve the embedding origin. VidSrcEmbed opens it only after the native resolver reports a Cloudflare/Turnstile challenge. Complete any visible browser check; on Android TV press OK to tap the center of the WebView player, and return from ad pages if they appear. Kodi receives the media URL and a subtitle URL when the page exposes them. Install this APK over earlier versions. It targets Android SDK 24.

This prototype only captures direct media URLs exposed to WebView. It cannot return `blob:` playback, DRM streams, or URLs that are cryptographically tied to the browser process. An Android TV device is required to verify the provider's current player behavior end to end.
