"""One-off script: build the curated "day of loot" dataset behind the landing
page's Loot Tracker preview (render_landing_loot_preview in app/pages/) and
write app/data/landing_loot_demo.json.
The preview is a fixed snapshot, not a live feature: one made-up day of
killing four NPCs (Goblin, Hill Giant, Turoth, Pyrelord), with drops simulated
from hand-transcribed wiki drop tables (NPCS), spread over 24 hours with four
blank hours (BLANK_HOURS/SESSION_PLAN).
The output comes from the real aggregation (build_loot_state in app/loot.py)
run against a throwaway demo GameAccount's LootEvent rows, so the data shape
matches a real player's page at the GE prices current when the script ran.
Numbers change only when the script is re-run.
A third key, "hideBreakdown", holds one entry per hour, {npcName: {killCount,
items: {itemHideKey: value}}}. It lets the preview's hide/unhide buttons
update the chart and header totals client-side; values go through
_resolve_loot_items, the same pricing code build_loot_state uses.
Two independently seeded random.Random instances (`rng`, `loot_rng`) keep the
day's schedule and the loot rolls separate, so tuning one does not change the
other.

Usage: python scripts/gen_landing_loot_demo.py (repo root, with a real
DATABASE_URL set).
"""
import datetime as dt
import json
import pathlib
import random
import sys
import uuid

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app.database import SessionLocal
from app.loot import _resolve_loot_items, build_loot_state, item_hide_key
from app.models import Account, GameAccount, LootEvent
from app.purchase_goals import get_latest_prices, get_mapping

OUTPUT_PATH = _REPO_ROOT / "app" / "data" / "landing_loot_demo.json"
DEMO_MARKER_EMAIL = "landing-demo-internal@myscape.invalid"

# name -> OSRS item id, used for RuneLite CDN icons and GE pricing (see
# item_icon_url/get_latest_prices in app/purchase_goals.py).
ITEM_ID = {
    "Coins": 995,
    "Bones": 526, "Big bones": 532, "Bronze sq shield": 1173, "Bronze spear": 1237,
    "Body rune": 559, "Water rune": 555, "Earth rune": 557, "Bronze bolts": 877,
    "Hammer": 2347, "Goblin mail": 288, "Chef's hat": 1949, "Beer": 1917,
    "Brass necklace": 1009, "Ensouled goblin head": 13448,
    "Iron dagger": 1203, "Iron med helm": 1137, "Iron full helm": 1153, "Iron kiteshield": 1191,
    "Steel scimitar": 1325, "Steel longsword": 1295, "Iron arrow": 884, "Fire rune": 554,
    "Law rune": 563, "Limpwurt root": 225, "Ensouled giant head": 13475, "Giant key": 20754,
    "Steel platelegs": 1069, "Mithril axe": 1355, "Mithril kiteshield": 1197,
    "Adamant full helm": 1161, "Rune dagger": 1213, "Necklace of Fangs": 34401,
    "Nature rune": 561, "Grimy ranarr weed": 207, "Toadflax seed": 5296,
    "Fiendish ashes": 25766, "Mithril full helm": 1159, "Staff of fire": 1387,
    "Mithril chainbody": 1109, "Adamant med helm": 1145, "Steel boots": 4123,
    "Chaos rune": 562, "Death rune": 560, "Gold ore": 444, "Jug of wine": 1993,
    "Uncut sapphire": 1623, "Uncut emerald": 1621, "Uncut ruby": 1619,
    "Dragon bones": 536, "Green dragonhide": 1753, "Steel battleaxe": 1365,
    "Mithril spear": 1243, "Bass": 365, "Adamantite ore": 449, "Grimy irit leaf": 209,
    "Uncut diamond": 1617, "Ensouled dragon head": 13511,
    "Frost dragon bones": 31729, "Dragon metal sheet": 31996, "Rune 2h sword": 1319,
    "Rune kiteshield": 1201, "Rune longsword": 1303, "Rune pickaxe": 1275,
    "Adamant platebody": 1123, "Adamant warhammer": 1345, "Air rune": 556,
    "Blood rune": 565, "Mist rune": 4695, "Dragon cannonball": 31916,
    "Rune cannonball": 31914, "Rune knife": 868, "Dragon arrowtips": 11237,
    "Superior dragon bones": 22124, "Runite ore": 451, "Dragon nails": 31406,
    "Apple pie": 2323, "Draconic visage": 11286,
    "Fangs of Venenatis": 27670, "Dragon 2h sword": 7158, "Dragon pickaxe": 11920,
    "Voidwaker gem": 27687, "Treasonous ring": 12605, "Mystic air staff": 1405,
    "Rune dart": 811, "Rune platelegs": 1079, "Rune sq shield": 1185,
    "Dragon dagger": 1215, "Diamond bolts (e)": 9243, "Steel cannonball": 2,
    "Onyx bolt tips": 9194, "Magic logs": 1513, "Supercompost": 6034,
    "Dark crab": 11936, "Battlestaff": 1391, "Red spiders' eggs": 223,
    "Grimy snapdragon": 3051, "Antidote++(4)": 5952, "Super restore(4)": 3024,
    "Unicorn horn": 237, "Uncut dragonstone": 1631,
    "Ancient blood ornament kit": 28336, "Venator vestige": 28283,
    "Chromium ingot": 28276, "Leviathan's lure": 28325, "Virtus mask": 26241,
    "Virtus robe top": 26243, "Virtus robe bottom": 26245, "Scarred tablet": 28332,
    "Awakener's orb": 28334, "Smoke quartz": 28274,
    "Prayer potion(3)": 139, "Ranging potion(2)": 171, "Sea turtle": 397,
    "Aether catalyst": 30771, "Iron ore": 440, "Silver ore": 442, "Coal": 453,
    "Sapphire": 1607, "Emerald": 1605, "Ruby": 1603, "Dragon javelin tips": 19582,
    "Dragon bolts (unf)": 21930, "Raw manta ray": 389, "Anglerfish": 13441,
    "Bronze arrow": 882, "Mithril arrow": 888, "Adamant arrow": 890, "Rune arrow": 892,
    "Smoke rune": 4697, "Soul rune": 566, "Brimstone key": 23083,
}


