"""One-off script: fetch the OSRS Wiki's Category:Quests and
Category:Miniquests membership lists and build a sorted
["Quest Name", ...] JSON index to app/data/quest_names.json for the
Mindmaps QUEST goal's search field.

Unlike items (scripts/fetch_item_ids.py) or NPCs
(scripts/fetch_npc_names.py), the wiki's Bucket data extension has no
table for quests (`bucket('infobox_quest')` does not exist), so this
uses the standard MediaWiki `list=categorymembers` API instead, which
simply lists page titles belonging to a category.

Both categories carry more than just quest/miniquest pages -- namespace
14 entries are wiki subcategories (e.g. "Category:Quest NPCs"), and a
handful of namespace-0 pages are meta/list pages about quests rather
than quests themselves (e.g. "Quests", "Quest Difficulties",
"Optimal quest guide") or "/"-suffixed subpages of one
(e.g. "Quests/Novice", "Recipe for Disaster/Freeing Pirate Pete" --
that last one is a walkthrough subsection of the single quest "Recipe
for Disaster", not a separate quest). Both are filtered out below.

Run with: python scripts/fetch_quest_names.py (from the repo root).

Re-run this manually (not on a schedule) if new quests/miniquests are
released and don't show up in search -- like items, this data only
changes when Jagex adds content, so a bundled snapshot refreshed by
hand is plenty.
"""
import json
import pathlib
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Mindmaps; contact: chandler@myscape.io)"
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "quest_names.json"

# Namespace-0 category members that are meta/list pages about quests,
# not quests themselves -- confirmed by hand against the category's
# actual membership (see this script's docstring).
NON_QUEST_TITLES = {
    "Quests",
    "Quest Difficulties",
    "Quest experience rewards",
    "Quest experience rewards (F2P)",
    "Quest item rewards",
    "Quest point hood",
    "Quest points",
    "Optimal quest guide",
}
# "Category:Miniquests" itself is also returned as a member of
# Category:Miniquests' own listing in some wiki category setups; drop
# it defensively alongside the quest meta-pages above.
NON_QUEST_TITLES |= {"Miniquests"}


def fetch_category(cmtitle: str) -> list:
    titles = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": cmtitle,
            "cmlimit": "500",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        url = API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(data["error"])
        members = data.get("query", {}).get("categorymembers", [])
        for m in members:
            if m.get("ns") != 0:
                continue  # a subcategory, not a page
            title = m.get("title") or ""
            if "/" in title:
                continue  # a subpage of a quest/list, not its own entry
            if title in NON_QUEST_TITLES:
                continue
            titles.append(title)
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
    return titles


def main():
    quests = fetch_category("Category:Quests")
    print(f"fetched {len(quests)} quests")
    miniquests = fetch_category("Category:Miniquests")
    print(f"fetched {len(miniquests)} miniquests")

    combined = sorted(set(quests) | set(miniquests), key=lambda s: s.lower())
    print(f"total unique quest/miniquest names: {len(combined)}")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(combined, f, separators=(",", ":"))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
