"""One-off script: port RuneLite's own "Item Prices" plugin data -- the
table that lets the OSRS client show a GE-value tooltip on an
untradeable item (e.g. hovering a Crystal helm shows "GE: 5.47M gp",
the cost of the Crystal armour seed it takes to make one) -- into a
{untradeableItemId: [{"itemId": tradeableItemId, "qty": int}, ...]}
JSON index at app/data/untradeable_mapping.json for both Possessions
Monitoring (app/possessions.py) and Purchase Goals
(app/purchase_goals.py) to derive a value for an item that has no GE
listing of its own.

Where this comes from, and why porting it (rather than re-deriving it
some other way) is the right call: the OSRS Wiki's own price-mapping
API -- the same one get_mapping()/get_latest_prices() in
app/purchase_goals.py already depend on for every tradeable item's
name/icon/price -- simply does not carry this data at all (confirmed
directly: Crystal helm and friends are absent from that mapping
entirely, and the wiki's own item infobox for one shows only its
static store "Value", not a GE-derived one). RuneLite maintains the
real, currently-used version of this table as
net.runelite.client.game.ItemMapping (BSD 2-Clause licensed -- see
https://github.com/runelite/runelite/blob/master/LICENSE), a Java enum
of ~320 entries each naming one or more untradeable item ids, the
tradeable item id whose live price stands in for them, and (for a
minority of entries -- Crystal helm/legs/body being the motivating
example) an explicit quantity multiplier. A companion table,
net.runelite.client.game.ItemVariationMapping (backed by
runelite-client's own item_variations.json resource), groups an item's
charge-state/recolour/degraded variants together, since ItemMapping
usually only lists one canonical id per entry and expects every
variant to inherit its price. This script reproduces both, plus
ItemManager.getItemPriceWithSource()'s recursive resolution (a handful
of entries point at a tradeable id that is *itself* another entry's
untradeable id -- e.g. the "Echo" Barrows pieces price as [the plain
piece] + [its ornament kit], and the plain piece is untradeable too),
flattening every chain down to real, directly GE-priceable leaf item
ids ahead of time so the app never needs to walk the chain itself.

Sources fetched (all from the runelite/runelite repo, `master` branch,
plain BSD-2-Clause-licensed source/resource files -- ported/adapted
under that license):
  - runelite-client/src/main/java/net/runelite/client/game/ItemMapping.java
  - runelite-client/src/main/resources/item_variations.json
  - runelite-api/src/main/java/net/runelite/api/gameval/ItemID.java
    (needed purely to resolve ItemMapping.java's symbolic `ItemID.FOO`
    references to the real numeric ids it never spells out itself --
    auto-generated, ~19,900 top-level constants. NOTE: this file also
    declares two NESTED classes, `ItemID.Cert` and `ItemID.Placeholder`,
    which redeclare many of the SAME symbol names for that item's noted
    and bank-placeholder ids -- e.g. `PRIF_ARMOUR_SEED` is 23956
    top-level but a different number again inside each nested class.
    ItemMapping.java only ever writes bare `ItemID.FOO` (never
    `ItemID.Cert.FOO`), so this script resolves symbols against the
    top-level class body ONLY, cut off before `Cert` begins -- reading
    the whole file into one flat name->id dict silently collapses all
    three onto whichever was seen last and resolves nearly every
    Prifddinas/crystal item to the wrong (placeholder) id.)

Verified end to end against a real in-game report: a Crystal helm
resolves here to 1x Crystal armour seed (item id 23956), which priced
at ~5.52M gp at the time this was last run -- matching a player's own
observed "GE: 5.47M gp" tooltip almost exactly (the gap is ordinary
day-to-day GE price drift, not a mapping error).

Like item_ids.json/recipes.json, this only needs re-running by hand
when RuneLite's own upstream table changes (Jagex adds a new
untradeable-with-a-GE-equivalent item, mainly) -- run with:
    python scripts/fetch_untradeable_mapping.py
from the repo root.
"""
import json
import pathlib
import re
import urllib.request
from collections import defaultdict

RAW_BASE = "https://raw.githubusercontent.com/runelite/runelite/master"
ITEM_MAPPING_URL = f"{RAW_BASE}/runelite-client/src/main/java/net/runelite/client/game/ItemMapping.java"
ITEM_VARIATIONS_URL = f"{RAW_BASE}/runelite-client/src/main/resources/item_variations.json"
ITEM_ID_URL = f"{RAW_BASE}/runelite-api/src/main/java/net/runelite/api/gameval/ItemID.java"
USER_AGENT = "myscape.io/1.0 (Purchase Goals / Storages Viewer; contact: chandler@myscape.io)"

OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "untradeable_mapping.json"

# A mapping chain is never expected to run more than 2-3 hops deep (the
# deepest real case -- the "Echo" Barrows pieces -- is 2) -- this is
# purely a safety cap against an unforeseen cycle in upstream data, so
# a bug there degrades to "a couple of items keep their intermediate,
# still-untradeable id as a leaf" rather than an infinite loop.
MAX_CHAIN_DEPTH = 6


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _fetch_json(url: str):
    return json.loads(_fetch_text(url))


def parse_item_id_symbols(item_id_src: str) -> dict:
    """symbol -> numeric id, top-level ItemID class body only -- see
    this script's own module docstring for why `Cert`/`Placeholder`
    must be excluded."""
    cert_idx = item_id_src.index("public static final class Cert")
    top_level = item_id_src[:cert_idx]
    pairs = re.findall(r"public static final int (\w+)\s*=\s*(-?\d+);", top_level)
    return {name: int(value) for name, value in pairs}


