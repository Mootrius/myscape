"""One-off script: fetch the OSRS Wiki's Bucket:Recipe table in full,
keep only entries shaped like a pure item combination -- no uses_skill
(e.g. Neitiznot faceguard = Helm of Neitiznot + Basilisk jaw -- see the
research notes in the conversation this was built from) and an output
quantity of exactly 1 (excludes batch-crafting recipes like "5 poisoned
arrows from a batch of unfinished ones", where the listed material
quantities are for the whole batch, not per unit, and dividing them out
isn't something this script tries to do) -- and write a compact
{outputNameLower: {"name":..., "icon":..., "materials": [...]}} JSON
index to app/data/recipes.json for the app to bundle/ship. Keyed by the
recipe's OUTPUT name rather than the wiki page name, since one page can
document several output variants (e.g. "Adamant arrow" documents both
plain and poisoned arrows as separate rows) and it's the output name a
player would actually search for.

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
    skipped_no_materials = 0
    skipped_no_output = 0
    skipped_batch_yield = 0
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
            skipped_no_materials += 1
            continue

        output = prod.get("output") or {}
        out_name = (output.get("name") or row.get("page_name") or "").strip()
        if not out_name:
            skipped_no_output += 1
            continue

        # Anything other than a 1-for-1 combination (e.g. "5 poisoned
        # arrows" from a batch of materials) isn't something we can
        # price correctly here -- the listed material quantities are
        # for the whole batch, not per output unit, and this script
        # doesn't attempt that division. This also naturally excludes
        # almost everything that isn't gear/equipment, which tends to
        # be exactly the kind of true 1:1 assembly this feature is for.
        try:
            out_qty = int(float(output.get("quantity") or 1))
        except (TypeError, ValueError):
            out_qty = 1
        if out_qty != 1:
            skipped_batch_yield += 1
            continue

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
        if not parsed_materials:
            continue

        key = out_name.lower()
        # First recipe seen for a given output name wins -- a handful of
        # items are documented with more than one way to obtain them
        # (e.g. via a quest reward as well as combining parts); the
        # first one the wiki returns is as good a pick as any, and
        # stability matters more than which one here.
        index.setdefault(key, {
            "name": out_name,
            "icon": output.get("image") or None,
            "materials": parsed_materials,
        })

    print(f"combination-shaped rows (no uses_skill): {combos}")
    print(f"  of which had no materials at all (skipped): {skipped_no_materials}")
    print(f"  of which had no output name (skipped): {skipped_no_output}")
    print(f"  of which were a batch yield, not 1:1 (skipped): {skipped_batch_yield}")
    print(f"  skilling recipes (excluded): {skilling}")
    print(f"final recipe index entries: {len(index)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(index, f, separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
