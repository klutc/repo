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
    helper_apk = ROOT / "android" / "myvidplay-bridge" / "releases" / "MyVidPlayBridge-0.4.0.apk"
    if helper_apk.is_file():
        shutil.copy2(helper_apk, OUT / helper_apk.name)
    # Put the repository installer ZIP at the web root and use an Apache-style
    # directory index. Kodi's file browser can parse this listing, while it
    # does not treat a custom landing page as a browsable directory.
    repo_id = "repository.klutc"
    repo_xml = ET.parse(ROOT / "addons" / repo_id / "addon.xml").getroot()
    repo_version = repo_xml.attrib["version"]
    repo_zip_name = f"{repo_id}-{repo_version}.zip"
    shutil.copy2(OUT / repo_id / repo_zip_name, OUT / repo_zip_name)
    listing = [
        '<!doctype html><html><head><meta charset="utf-8"><title>Index of /repo/</title></head><body>',
        '<h1>Index of /repo/</h1><pre>',
        '<a href="../">Parent Directory</a>',
    ]
    for path in sorted(OUT.iterdir(), key=lambda item: item.name.lower()):
        if path.name == "index.html":
            continue
        name = path.name + ("/" if path.is_dir() else "")
        href = html.escape(name, quote=True)
        label = html.escape(name)
        listing.append(f'<a href="{href}">{label}</a>')
    listing.append('</pre></body></html>')
    (OUT / "index.html").write_text("\n".join(listing), encoding="utf-8")
    print(f"Built {len(links)} add-on(s) in {OUT}")

if __name__ == "__main__":
    build()
