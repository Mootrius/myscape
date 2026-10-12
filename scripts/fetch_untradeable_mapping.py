"""One-off script: port RuneLite's "Item Prices" data (the table behind the
GE-value tooltip on untradeable items, e.g. Crystal helm -> Crystal armour
seed) into app/data/untradeable_mapping.json, a {untradeableItemId:
[{"itemId": tradeableItemId, "qty": int}, ...]} index. Possessions Monitoring
(app/possessions.py) and Purchase Goals (app/purchase_goals.py) use it to
value items with no GE listing.
The wiki price-mapping API lacks this data. RuneLite keeps it in ItemMapping
(BSD 2-Clause), with ItemVariationMapping (item_variations.json) grouping
charge/recolour variants. This script reproduces both plus
ItemManager.getItemPriceWithSource()'s recursive resolution (e.g. "Echo"
Barrows pieces price as the plain piece plus its ornament kit), flattening
each chain to GE-priceable leaf ids.

Sources (runelite/runelite, master):
- runelite-client/src/main/java/net/runelite/client/game/ItemMapping.java
- runelite-client/src/main/resources/item_variations.json
- runelite-api/src/main/java/net/runelite/api/gameval/ItemID.java, which
resolves the symbolic `ItemID.FOO` references. It also declares nested `Cert`
and `Placeholder` classes that reuse the same symbols with different ids
(PRIF_ARMOUR_SEED is 23956 top-level). ItemMapping only uses top-level names,
so symbols are resolved against the top-level class body, cut off before
`Cert`.

Usage: python scripts/fetch_untradeable_mapping.py (repo root). Re-run by hand
when RuneLite's upstream table changes.
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

# Safety cap against cycles in upstream data (real chains are at most 2 hops
# deep).
MAX_CHAIN_DEPTH = 6


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _fetch_json(url: str):
    return json.loads(_fetch_text(url))


def parse_item_id_symbols(item_id_src: str) -> dict:
    """symbol -> numeric id, top-level ItemID class body only (see the module
    docstring for why Cert/Placeholder are excluded).
    """
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
    ItemMapping(tradeableItem, boolean includeVariations, long quantity,
    int... untradableItems)
    """
    enum_start = mapping_src.index("public enum ItemMapping")
    body_start = mapping_src.index("{", enum_start) + 1
    # The enum's entries end where its field declarations / static{} initializer
    # begin.
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
    """Mirrors ItemVariationMapping: id -> its group's base id (first listed),
    and base id -> full group.
    """
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
    ItemMapping's MAPPINGS multimap. An id can collect several entries (an
    "Echo" Barrows piece maps to the plain piece and its ornament kit).
    """
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
    """Resolve each chain to leaf tradeable ids, merging quantities of duplicate
    leaves.
    """
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
