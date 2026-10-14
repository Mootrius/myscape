"""One-off script: download the 48 Achievement Diary reward icons (12 areas x
4 tiers) from the wiki into app/static/img/diary-icons/, so Character Overview
can serve them as plain static files.

The file names are read from DIARY_AREA_TIER_ICON in
app/pages/assets/character_overview.js (the '/icon-cache/<name>' entries), so
this script and the page cannot drift apart. Each icon is saved as
<name with spaces as underscores and no apostrophes>.png, e.g.
Ardougne_cloak_1.png and Radas_blessing_1.png.

Fetches the wiki's Special:FilePath URL (the same one app/icon_cache.py uses)
one file at a time with a 1 second pause, skips files already on disk, and
checks each response is a real PNG. Safe to re-run.

Usage: python scripts/fetch_diary_icons.py (repo root). Re-run by hand, deleting
the old files first, if the wiki changes these icons.
"""
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS_PATH = ROOT / "app" / "pages" / "assets" / "character_overview.js"
OUTPUT_DIR = ROOT / "app" / "static" / "img" / "diary-icons"
ICON_PATH_BASE = "https://oldschool.runescape.wiki/w/Special:FilePath"
USER_AGENT = "myscape.io/1.0 (Character Overview; contact: chandler@myscape.io)"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PAUSE_SECONDS = 1.0


def icon_names() -> list:
    """Wiki file names (spaces, not underscores) from the page's icon table."""
    text = JS_PATH.read_text(encoding="utf-8")
    names = [urllib.parse.unquote(m) for m in re.findall(r"'/icon-cache/([^']+)'", text)]
    return list(dict.fromkeys(names))


def static_name(wiki_name: str) -> str:
    return wiki_name.replace(" ", "_").replace("'", "")


def fetch(wiki_name: str) -> bytes:
    url = ICON_PATH_BASE + "/" + urllib.parse.quote(wiki_name)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    if not data.startswith(PNG_MAGIC):
        raise ValueError(f"{wiki_name}: response is not a PNG ({len(data)} bytes)")
    return data


def main() -> None:
    names = icon_names()
    if len(names) != 48:
        raise SystemExit(f"expected 48 icon names in {JS_PATH.name}, found {len(names)}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    failed = []
    for i, name in enumerate(names, 1):
        target = OUTPUT_DIR / static_name(name)
        if target.exists():
            print(f"[{i}/48] have {target.name}")
            continue
        try:
            target.write_bytes(fetch(name))
            print(f"[{i}/48] saved {target.name}")
        except Exception as exc:  # noqa: BLE001 -- keep going, report at the end
            failed.append(name)
            print(f"[{i}/48] FAILED {name}: {exc}")
        time.sleep(PAUSE_SECONDS)
    if failed:
        raise SystemExit(f"{len(failed)} failed (re-run to retry): {failed}")
    print(f"done: {len(names)} icons in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
