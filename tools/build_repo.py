#!/usr/bin/env python3
"""Build a static Kodi repository from addon source folders."""
from pathlib import Path
import hashlib
import html
import re
import shutil
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"

def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    catalog = ET.Element("addons")
    links = []
    for source in sorted((ROOT / "addons").iterdir()):
        if not source.is_dir() or not (source / "addon.xml").is_file():
            continue
        addon = ET.parse(source / "addon.xml").getroot()
        addon_id, version = addon.attrib["id"], addon.attrib["version"]
        if addon.tag != "addon" or source.name != addon_id:
            raise ValueError(f"Invalid addon id or folder: {source}")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", addon_id) or not re.fullmatch(r"[A-Za-z0-9_.+-]+", version):
            raise ValueError("Invalid addon id or version")
        target = OUT / addon_id
        target.mkdir()
        archive = target / f"{addon_id}-{version}.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as package:
            for path in sorted(source.rglob("*")):
                if path.is_symlink():
                    raise ValueError(f"Symlinks are unsupported: {path}")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                    package.write(path, (Path(addon_id) / path.relative_to(source)).as_posix())
        for asset in addon.findall("./extension/assets/*"):
            if asset.text:
                relative = Path(asset.text)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Invalid asset path: {relative}")
                asset_source = source / relative
                if not asset_source.is_file():
                    raise ValueError(f"Missing asset: {asset_source}")
                (target / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset_source, target / relative)
        shutil.copy2(source / "addon.xml", target / "addon.xml")
        catalog.append(addon)
        href = archive.relative_to(OUT).as_posix()
        links.append(f'<li><a href="{html.escape(href)}">{html.escape(addon.attrib.get("name", addon_id))} {html.escape(version)}</a></li>')
        (target / "index.html").write_text(f'<!doctype html><meta charset="utf-8"><a href="{archive.name}">{archive.name}</a>', encoding="utf-8")
    if not links:
        raise ValueError("No add-ons found")
    ET.indent(catalog)
    payload = ET.tostring(catalog, encoding="utf-8", xml_declaration=True)
    (OUT / "addons.xml").write_bytes(payload)
    (OUT / "addons.xml.md5").write_text(hashlib.md5(payload).hexdigest(), encoding="ascii")
    (OUT / ".nojekyll").touch()
    (OUT / "index.html").write_text(
        '<!doctype html><html lang="bg"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>klutc Repo</title><style>body{font:18px system-ui;max-width:760px;margin:60px auto;padding:0 24px;line-height:1.6}a{color:#1769aa}</style>'
        '<h1>klutc Repo</h1><p>Изтегли repository.klutc ZIP и го инсталирай в Kodi чрез '
        'Add-ons → Install from zip file. След това отвори Install from repository → klutc Repo.</p>'
        '<p>Поддържа Kodi 20 и по-нови версии. Хранилището засега съдържа само repository добавката.</p>'
        '<ul>' + "".join(links) + '</ul><p><a href="https://github.com/klutc/repo">GitHub</a></p></html>',
        encoding="utf-8",
    )
    print(f"Built {len(links)} add-on(s) in {OUT}")

if __name__ == "__main__":
    build()
