# MyVidPlay Bridge for Kodi

Small Android WebView companion prototype for Filmi2K. Kodi launches the page in an Android WebView so the user can complete any browser checks and press Play. The helper observes direct `.mp4`, `.m4v`, and `.m3u8` requests and returns the URL and relevant cookies to the add-on's loopback callback.

This is a prototype. MyVidPlay/DoodStream can change its player, require manual verification, or bind media URLs to browser cookies. In those cases the helper may not be able to hand a playable URL back to Kodi.

Build with Android SDK platform 30, Build Tools 30.0.2, Android Gradle Plugin 4.2.2, Gradle 6.9.4, and JDK 11:

```sh
gradle assembleDebug
```

Install `releases/MyVidPlayBridge-0.1.0.apk` on the Android TV. Package: `org.klutc.myvidplaybridge`. Filmi2K 1.0.4 will launch it automatically for MyVidPlay/PlayMogo links on Android. Install the helper APK before updating the Kodi add-on.

This prototype only captures direct media URLs exposed to WebView. It cannot return `blob:` playback, DRM streams, or URLs that are cryptographically tied to the browser process. An Android TV device is required to verify the provider's current player behavior end to end.
