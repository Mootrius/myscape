"""One-off script: fetch the OSRS Wiki's Bucket:Infobox_item table in
full and build a
{itemNameLower: {"name": str, "ids": [int, ...], "icon": str|None}}
JSON index to app/data/item_ids.json for the app to bundle/ship.

This exists to fix a specific class of bug: an untradeable item (no
Grand Exchange listing, so no real item id in the wiki's price-mapping
API) can currently only be matched against what a player already owns
by comparing item NAME TEXT -- see _take_owned in
app/purchase_goals.py. That's fragile: the RuneLite plugin reports
whatever the game client itself calls an item, and if that text
differs from what a gear slot/recipe names it in any way (an
apostrophe encoded differently, incidental whitespace, etc.) the match
silently fails and the item looks unowned even when it isn't.

Every item in the game -- tradeable or not -- has a small number of
real, permanent, globally-unique numeric ids (the SAME ids RuneLite
itself uses), and the wiki's item infobox data records them for every
item page. Matching by id instead of by name text sidesteps the whole
class of text-formatting mismatches, since an id either is or isn't
the same physical item -- there's no such thing as "close enough" or
"differently capitalized" for a numeric id. Name matching remains as a
fallback in app/purchase_goals.py for anything this snapshot doesn't
cover (e.g. an item added to the game after this was last generated).

One item page can list more than one id (quest-reward variants,
Last Man Standing-only versions, etc.) -- all of them are kept, since a
player owning the item under any of its real ids should count as
owning it. One item page can also appear more than once with different
`image` values across those variants; whichever version the wiki marks
`default_version` (or the first one seen, if none is marked) is used
for the icon, since that's the one a player would recognize.

`name` keeps the original, properly-cased spelling the wiki uses (the
dict key itself is lowercased, for case-insensitive lookup) -- needed
so a search suggestion built from this snapshot (see
search_item_names in app/item_ids.py, the final fallback tier in
app/purchase_goals.py's search_items once neither the GE mapping nor a
known recipe matches) can display "Zulrah's scales" rather than
"zulrah's scales".

Run with: python scripts/fetch_item_ids.py (from the repo root).

Re-run this manually (not on a schedule) if items keep coming up
without an icon or without being recognized as owned -- like recipes,
this data only changes when new items are added to the game, so a
bundled snapshot refreshed by hand is plenty.
"""
import json
import pathlib
import time
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
PAGE_SIZE = 5000
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "item_ids.json"


def fetch_page(offset: int) -> list:
    query = (
        "bucket('infobox_item')"
        ".select('item_name','item_id','image','default_version')"
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


def _parse_icon(raw_images) -> str:
    """image is a repeated PAGE field shaped like "File:Name.png" --
    strip the File: namespace prefix to get the plain filename
    item_icon_url (see app/purchase_goals.py) expects."""
    for raw in raw_images or []:
        name = str(raw)
        if name.lower().startswith("file:"):
            name = name[len("file:"):]
        if name:
            return name
    return None


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

    index = {}
    for row in all_rows:
        name = (row.get("item_name") or "").strip()
        if not name:
            continue
        ids = _parse_ids(row.get("item_id"))
        icon = _parse_icon(row.get("image"))
        is_default = bool(row.get("default_version"))

        key = name.lower()
        entry = index.get(key)
        if entry is None:
            index[key] = {"name": name, "ids": list(ids), "icon": icon, "_has_default_icon": is_default and bool(icon)}
            continue

        # Merge in this row's ids (a page can list more than one row,
        # one per "version" of the item -- e.g. a quest-reward variant
        # alongside the standard one) without duplicating any.
        for i in ids:
            if i not in entry["ids"]:
                entry["ids"].append(i)
        # Prefer the default version's icon; otherwise keep whatever
        # was already found rather than overwrite it with a variant's.
        if icon and (not entry["icon"] or (is_default and not entry["_has_default_icon"])):
            entry["icon"] = icon
            entry["_has_default_icon"] = entry["_has_default_icon"] or is_default

    # Drop the bookkeeping-only field and anything with no real ids at
    # all (nothing useful to match or display).
    final_index = {}
    for key, entry in index.items():
        if not entry["ids"]:
            continue
        final_index[key] = {"name": entry["name"], "ids": sorted(entry["ids"]), "icon": entry["icon"]}

    print(f"final item index entries: {len(final_index)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(final_index, f, separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