def T(*rows):
    """rows: (name, qty, weight), one per main-table entry, weight being the
    wiki's numerator. Returns (rows, denom=sum of weights) for roll_table; any
    gap to the wiki's real denominator is an implicit "nothing" roll.
    """
    denom = sum(w for _, _, w in rows)
    return rows, denom


def roll_table(rows, denom, rng):
    r = rng.uniform(0, denom)
    cum = 0.0
    for name, qty, weight in rows:
        cum += weight
        if r < cum:
            return (name, qty)
    return None


# Each NPC: always=[(name,qty), ...] (every kill), tables=[(rows, denom), ...]
# (independently rolled weighted tables), tertiary=[(name, qty, probability),
# ...] (independent per-kill rolls at the wiki's absolute rate).
NPCS = {
    "Goblin": {
        "combat_level": 2,
        "always": [("Bones", 1)],
        "tables": [T(
            ("Bronze sq shield", 1, 3), ("Bronze spear", 1, 4), ("Body rune", 7, 5),
            ("Water rune", 6, 6), ("Earth rune", 4, 3), ("Bronze bolts", 8, 3),
            ("Coins", 5, 28), ("Coins", 9, 3), ("Coins", 15, 3), ("Coins", 20, 2), ("Coins", 1, 1),
            ("Hammer", 1, 15), ("Goblin mail", 1, 5), ("Chef's hat", 1, 3), ("Beer", 1, 2),
            ("Brass necklace", 1, 1),
        )],
        "tertiary": [("Ensouled goblin head", 1, 1 / 35)],
    },
    "Hill Giant": {
        "combat_level": 28,
        "always": [("Big bones", 1)],
        "tables": [T(
            ("Iron dagger", 1, 4), ("Iron med helm", 1, 5), ("Iron full helm", 1, 5),
            ("Iron kiteshield", 1, 3), ("Steel scimitar", 1, 2), ("Steel longsword", 1, 2),
            ("Iron arrow", 3, 6), ("Fire rune", 15, 3), ("Water rune", 7, 3), ("Law rune", 2, 3),
            ("Coins", 5, 18), ("Coins", 38, 14), ("Coins", 52, 10), ("Coins", 15, 8),
            ("Coins", 10, 7), ("Coins", 8, 6), ("Coins", 88, 2),
            ("Limpwurt root", 1, 11), ("Beer", 1, 6), ("Giant key", 1, 1),
        )],
        "tertiary": [("Ensouled giant head", 1, 1 / 25)],
    },
    "Turoth": {
        "combat_level": 83,
        "always": [("Bones", 1)],
        "tables": [T(
            ("Steel platelegs", 1, 7), ("Mithril axe", 1, 3), ("Mithril kiteshield", 1, 1),
            ("Adamant full helm", 1, 1), ("Rune dagger", 1, 1), ("Necklace of Fangs", 1, 1),
            ("Law rune", 3, 6), ("Nature rune", 15, 5), ("Limpwurt root", 1, 7),
            ("Coins", 44, 29), ("Coins", 132, 12), ("Coins", 440, 1),
            ("Grimy ranarr weed", 1, 4), ("Toadflax seed", 1, 2),
        )],
        "tertiary": [],
    },
    "Pyrelord": {
        "combat_level": 60,
        "always": [("Fiendish ashes", 1)],
        "tables": [T(
            ("Mithril axe", 1, 4), ("Mithril full helm", 1, 4), ("Staff of fire", 1, 3),
            ("Mithril chainbody", 1, 2), ("Adamant med helm", 1, 1), ("Steel boots", 1, 1),
            ("Fire rune", 50, 21), ("Fire rune", 100, 8), ("Chaos rune", 20, 5), ("Death rune", 5, 3),
            ("Coins", 10, 7), ("Coins", 60, 24), ("Coins", 200, 20), ("Coins", 400, 10), ("Coins", 600, 2),
            ("Gold ore", 2, 8), ("Jug of wine", 1, 2),
            ("Uncut sapphire", 1, 1), ("Uncut emerald", 1, 1), ("Uncut ruby", 1, 1),
        )],
        "tertiary": [],
    },
}

