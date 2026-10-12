"""One-off script: build app/data/collection_log_item_names.json, an {item id:
item name} index covering the item ids in app/data/collection_log_schema.json.
The collection log UI needs a name under each icon, including for items not
yet obtained. Icons come from RuneLite's CDN by numeric id; no id-keyed name
source existed.
Resolved by inverting app/data/item_ids.json (name -> ids, from
scripts/fetch_item_ids.py). The 17 ids it cannot resolve are named by hand in
ITEM_NAME_OVERRIDES, taken from osrsbox-db's id-keyed items-complete.json.

Usage: python scripts/build_collection_log_item_names.py (repo root; needs the
schema and item_ids.json). Re-run by hand when the collection log schema is
re-exported.
"""
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEM_IDS_PATH = REPO_ROOT / "app" / "data" / "item_ids.json"
SCHEMA_PATH = REPO_ROOT / "app" / "data" / "collection_log_schema.json"
OUTPUT_PATH = REPO_ROOT / "app" / "data" / "collection_log_item_names.json"

# Ids that CollectionLogSchemaExporter remaps from a "page struct" id to an
# "item widget" id (PAGE_STRUCT_ITEM_ID_TO_WIDGET_ITEM_ID) are missing under the
# new id in the Bucket table, so they are named by hand. Names are checked
# against osrsbox-db by final id, not copied from upstream comments (evansloan's
# comment mislabels 25618 as "Red satchel"; it is "Plain satchel").
# The remaining five (6926, 24868-24871) are ordinary ids the Bucket table
# lacks.
ITEM_NAME_OVERRIDES = {
    6926: "Bones to peaches",
    24868: "Golden armadyl special attack",
    24869: "Golden bandos special attack",
    24870: "Golden saradomin special attack",
    24871: "Golden zamorak special attack",
    25617: "Tea flask",
    25618: "Plain satchel",
    25619: "Green satchel",
    25620: "Red satchel",
    25621: "Black satchel",
    25622: "Gold satchel",
    25623: "Rune satchel",
    25624: "Unsired",
    25627: "Coal bag",
    25628: "Gem bag",
    25629: "Plank sack",
    25630: "Flamtaer bag",
}


def collection_log_item_ids() -> set:
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    ids = set()
    for tab in schema["tabs"]:
        for page in tab["pages"]:
            ids.update(page["itemIds"])
    return ids


def build_id_to_name_from_item_ids_json() -> dict:
    with open(ITEM_IDS_PATH) as f:
        name_map = json.load(f)
    id_to_name = {}
    for key, info in name_map.items():
        # info["name"] has the real display casing; `key` is lowercased for
        # lookups and must not be used here.
        name = info["name"]
        for item_id in info["ids"]:
            # A few non-collection-log ids (puppy colour variants) appear under
            # several names; the first wins.
            id_to_name.setdefault(item_id, name)
    return id_to_name


def main():
    needed_ids = collection_log_item_ids()
    print(f"collection log schema needs names for {len(needed_ids)} unique item ids")

    id_to_name = build_id_to_name_from_item_ids_json()
    resolved = {}
    missing = []
    for item_id in needed_ids:
        name = ITEM_NAME_OVERRIDES.get(item_id) or id_to_name.get(item_id)
        if name is None:
            missing.append(item_id)
        else:
            resolved[item_id] = name

    if missing:
        raise RuntimeError(
            f"{len(missing)} item ids have no resolvable name, add them to "
            f"ITEM_NAME_OVERRIDES above: {sorted(missing)}"
        )

    print(f"resolved all {len(resolved)} names "
          f"({len(needed_ids) - len(ITEM_NAME_OVERRIDES.keys() & needed_ids)} from item_ids.json, "
          f"{len(ITEM_NAME_OVERRIDES.keys() & needed_ids)} from ITEM_NAME_OVERRIDES)")

    # JSON object keys are strings; consumers read them back with int(key).
    output = {str(item_id): resolved[item_id] for item_id in sorted(resolved)}
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
