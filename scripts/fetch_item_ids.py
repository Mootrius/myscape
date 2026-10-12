"""One-off script: fetch the wiki's Bucket:Infobox_item table and write
app/data/item_ids.json, a {itemNameLower: {"name": str, "ids": [int, ...],
"icon": str|None}} index.
Untradeable items have no GE id, so owned items were matched by name text
(_take_owned in app/purchase_goals.py), which fails on encoding or whitespace
differences. Matching on the numeric ids (the same ones RuneLite uses) avoids
that; name matching stays as the fallback for items missing from this
snapshot.
An item page may list several ids (quest-reward variants, Last Man Standing
versions); all are kept. The icon comes from the version marked
`default_version`, else the first seen.
`name` keeps the wiki's casing (the key is lowercased) so search_item_names
(app/item_ids.py) can show "Zulrah's scales".

Usage: python scripts/fetch_item_ids.py (repo root). Re-run by hand when items
lack icons or are not recognized as owned.
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
    """image is a repeated PAGE field like "File:Name.png"; strip the File:
    prefix to get the filename item_icon_url (app/purchase_goals.py) expects.
    """
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

        # Merge this row's ids (one row per item version) without duplicates.
        for i in ids:
            if i not in entry["ids"]:
                entry["ids"].append(i)
        # Prefer the default version's icon; otherwise keep the one already
        # found.
        if icon and (not entry["icon"] or (is_default and not entry["_has_default_icon"])):
            entry["icon"] = icon
            entry["_has_default_icon"] = entry["_has_default_icon"] or is_default

    # Drop the bookkeeping field and entries with no ids.
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
