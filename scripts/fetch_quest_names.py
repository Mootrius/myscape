"""One-off script: fetch the wiki's Category:Quests and Category:Miniquests and
write app/data/quest_names.json, a sorted ["Quest Name", ...] list for the
Mindmaps QUEST goal's search.
The Bucket extension has no quest table, so this uses the MediaWiki
`list=categorymembers` API. Both categories also hold subcategories (namespace
14), meta/list pages ("Quests", "Quest Difficulties") and "/" subpages
("Recipe for Disaster/Freeing Pirate Pete"); these are filtered out.

Usage: python scripts/fetch_quest_names.py (repo root). Re-run by hand when
quests or miniquests are released.
"""
import json
import pathlib
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Mindmaps; contact: chandler@myscape.io)"
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "quest_names.json"

# Namespace-0 members that are meta/list pages, not quests.
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
# Some category setups list "Category:Miniquests" as its own member; drop it
# too.
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
