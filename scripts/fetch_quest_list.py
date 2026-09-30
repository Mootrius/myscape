"""One-off script: fetch the OSRS Wiki's Category:Free-to-play quests
and Category:Members' quests membership lists and build
app/data/quest_list.json -- {"free": [...], "members": [...]}, each
already alphabetized by the category API itself (ignoring a leading
"The", matching the real in-game default Quest List interface's own
sort within each of its two groups).

Deliberately its own file rather than reusing app/quest_names.py's
existing app/data/quest_names.json snapshot (scripts/fetch_quest_names.
py) -- that one is a flat, F2P/members-undifferentiated list that also
includes miniquests, built for the Mindmaps QUEST goal's search field.
Character Overview's quest list section needs the real in-game
grouping (Free Quests, then Members' Quests, miniquests excluded
entirely -- they aren't part of that in-game list), which these two
wiki categories give directly with no further filtering needed (a spot
check against oldschool.runescape.wiki/w/Combat_Achievements-adjacent
tooling, RuneProfile, confirmed no overlap and no stray non-quest
pages in either category as of this writing).

Run with: python scripts/fetch_quest_list.py (from the repo root).
Re-run this manually (not on a schedule) if new quests are released --
this only changes when Jagex adds a quest, same reasoning
fetch_quest_names.py's own docstring gives.
"""
import json
import pathlib
import urllib.parse
import urllib.request

API = "https://oldschool.runescape.wiki/api.php"
USER_AGENT = "myscape.io/1.0 (Character Overview; contact: chandler@myscape.io)"
OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "quest_list.json"


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
        for m in data.get("query", {}).get("categorymembers", []):
            if m.get("ns") == 0 and not m["title"].startswith("Quests/"):
                titles.append(m["title"])
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        cmcontinue = cont
    return sorted(titles)


def main() -> None:
    free = fetch_category("Category:Free-to-play quests")
    members = fetch_category("Category:Members' quests")
    overlap = set(free) & set(members)
    if overlap:
        raise RuntimeError(f"Quest(s) in both categories: {overlap}")
    OUTPUT_PATH.write_text(
        json.dumps({"free": free, "members": members}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(free)} free + {len(members)} members quests to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