KC = {
    "Goblin": 238, "Hill Giant": 109, "Turoth": 33, "Pyrelord": 83,
}


def simulate_kill(npc_name, rng):
    spec = NPCS[npc_name]
    items = []
    for name, qty in spec["always"]:
        items.append((name, qty))
    for rows, denom in spec["tables"]:
        hit = roll_table(rows, denom, rng)
        if hit:
            items.append(hit)
    for name, qty, prob in spec["tertiary"]:
        if rng.random() < prob:
            items.append((name, qty))
    return items


def build_events():
    rng = random.Random(9)  # schedule timing (session split, per-kill timestamps)
    loot_rng = random.Random(9)  # loot rolls only -- see this file's own module
    # A second, independent Random instance; see the module docstring.

    # 24 one-hour slots with 4 blank (an overnight lull and three breaks), the
    # rest each carrying one NPC session, with that NPC's kills spread unevenly
    # across the session's minutes.
    blank_hours = {3, 4, 9, 20}
    active_hours = [h for h in range(24) if h not in blank_hours]  # 20 hours

    # Roughly proportional to each NPC's kill count (Goblin 238 down to Turoth
    # 33).
    session_plan = [
        ("Goblin", 3), ("Hill Giant", 2), ("Turoth", 1), ("Pyrelord", 2),
        ("Goblin", 3), ("Hill Giant", 2), ("Pyrelord", 2),
        ("Goblin", 2), ("Turoth", 1), ("Hill Giant", 2),
    ]
    assert sum(h for _, h in session_plan) == len(active_hours)

    hour_cursor = 0
    npc_hours = {name: [] for name in NPCS}
    for npc, span in session_plan:
        for _ in range(span):
            npc_hours[npc].append(active_hours[hour_cursor])
            hour_cursor += 1
    for name in NPCS:
        assert npc_hours[name], name

    base_date = dt.datetime(2026, 9, 22, 0, 0, 0, tzinfo=dt.timezone.utc)

    events = []
    for npc, kc in KC.items():
        hours = npc_hours[npc]
        weights = [rng.uniform(0.6, 1.4) for _ in hours]
        total_w = sum(weights)
        counts = [max(1, round(kc * w / total_w)) for w in weights]
        diff = kc - sum(counts)
        i = 0
        while diff != 0:
            idx = i % len(counts)
            if diff > 0:
                counts[idx] += 1
                diff -= 1
            elif counts[idx] > 1:
                counts[idx] -= 1
                diff += 1
            i += 1

        for hour, n in zip(hours, counts):
            offsets = sorted(rng.uniform(0, 3599) for _ in range(n))
            for off in offsets:
                ts = base_date + dt.timedelta(hours=hour, seconds=off)
                items = simulate_kill(npc, loot_rng)
                events.append({
                    "source_name": npc,
                    "source_type": "npc",
                    "combat_level": NPCS[npc]["combat_level"],
                    "items": [
                        {"item_id": ITEM_ID[name], "item_name": name, "quantity": qty}
                        for name, qty in items
                    ],
                    "occurred_at": ts,
                })

    events.sort(key=lambda e: e["occurred_at"])
    return events, base_date


