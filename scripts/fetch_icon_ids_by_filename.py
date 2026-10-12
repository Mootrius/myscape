"""One-off script: fetch the wiki's Bucket:Infobox_item table and write
app/data/icon_ids_by_filename.json, a {image filename (lowercase, no "File:"
prefix): [item_id, ...]} index.
item_ids.json is keyed by item name, and the wiki shares one item_name across
cosmetic recolors (every Crystal helm colour is "Crystal helm"), so a recolor
such as "Crystal helm (Ithell)" cannot be resolved to its own id by name. Each
infobox row has a distinct `image`, which matches the "icon" field in
app/data/recipes.json (see scripts/fetch_recipes.py).
find_item_id_by_icon_filename (app/item_ids.py) uses this index so
_untradeable_item_icon (app/purchase_goals.py) can use RuneLite's CDN.
A filename may list several ids (e.g. inventory/worn pairs); all are kept in
wiki order.

Usage: python scripts/fetch_icon_ids_by_filename.py (repo root). Re-run by
hand with fetch_item_ids.py and fetch_recipes.py when a variant icon is wrong
or missing.
"""
import json
import pathlib
import time
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
PAGE_SIZE = 5000
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "icon_ids_by_filename.json"


def fetch_page(offset: int) -> list:
    query = (
        "bucket('infobox_item')"
        ".select('item_id','image')"
        f".limit({PAGE_SIZE}).offset({offset}).run()"
    )
    url = API + "?" + urllib.parse.urlencode({"action": "bucket", "format": "json", "query": query})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("bucket", [])


def _parse_ids(raw_ids) -> list:
    out = []
    for raw in raw_ids or []:
        try:
            out.append(int(raw))
        except (TypeError, ValueError):
            continue
    return out


def main():
    all_rows = []
    offset = 0
    while True:
        page = fetch_page(offset)
        all_rows.extend(page)
        print(f"fetched offset={offset} -> {len(page)} rows (total so far: {len(all_rows)})")
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.3)  # be polite to the wiki's API

    print(f"total infobox_item rows: {len(all_rows)}")

    index: dict = {}
    for row in all_rows:
        ids = _parse_ids(row.get("item_id"))
        if not ids:
            continue
        for raw_img in row.get("image") or []:
            name = str(raw_img)
            if name.lower().startswith("file:"):
                name = name[len("file:"):]
            if not name:
                continue
            key = name.lower()
            entry = index.setdefault(key, [])
            for i in ids:
                if i not in entry:
                    entry.append(i)

    print(f"final filename index entries: {len(index)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(index, f, separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
