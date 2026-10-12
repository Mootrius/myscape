"""One-off script: fetch the wiki's Bucket:Recipe table and write
app/data/recipes.json, a {outputNameLower: {"name", "icon", "materials":
[...]}} index.
Only pure item combinations are kept (e.g. Neitiznot faceguard = Helm of
Neitiznot + Basilisk jaw): no uses_skill, or the exact pair in
ALSO_ALLOWED_SKILL_SIGNATURE, and an output quantity of exactly 1 (batch
recipes list whole-batch quantities, which this script does not divide). Keyed
by output name because one page can document several outputs ("Adamant arrow"
covers plain and poisoned arrows).
The snapshot records one level only; app/recipes.py (expand_recipe_components)
resolves nested combinations at lookup time.

Usage: python scripts/fetch_recipes.py (repo root). Re-run by hand when new
combination gear is not recognized.
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

# A few real combination recipes (Eternal/Pegasian/Primordial boots, the Avernic
# treads chain, Ecumenical key) carry the skill pair ["Magic", "Runecraft"] from
# a small ritual XP reward. That exact pair, in that order, appears on those 11
# items only, so allowing it pulls in no real skilling recipes. Re-verify if the
# wiki data is reorganized.
ALSO_ALLOWED_SKILL_SIGNATURE = ["Magic", "Runecraft"]

# The three Doom of Mokhaiotl demonbane weapons (Emberlight, Scorching bow,
# Purging staff) are 1:1 combinations, but each has its own incidental skill tag
# (Smithing, Fletching, Crafting+Smithing) that cannot be allowed generally.
# They are allowed by exact page name instead.
ALSO_ALLOWED_PAGE_NAMES = {"Emberlight", "Scorching bow", "Purging staff"}

# Emberlight's wiki materials include an Arclight, which is untradeable, has no
# recipe, and is consumed as a prerequisite the player already owns. Tracking it
# would make the combo look incomplete for non-monetary reasons, so Emberlight
# is priced as its Tormented synapse alone. Scorching bow and Purging staff have
# only tradeable extras and are priced normally.
MANUAL_MATERIAL_OVERRIDES = {
    "emberlight": [{"name": "Tormented synapse", "quantity": 1}],
}


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
        uses_skill = row.get("uses_skill") or []
        page_name = (row.get("page_name") or "").strip()
        if uses_skill and uses_skill != ALSO_ALLOWED_SKILL_SIGNATURE and page_name not in ALSO_ALLOWED_PAGE_NAMES:
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

        # Only 1-for-1 combinations are kept: batch recipes list whole-batch
        # quantities and are not divided here. This also mostly limits results
        # to gear.
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
        # MANUAL_MATERIAL_OVERRIDES (currently Emberlight) take precedence over
        # the wiki's materials list.
        parsed_materials = MANUAL_MATERIAL_OVERRIDES.get(key, parsed_materials)
        # The first recipe seen for an output name wins (some items have several
        # ways to obtain them).
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
