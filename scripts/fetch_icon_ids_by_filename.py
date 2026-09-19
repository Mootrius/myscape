"""One-off script: fetch the OSRS Wiki's Bucket:Infobox_item table in
full and build a {wiki image filename (lowercase, no "File:" prefix):
[item_id, ...]} JSON index to app/data/icon_ids_by_filename.json for
the app to bundle/ship.

This exists to fix a specific gap scripts/fetch_item_ids.py's own
item_ids.json snapshot can't close: that snapshot is keyed by item
NAME, and merges every cosmetic recolor of one item page under a
single shared name -- because the wiki's infobox_item rows genuinely
share one item_name across every recolor too (every Crystal helm
colour is item_name "Crystal helm", whether it's the original or the
Ithell-recoloured version). So a name like "Crystal helm (Ithell)" --
which app/data/recipes.json stores as its own exact combination-recipe
name, complete with its own distinct icon filename -- has no way to
resolve to its own specific real id through item_ids.json at all; the
best that snapshot can do is hand back the WHOLE merged id list for
"crystal helm", with no way to tell which of those ten ids is
specifically the Ithell one.

Those same infobox_item rows DO each carry their own distinct 'image'
field, though, even while sharing one item_name -- e.g. one row for
"Crystal helm" is {item_id: 27717, image: "File:Crystal helm
(Ithell).png"}, a different row for the same item_name is {item_id:
27753, image: "File:Crystal helm (Cadarn).png"}, and so on. That
per-row image filename is exactly the same string
app/data/recipes.json already stores as that colour variant's own
"icon" field (see scripts/fetch_recipes.py) -- so keying THIS
snapshot by filename instead of name closes the gap: given "Crystal
helm (Ithell)"'s recipe icon "Crystal helm (Ithell).png",
find_item_id_by_icon_filename (app/item_ids.py) looks it up here and
gets back 27717 directly, letting _untradeable_item_icon
(app/purchase_goals.py) reach RuneLite's CDN for it exactly like every
other real id in this app, instead of falling back to fetching the
wiki image itself.

A filename can list more than one id (an inventory/worn pair sharing
one look, the same "id1"/"id2" split item_ids.json's own merge already
handles for other items) -- both are kept, in the order the wiki
returns them, since by construction every id sharing one image
filename shares its icon too.

Run with: python scripts/fetch_icon_ids_by_filename.py (from the repo
root). Re-run this manually (not on a schedule) alongside
fetch_item_ids.py/fetch_recipes.py if a cosmetic-variant icon starts
coming up wrong or missing -- like those two, this data only changes
when new items are added to the game, so a bundled snapshot refreshed
by hand is plenty.
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
