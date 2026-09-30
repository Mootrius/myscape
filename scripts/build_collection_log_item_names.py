"""One-off script: build app/data/collection_log_item_names.json, an
{item id: item name} index covering exactly the item ids in
app/data/collection_log_schema.json (see CollectionLogSchemaExporter
in the Mootrius/myscape-plugin repo for how that schema itself was
built) -- the collection log UI needs a real name to show under each
item's icon, including for items a player hasn't obtained yet (icons
alone come for free from RuneLite's own static CDN by numeric id, the
same way app/purchase_goals.py's item_icon_url already builds every
other item icon in this app -- see that function's own comment -- but
there's no id-keyed name source already wired up for this).

app/item_ids.py's own snapshot (app/data/item_ids.json, name -> ids,
built by scripts/fetch_item_ids.py from the wiki's Bucket data
extension) is a NAME-keyed index, built for the opposite lookup
direction (matching an untradeable item's name to a real id -- see
that module's own docstring). Inverting it here resolves 1704 of the
collection log's 1721 unique item ids outright.

The 17 that don't resolve are every one that CollectionLogSchemaExporter
itself remaps away from its "page struct" id to a different "item
widget" id (see that class's own PAGE_STRUCT_ITEM_ID_TO_WIDGET_ITEM_ID,
credited there to evansloan/collection-log) plus a handful of older or
more obscure drops the wiki's Bucket table simply doesn't carry under
these specific final ids -- ITEM_NAME_OVERRIDES below covers each by
hand, looked up directly by numeric id (not by trusting any comment
text in either that remap table or evansloan's own source, which turns
out to have at least one actual mistake -- see the id 25618 comment
below) against osrsbox-db's own id-keyed item-complete.json snapshot
(github.com/osrsbox/osrsbox-db, id-indexed dump of the whole item
cache), the same kind of authoritative id-keyed source
scripts/fetch_item_ids.py already leans on elsewhere in this repo.

Run with: python scripts/build_collection_log_item_names.py (from the
repo root, after app/data/collection_log_schema.json and
app/data/item_ids.json already exist). Re-run this by hand (not on a
schedule) whenever the collection log schema itself is re-exported --
same "only changes when Jagex adds content" cadence as every other
static snapshot in this repo.
"""
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ITEM_IDS_PATH = REPO_ROOT / "app" / "data" / "item_ids.json"
SCHEMA_PATH = REPO_ROOT / "app" / "data" / "collection_log_schema.json"
OUTPUT_PATH = REPO_ROOT / "app" / "data" / "collection_log_item_names.json"

# Every item id CollectionLogSchemaExporter's own remap sends collection
# log data through (the OLD "page struct" id -> the NEW "item widget"
# id -- see that class's PAGE_STRUCT_ITEM_ID_TO_WIDGET_ITEM_ID) never
# appears under its NEW id in the wiki's Bucket infobox table, which is
# what app/data/item_ids.json is built from -- so all twelve need a
# name looked up by hand here. Confirmed against osrsbox-db's
# items-complete.json by the FINAL id itself, not against either
# remap table's own comment text: evansloan's own upstream comment
# labels id 25618 "Red satchel", but osrsbox-db (and the in-game item
# examine text) says "Plain satchel" -- the comment is simply wrong,
# which is exactly why this doesn't just copy those comments over.
#
# The remaining five (6926, 24868-24871) aren't part of that remap at
# all -- ordinary collection log item ids the Bucket table just doesn't
# carry a page for under these ids, resolved the same way.
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
        # info["name"] is the item's real display casing (e.g.
        # "Tanzanite fang") -- the dict KEY (`key` here) is a
        # lowercased version of that same name, used elsewhere in this
        # repo purely for case-insensitive lookup (see app/item_ids.py's
        # own docstring), and would silently lowercase every name in
        # this output if used here instead.
        name = info["name"]
        for item_id in info["ids"]:
            # A handful of ids (puppy colour variants, none of them
            # collection log items) are listed under more than one
            # name in this snapshot -- first one wins, arbitrarily;
            # see this script's own verification step below, which
            # would catch it if that ever mattered for an id this
            # actually needs.
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

    # Keys become JSON object keys, which are always strings -- read
    # back with int(key) on the server side (see app/possessions.py or
    # wherever this actually gets consumed).
    output = {str(item_id): resolved[item_id] for item_id in sorted(resolved)}
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
