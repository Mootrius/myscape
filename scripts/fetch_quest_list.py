"""One-off script: fetch the wiki's Category:Free-to-play quests and
Category:Members' quests and write app/data/quest_list.json as {"free": [...],
"members": [...]}, already sorted by the category API (ignoring a leading
"The", like the in-game Quest List).
Kept separate from app/data/quest_names.json (scripts/fetch_quest_names.py),
which is a flat list that includes miniquests. Character Overview needs the
in-game Free/Members grouping without miniquests, which these two categories
provide with no filtering.

Usage: python scripts/fetch_quest_list.py (repo root). Re-run by hand when
quests are released.
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