def main():
    events, base_date = build_events()
    print(f"Simulated {len(events)} kills across {len(NPCS)} NPCs.")

    db = SessionLocal()
    try:
        acct = db.query(Account).filter(Account.email == DEMO_MARKER_EMAIL).first()
        if acct is None:
            acct = Account(id=uuid.uuid4(), email=DEMO_MARKER_EMAIL, password_hash=None)
            db.add(acct)
            db.flush()

        ga = db.query(GameAccount).filter(GameAccount.account_id == acct.id).first()
        if ga is None:
            ga = GameAccount(id=uuid.uuid4(), account_id=acct.id, runescape_name="LandingDemo")
            db.add(ga)
            db.flush()

        # Wipe any previous run's rows so re-running regenerates cleanly.
        db.query(LootEvent).filter(LootEvent.game_account_id == ga.id).delete()
        db.flush()

        for i, e in enumerate(events):
            db.add(LootEvent(
                id=uuid.uuid4(),
                game_account_id=ga.id,
                event_id=f"demo-{i}",
                source_name=e["source_name"],
                source_type=e["source_type"],
                combat_level=e["combat_level"],
                items=e["items"],
                occurred_at=e["occurred_at"],
            ))
        db.commit()

        start = base_date
        end = base_date + dt.timedelta(hours=24)
        full_state = build_loot_state(db, ga, start, end)
        print("windowKills:", full_state["windowKills"], "windowValue:", full_state["windowValue"])
        print("blank buckets:", [i for i, b in enumerate(full_state["buckets"]) if b["killCount"] == 0])

        # One build_loot_state call per bucket over its [start, end) range, the
        # same call the real page makes when a bar is clicked
        # (bucketUrl()/loadBucketData() in render_loot_tracker, app/pages/).
        # Precomputed because the preview has no backend;
        # render_landing_loot_preview's fetch shim serves it by each bucket's
        # `start` timestamp.
        bucket_states = []
        for b in full_state["buckets"]:
            b_start = dt.datetime.fromisoformat(b["start"])
            b_end = dt.datetime.fromisoformat(b["end"]) - dt.timedelta(milliseconds=1)
            bucket_states.append(build_loot_state(db, ga, b_start, b_end))

        # hideBreakdown (see the module docstring), built from the in-memory
        # `events` rather than re-querying the DB.
        # get_mapping()/get_latest_prices() are cached at module level
        # (app/purchase_goals.py), so the prices match full_state/bucket_states.
        mapping, _mapping_error = get_mapping()
        prices, _prices_error = get_latest_prices()
        hide_breakdown = [dict() for _ in range(24)]
        for e in events:
            if e["source_type"] != "npc":
                continue  # only NPCs ever get an eye button -- see build_loot_state's own "By NPC" row being npc-only
            hour_idx = int((e["occurred_at"] - base_date).total_seconds() // 3600)
            if not (0 <= hour_idx < 24):
                continue
            resolved_items, _ = _resolve_loot_items(e["items"], mapping, prices, set())
            npc_bucket = hide_breakdown[hour_idx].setdefault(
                e["source_name"], {"killCount": 0, "items": {}}
            )
            npc_bucket["killCount"] += 1
            for it in resolved_items:
                key = item_hide_key(it["itemId"], it["itemName"])
                npc_bucket["items"][key] = npc_bucket["items"].get(key, 0) + it["value"]

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w") as f:
            json.dump(
                {"full": full_state, "buckets": bucket_states, "hideBreakdown": hide_breakdown},
                f, separators=(",", ":"),
            )
        print(f"wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")

        # Remove the demo account and its rows so nothing lingers.
        db.query(LootEvent).filter(LootEvent.game_account_id == ga.id).delete()
        db.delete(ga)
        db.delete(acct)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
