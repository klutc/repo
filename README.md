# klutc Repo

Лично хранилище за Kodi 20 и по-нови версии.

## Публикуване

В Settings → Pages избери **Source: GitHub Actions**.
Workflow-ът Build and publish Kodi repository генерира каталога и ZIP пакетите при всеки push към main.
Ако първото изпълнение е неуспешно заради изключени Pages, отвори Actions и избери Re-run all jobs.

Адрес след успешното публикуване: https://klutc.github.io/repo/

## Инсталиране в Kodi

1. Изтегли https://klutc.github.io/repo/repository.klutc/repository.klutc-1.0.0.zip
2. Разреши Settings → System → Add-ons → Unknown sources.
3. Отвори Add-ons → Install from zip file и избери изтегления ZIP.
4. Отвори Install from repository → klutc Repo.

Хранилището засега съдържа само repository добавката, без видео добавки.

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