def parse_item_mapping_entries(mapping_src: str, sym_to_id: dict) -> list:
    """Each ItemMapping enum entry -> {"tradeable_id", "quantity",
    "include_variations", "untradeable_ids": [...]}, covering all three
    constructor shapes:
        ItemMapping(tradeableItem, int... untradableItems)
        ItemMapping(tradeableItem, long quantity, int... untradableItems)
        ItemMapping(tradeableItem, boolean includeVariations, long quantity, int... untradableItems)
    """
    enum_start = mapping_src.index("public enum ItemMapping")
    body_start = mapping_src.index("{", enum_start) + 1
    # The enum's entries end right where its own field declarations /
    # static{} initializer begins.
    static_idx = mapping_src.index("static\n\t{")
    body = mapping_src[body_start:static_idx]
    body = re.sub(r"//[^\n]*", "", body)  # strip line comments

    def resolve(token: str):
        m = re.match(r"ItemID\.(\w+)$", token)
        if not m:
            return None
        return sym_to_id.get(m.group(1))

    entries = []
    for m in re.finditer(r"(ITEM_\w+)\(([^()]*)\)\s*,?", body):
        name = m.group(1)
        args = [a.strip() for a in m.group(2).split(",") if a.strip()]
        if not args:
            continue

        tradeable_id = resolve(args[0])
        rest = args[1:]

        include_variations = False
        quantity = 1
        if rest and rest[0] == "true":
            include_variations = True
            quantity = int(rest[1].rstrip("L"))
            rest = rest[2:]
        elif rest and re.match(r"^-?\d+L$", rest[0]):
            quantity = int(rest[0].rstrip("L"))
            rest = rest[1:]

        untradeable_ids = [rid for rid in (resolve(tok) for tok in rest) if rid is not None]
        if tradeable_id is None or not untradeable_ids:
            continue  # a symbol this script's ItemID snapshot doesn't know -- skip rather than guess

        entries.append({
            "name": name,
            "tradeable_id": tradeable_id,
            "quantity": quantity,
            "include_variations": include_variations,
            "untradeable_ids": untradeable_ids,
        })
    return entries


def build_variation_index(variation_groups: dict):
    """Reproduces ItemVariationMapping: id -> its group's base id (the
    first id listed for that group), and base id -> the full group
    (including the base itself), mirroring
    MAPPINGS/INVERTED_MAPPINGS there."""
    id_to_base = {}
    base_to_group = {}
    for ids in variation_groups.values():
        if not ids:
            continue
        base = ids[0]
        base_to_group[base] = list(ids)
        for i in ids:
            id_to_base[i] = base
    return id_to_base, base_to_group


def build_raw_mappings(entries: list, id_to_base: dict, base_to_group: dict) -> dict:
    """untradeable item id -> [(tradeable_id, quantity), ...], mirroring
    ItemMapping's own static MAPPINGS Multimap -- an id can collect
    contributions from more than one entry (e.g. an "Echo" Barrows
    piece's fortified-set id maps toward both the plain piece AND its
    ornament kit)."""
    raw = defaultdict(list)
    for e in entries:
        for uid in e["untradeable_ids"]:
            if e["include_variations"]:
                base = id_to_base.get(uid, uid)
                variation_ids = base_to_group.get(base, [uid])
                for vid in variation_ids:
                    if vid == e["tradeable_id"]:
                        continue  # already IS the priced item -- nothing to derive
                    raw[vid].append((e["tradeable_id"], e["quantity"]))
            else:
                raw[uid].append((e["tradeable_id"], e["quantity"]))
    return raw


def flatten(raw_mappings: dict) -> dict:
    """Resolves every chain down to real leaf tradeable ids ahead of
    time (see ItemManager.getItemPriceWithSource()'s own recursion),
    merging duplicate leaves' quantities."""
    def _walk(item_id, qty_mult, depth, visiting):
        if depth > MAX_CHAIN_DEPTH or item_id in visiting or item_id not in raw_mappings:
            return [(item_id, qty_mult)]
        visiting = visiting | {item_id}
        out = []
        for tradeable_id, qty in raw_mappings[item_id]:
            out.extend(_walk(tradeable_id, qty_mult * qty, depth + 1, visiting))
        return out

    flat = {}
    for untradeable_id in raw_mappings:
        merged = defaultdict(int)
        for leaf_id, qty in _walk(untradeable_id, 1, 0, frozenset()):
            merged[leaf_id] += qty
        flat[untradeable_id] = sorted(
            ({"itemId": leaf_id, "qty": qty} for leaf_id, qty in merged.items()),
            key=lambda c: c["itemId"],
        )
    return flat


def main():
    print("fetching ItemMapping.java, item_variations.json, ItemID.java from runelite/runelite...")
    mapping_src = _fetch_text(ITEM_MAPPING_URL)
    variation_groups = _fetch_json(ITEM_VARIATIONS_URL)
    item_id_src = _fetch_text(ITEM_ID_URL)

    sym_to_id = parse_item_id_symbols(item_id_src)
    print(f"parsed {len(sym_to_id)} top-level ItemID symbols")

    entries = parse_item_mapping_entries(mapping_src, sym_to_id)
    print(f"parsed {len(entries)} ItemMapping entries")

    id_to_base, base_to_group = build_variation_index(variation_groups)
    raw_mappings = build_raw_mappings(entries, id_to_base, base_to_group)
    print(f"raw mappings cover {len(raw_mappings)} untradeable item ids")

    flat = flatten(raw_mappings)
    print(f"final flattened mapping: {len(flat)} untradeable item ids")

    out = {str(item_id): components for item_id, components in sorted(flat.items())}
    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
