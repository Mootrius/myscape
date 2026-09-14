"""One-off script: fetch the OSRS Wiki's Bucket:Recipe table in full,
keep only entries with no uses_skill (pure item-combination recipes,
e.g. Neitiznot faceguard = Helm of Neitiznot + Basilisk jaw -- see the
research notes in the conversation this was built from), and write a
compact {itemNameLower: [{"name":..., "quantity":...}, ...]} JSON index
to app/data/recipes.json for the app to bundle/ship.

Run with: python scripts/fetch_recipes.py (from the repo root).

Re-run this manually (not on a schedule) if new combination gear is
added to the game and the app doesn't recognize it yet -- combination
recipes essentially never change, so this is a cached snapshot, not a
live query.
"""
import json
import pathlib
import time
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Purchase Goals; contact: chandler@myscape.io)"
PAGE_SIZE = 5000
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "recipes.json"


def fetch_page(offset: int) -> list:
    query = (
        "bucket('recipe')"
        ".select('page_name','uses_skill','production_json')"
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

    print(f"total recipe rows: {len(all_rows)}")

    combos = 0
    skilling = 0
    no_output = 0
    index = {}
    for row in all_rows:
        if row.get("uses_skill"):
            skilling += 1
            continue  # skilling recipe, not a pure item combination
        combos += 1
        try:
            prod = json.loads(row.get("production_json") or "{}")
        except json.JSONDecodeError:
            continue
        materials = prod.get("materials") or []
        if not materials:
            no_output += 1
            continue
        name = row.get("page_name") or (prod.get("output") or {}).get("name")
        if not name:
            continue
        key = name.strip().lower()
        parsed_materials = []
        for m in materials:
            mat_name = (m.get("name") or "").strip()
            if not mat_name:
                continue
            try:
                qty = int(float(m.get("quantity") or 1))
            except (TypeError, ValueError):
                qty = 1
            parsed_materials.append({"name": mat_name, "quantity": max(qty, 1)})
        if parsed_materials:
            index[key] = parsed_materials

    print(f"combination-shaped rows (no uses_skill): {combos}")
    print(f"  of which had no materials/output (skipped): {no_output}")
    print(f"  skilling recipes (excluded): {skilling}")
    print(f"final recipe index entries: {len(index)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(index, f, separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
