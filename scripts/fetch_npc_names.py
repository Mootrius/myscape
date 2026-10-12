"""One-off script: fetch the wiki's Bucket:Infobox_monster table and write
app/data/npc_names.json, a sorted ["NPC Name", ...] list for the Mindmaps KC
goal's NPC search.
Only fightable NPCs are kept (a missing or zero `combat_level` means
non-combat). Names are deduped, since one NPC appears once per variant (e.g.
Zulrah has three phases).

Usage: python scripts/fetch_npc_names.py (repo root). Re-run by hand when a
new NPC is missing from search.
"""
import json
import pathlib
import time
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Mindmaps; contact: chandler@myscape.io)"
PAGE_SIZE = 5000
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "npc_names.json"


def fetch_page(offset: int) -> list:
    query = (
        "bucket('infobox_monster')"
        ".select('name','combat_level')"
        f".limit({PAGE_SIZE}).offset({offset}).run()"
    )
    url = API + "?" + urllib.parse.urlencode({"action": "bucket", "format": "json", "query": query})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("bucket", [])


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

    print(f"total infobox_monster rows: {len(all_rows)}")

    names = set()
    for row in all_rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        combat = row.get("combat_level")
        try:
            combat = int(combat)
        except (TypeError, ValueError):
            combat = 0
        if combat <= 0:
            continue  # not killable -- a shopkeeper, quest NPC, etc.
        names.add(name)

    combined = sorted(names, key=lambda s: s.lower())
    print(f"final killable-NPC name count: {len(combined)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(combined, f, separators=(",", ":"))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
