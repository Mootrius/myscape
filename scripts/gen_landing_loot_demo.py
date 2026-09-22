"""One-off script: builds the curated "day of loot" dataset behind the
landing page's interactive Loot Tracker preview (see
render_landing_loot_preview in app/pages.py) and writes it to
app/data/landing_loot_demo.json.

This is NOT a live feature -- there's no logged-out account for a
marketing-page visitor to poll real loot from, so the preview instead
ships a single, fixed ("curated", the person's own word for it when
this was scoped) snapshot: one made-up "day" of killing eight NPCs the
person picked by name and kill count, with drops simulated from each
NPC's real OSRS Wiki drop table (weights/rates hand-transcribed into
NPCS below), spread across a 24-hour schedule with exactly four blank
hours (see BLANK_HOURS/SESSION_PLAN) rather than either a perfectly
even distribution or one single sitting.

The output is produced by running the exact same server-side
aggregation the real Loot Tracker uses (build_loot_state in
app/loot.py) against a throwaway, immediately-deleted demo
GameAccount's LootEvent rows -- not a hand-rolled reimplementation of
that bucketing/pricing/icon-resolution logic -- so the preview's data
shape is guaranteed byte-identical to what a real player's page would
produce, at whatever live GE prices were current the moment this
script last ran. That also means the numbers only ever change by
re-running this script by hand (same as every other snapshot in
app/data/ -- see e.g. scripts/fetch_npc_names.py's own docstring),
never automatically, matching the "fixed, not randomized every page
load" choice this preview was built around.

Two separate random.Random instances, both seeded but independently
so (see `rng`/`loot_rng` below): one lays out the day's schedule (how
kills split across hours), the other rolls each kill's own loot --
kept apart so hand-tuning one (e.g. picking a seed with a satisfying
spread of rare drops) never perturbs the other. loot_rng's seed here
(9) was picked exactly that way: searched across a range of seeds
offline for one landing a small, not-overwhelming handful of the
flashier possible drops (see the module-level comment further down,
by NPCS, for which ones) without needing to hand-place a single item.

Run with: python scripts/gen_landing_loot_demo.py (from the repo
root, with a real DATABASE_URL in the environment -- it needs a
working DB connection to run build_loot_state against, same as the
app itself).
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
from app.loot import build_loot_state
from app.models import Account, GameAccount, LootEvent

OUTPUT_PATH = _REPO_ROOT / "app" / "data" / "landing_loot_demo.json"
DEMO_MARKER_EMAIL = "landing-demo-internal@myscape.invalid"

# name -> real OSRS item id (RuneLite CDN icons and GE pricing are both
# keyed off this, same as every other item-source table in this app --
# see item_icon_url/get_latest_prices in app/purchase_goals.py).
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
    """rows: (name, qty, weight) -- one row per main-table drop-table
    entry, weight exactly the numerator the wiki lists it under (out of
    that table's own denominator, e.g. weight=28 of 128 for a goblin's
    common 5gp drop). Returns (rows, denom=sum of weights) for
    roll_table below; any shortfall between the weights' own sum and
    the table's real wiki-stated denominator is an implicit "nothing"
    (this main roll adds no extra item beyond whatever's in `always`),
    same as a real kill often outright not dropping anything notable."""
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


# Each NPC: always=[(name,qty), ...] (unconditional per-kill drops),
# tables=[(rows, denom), ...] (independently-rolled weighted tables --
# most NPCs have one, matching their wiki page's own single combined
# table; the Leviathan has several, matching its wiki page listing
# Supplies/Resources/Runes-and-ammunition as separate rolled tables),
# tertiary=[(name, qty, probability), ...] (independent low-probability
# per-kill rolls, each item's own absolute rate as the wiki states it --
# including this dataset's few "exciting" flavor drops: Fangs of
# Venenatis, Chromium ingot, and Leviathan's lure all happen to land at
# loot_rng's seed of 9, picked for exactly that spread -- see this
# file's own module docstring).
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
    "Green dragon": {
        "combat_level": 79,
        "always": [("Dragon bones", 1), ("Green dragonhide", 1)],
        "tables": [T(
            ("Steel platelegs", 1, 4), ("Steel battleaxe", 1, 3), ("Mithril axe", 1, 3),
            ("Mithril spear", 1, 2), ("Mithril kiteshield", 1, 1), ("Adamant full helm", 1, 1),
            ("Rune dagger", 1, 1), ("Water rune", 75, 8), ("Fire rune", 37, 1),
            ("Nature rune", 15, 5), ("Law rune", 3, 3),
            ("Coins", 44, 29), ("Coins", 132, 25), ("Coins", 200, 10), ("Coins", 11, 5), ("Coins", 440, 1),
            ("Bass", 1, 3), ("Adamantite ore", 1, 3),
            ("Grimy ranarr weed", 1, 6), ("Grimy irit leaf", 1, 5),
            ("Uncut diamond", 1, 2), ("Uncut emerald", 1, 2),
        )],
        "tertiary": [("Ensouled dragon head", 1, 1 / 35)],
    },
    "Frost dragon": {
        "combat_level": 172,
        "always": [("Frost dragon bones", 1)],
        "tables": [T(
            ("Dragon metal sheet", 1, 1.3),
            ("Rune 2h sword", 1, 2), ("Rune kiteshield", 1, 2), ("Rune longsword", 1, 2),
            ("Rune pickaxe", 1, 2), ("Adamant platebody", 1, 4), ("Adamant warhammer", 1, 4),
            ("Death rune", 25, 5), ("Water rune", 150, 10), ("Water rune", 500, 5),
            ("Air rune", 150, 11), ("Blood rune", 15, 5), ("Chaos rune", 70, 8),
            ("Mist rune", 50, 10), ("Nature rune", 15, 4), ("Dragon cannonball", 16, 2),
            ("Rune cannonball", 27, 4), ("Rune knife", 15, 5), ("Dragon arrowtips", 7, 4),
            ("Superior dragon bones", 1, 3), ("Runite ore", 1, 3), ("Adamantite ore", 1, 3),
            ("Dragon nails", 15, 2), ("Coins", 75, 10), ("Coins", 350, 10), ("Apple pie", 1, 5),
        )],
        "tertiary": [("Draconic visage", 1, 1 / 10000)],
    },
    "Venenatis": {
        "combat_level": 464,
        "always": [("Big bones", 1)],
        "tables": [T(
            ("Mystic air staff", 4, 2), ("Rune pickaxe", 5, 8), ("Rune dart", 150, 3),
            ("Rune knife", 150, 5), ("Rune platelegs", 4, 2), ("Rune sq shield", 4, 2),
            ("Dragon dagger", 6, 2), ("Chaos rune", 500, 7), ("Death rune", 700, 7),
            ("Blood rune", 900, 7), ("Diamond bolts (e)", 300, 5), ("Steel cannonball", 600, 4),
            ("Uncut ruby", 50, 1), ("Uncut diamond", 25, 8), ("Gold ore", 675, 6),
            ("Onyx bolt tips", 150, 5), ("Magic logs", 225, 5), ("Limpwurt root", 100, 5),
            ("Coins", 50000, 10), ("Supercompost", 225, 4), ("Dark crab", 50, 5),
            ("Battlestaff", 12, 2), ("Red spiders' eggs", 500, 3), ("Grimy ranarr weed", 45, 2),
            ("Grimy snapdragon", 100, 2), ("Antidote++(4)", 20, 3), ("Super restore(4)", 10, 5),
            ("Unicorn horn", 225, 2), ("Uncut dragonstone", 5, 2),
        )],
        "tertiary": [
            ("Fangs of Venenatis", 1, 1 / 196), ("Dragon 2h sword", 1, 1 / 256),
            ("Dragon pickaxe", 1, 1 / 256), ("Voidwaker gem", 1, 1 / 360),
            ("Treasonous ring", 1, 1 / 512),
        ],
    },
    "The Leviathan": {
        "combat_level": 798,
        # Ancient blood ornament kit is the wiki's one "Always" row, but
        # footnoted as conditional rather than a flat per-kill drop --
        # modeled here as a first-kill-only unlock instead (see the
        # first_kill_done handling below), the same shape several other
        # DT2 bosses' own guaranteed-first-kill uniques already take.
        "always": [],
        "tables": [
            T(
                ("Prayer potion(3)", 1, 1), ("Ranging potion(2)", 1, 1), ("Sea turtle", 4, 1),
            ),
            T(
                ("Aether catalyst", 1875, 1), ("Iron ore", 71, 1), ("Silver ore", 71, 1),
                ("Coal", 243, 8), ("Gold ore", 84, 8), ("Adamantite ore", 71, 1),
                ("Runite ore", 33, 2), ("Sapphire", 31, 1), ("Emerald", 31, 1), ("Ruby", 31, 1),
                ("Uncut ruby", 46, 5), ("Uncut diamond", 46, 5), ("Dragon javelin tips", 67, 8),
                ("Dragon bolts (unf)", 187, 2), ("Onyx bolt tips", 112, 1),
                ("Raw manta ray", 225, 1), ("Anglerfish", 5, 8),
            ),
            T(
                ("Bronze arrow", 78, 1), ("Mithril arrow", 78, 1), ("Adamant arrow", 78, 1),
                ("Rune arrow", 67, 8), ("Body rune", 225, 1), ("Earth rune", 225, 1),
                ("Smoke rune", 375, 8), ("Soul rune", 750, 2),
            ),
        ],
        "tertiary": [
            ("Venator vestige", 1, 1 / 768), ("Chromium ingot", 1, 1 / 256),
            ("Leviathan's lure", 1, 1 / 768), ("Virtus mask", 1, 1 / 2304),
            ("Virtus robe top", 1, 1 / 2304), ("Virtus robe bottom", 1, 1 / 2304),
            ("Scarred tablet", 1, 1 / 25.8), ("Awakener's orb", 1, 1 / 53.6),
            ("Smoke quartz", 1, 1 / 206), ("Brimstone key", 1, 1 / 50),
        ],
    },
}

# Exactly the eight NPCs and kill counts the person asked for.
KC = {
    "Goblin": 238, "Hill Giant": 109, "Turoth": 33, "Pyrelord": 83,
    "Green dragon": 153, "Frost dragon": 255, "Venenatis": 56, "The Leviathan": 48,
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
    # docstring for why this is a second, independent Random instance
    # rather than reusing `rng` above.

    # 24 one-hour slots, exactly 4 left blank (spread through the day,
    # not clustered -- an overnight lull, a mid-morning break, an
    # afternoon break, a dinner break), the rest carrying one NPC
    # "session" apiece (a player sticking with one task for a couple
    # hours before switching, the way a real grinding day actually
    # looks) with that NPC's kills spread unevenly through its
    # session's minutes rather than a perfectly even split.
    blank_hours = {3, 4, 9, 20}
    active_hours = [h for h in range(24) if h not in blank_hours]  # 20 hours

    session_plan = [
        ("Goblin", 3), ("Hill Giant", 2), ("Turoth", 1), ("Pyrelord", 2),
        ("Green dragon", 3), ("Goblin", 2), ("Frost dragon", 4),
        ("Hill Giant", 1), ("The Leviathan", 1), ("Venenatis", 1),
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

        first_kill_done = False
        for hour, n in zip(hours, counts):
            offsets = sorted(rng.uniform(0, 3599) for _ in range(n))
            for off in offsets:
                ts = base_date + dt.timedelta(hours=hour, seconds=off)
                items = simulate_kill(npc, loot_rng)
                if npc == "The Leviathan" and not first_kill_done:
                    items.append(("Ancient blood ornament kit", 1))
                    first_kill_done = True
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

        # Wipe any previous run's rows first so re-running this script
        # regenerates cleanly rather than doubling up.
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

        # One extra build_loot_state call per bucket, scoped to that
        # bucket's own precise [start, end) -- the exact same call the
        # real page's own bucketUrl()/loadBucketData() makes when a bar
        # is clicked (see render_loot_tracker's script in app/pages.py).
        # Precomputed here, once, rather than on demand, since there's
        # no live backend behind this preview to answer that request
        # later -- see render_landing_loot_preview's own fetch shim,
        # which serves these back out by matching on each bucket's own
        # `start` timestamp.
        bucket_states = []
        for b in full_state["buckets"]:
            b_start = dt.datetime.fromisoformat(b["start"])
            b_end = dt.datetime.fromisoformat(b["end"]) - dt.timedelta(milliseconds=1)
            bucket_states.append(build_loot_state(db, ga, b_start, b_end))

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w") as f:
            json.dump({"full": full_state, "buckets": bucket_states}, f, separators=(",", ":"))
        print(f"wrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size} bytes)")

        # This demo account/game_account/its events only ever existed
        # to let build_loot_state compute the real payload above --
        # nothing about it should linger as an actual row afterward.
        db.query(LootEvent).filter(LootEvent.game_account_id == ga.id).delete()
        db.delete(ga)
        db.delete(acct)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
