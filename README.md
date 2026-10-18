# klutc Repo

Лично хранилище за Kodi 20 и по-нови версии.

## Публикуване

В Settings → Pages избери **Source: GitHub Actions**.
Workflow-ът Build and publish Kodi repository генерира каталога и ZIP пакетите при всеки push към main.
Ако първото изпълнение е неуспешно заради изключени Pages, отвори Actions и избери Re-run all jobs.

Адрес след успешно публикуване: https://klutc.github.io/repo/

## Инсталиране в Kodi

1. Изтегли https://klutc.github.io/repo/repository.klutc/repository.klutc-1.0.0.zip
2. Разреши Settings → System → Add-ons → Unknown sources.
3. Отвори Add-ons → Install from zip file и избери изтегления ZIP.
4. Отвори Install from repository → klutc Repo.

Хранилището съдържа:

| Добавка | Версия |
| --- | --- |
| Filmi9 by Klutc | 1.2.14 |
| FilmiZip by Klutc | 1.3.13 |
| ZenoPlay by Klutc | 1.0.16 |
| Klutc Movies (общ вход и търсене) | 1.2.4 |
| Find Stream URL (зависимост) | 2026.10.14.02 |
| ElementumOrg repository | 0.0.7 |

Видео добавките се намират в **Install from repository → klutc Repo → Video add-ons**. Klutc Movies предлага отделно **Search Movies** и **Search Series** във FilmiZip, Filmi9 и ZenoPlay, както и отделен достъп до каталога на всеки сайт. Избраните заглавия се отварят в оригиналната добавка, така че функциите и настройките ѝ се запазват. Резултатите са обозначени с името на сайта; наличните следващи страници могат да се отворят от общия списък. За заглавия от ZenoPlay с БГ Аудио се показва и маркер [BG]. За да добавиш Elementum към Kodi, инсталирай **ElementumOrg repository** от **Install from repository → klutc Repo → Add-on repositories**, след което намери Elementum в ElementumOrg repository.
Find Stream URL се инсталира като зависимост от това хранилище; Requests, Beautiful Soup, Six и Kodi Six се получават от официалното хранилище на Kodi.

На Android TV Filmi9 използва нативен обработчик за Vidsrcme; Vsembed, VOE, VIDM, PlayM и FMoon/Byse също имат директни обработчици без Chrome. При епизодите Kodi получава оригиналното заглавие на сериала, IMDb ID, сезона и епизода, така че добавките за външни субтитри могат да търсят при поискване. Видео добавките зареждат субтитрите, предоставени от избрания видеоизточник, без автоматично да ги заменят с резултат от OpenSubtitles. При FMoon/Byse първата автоматична проверка може да отнеме няколко минути. VOE предпочита MP4 на Android (променя се от настройките). Upbolt засега е блокиран от Cloudflare. Подробности и ограничения има в ANDROID.txt на всяка видео добавка.

При отваряне на филм бутонът „Пусни филма“ стартира първия източник; ако не работи, списъкът с източници остава достъпен. Иконите и прозорецът за информация са включени в пакетите; прозорецът показва година, жанр, държава, актьорски състав и резюме, когато източникът предоставя тези данни. Автоматичният информационен панел след 20 секунди използва отделна промяна на Confluence и не се инсталира чрез тези ZIP пакети. За ZenoPlay добави `resources/confluence-media-info.xml` към `MyVideoNav.xml` на Confluence, ако искаш този панел и за новата добавка.

Съставът се взема от FilmiZip и Filmi9. За ZenoPlay актьорският състав се зарежда от TMDb по избор: включи показването и въведи личния си API Read Access Token в настройките на добавката. В описанието на ZenoPlay е посочен TMDb като източник на актьорските данни.

## Добавяне на добавки

Постави кода на добавката в addons/<addon.id>/, с addon.xml в корена на тази папка.
Името на папката трябва да съвпада с id в addon.xml.
При обновяване увеличавай version в addon.xml.
Качи промяната в main; GitHub Actions ще генерира ZIP пакетите, addons.xml и addons.xml.md5.

Локална проверка:

```bash
python3 tools/build_repo.py
```

Готовите файлове се генерират в _site/.
