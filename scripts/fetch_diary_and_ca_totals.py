"""One-off script: build app/data/diary_area_tier_totals.json and
app/data/combat_achievement_tier_totals.json, the fixed per-tier task counts
(same kind of static snapshot as app/data/quest_list.json).
Diary totals are counted from each area's wiki wikitext (numbered rows under
data-diary-tier="<Tier>"). Combat achievement totals come from the Tiers table
of the rendered Combat_Achievements page, since the {{Globals|ca <tier>
tasks}} values are template-resolved.

Usage: python scripts/fetch_diary_and_ca_totals.py (repo root). Re-run when
new diary or combat achievement tasks are released.
"""
import json
import pathlib
import re
import subprocess
import urllib.parse

API = "https://oldschool.runescape.wiki/api.php"
DIARY_OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "diary_area_tier_totals.json"
CA_OUTPUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "data" / "combat_achievement_tier_totals.json"

# area slug (matches DIARY_AREAS in app/mindmaps.py) -> wiki page title
DIARY_AREA_PAGES = {
    "ardougne": "Ardougne_Diary",
    "desert": "Desert_Diary",
    "falador": "Falador_Diary",
    "fremennik": "Fremennik_Diary",
    "kandarin": "Kandarin_Diary",
    "karamja": "Karamja_Diary",
    "kourend_kebos": "Kourend_%26_Kebos_Diary",
    "lumbridge_draynor": "Lumbridge_%26_Draynor_Diary",
    "morytania": "Morytania_Diary",
    "varrock": "Varrock_Diary",
    "western_provinces": "Western_Provinces_Diary",
    "wilderness": "Wilderness_Diary",
}
TIER_NAMES = ["Easy", "Medium", "Hard", "Elite"]


def _fetch(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    # Uses curl rather than urllib: the wiki API returns 403 for urllib's
    # default request. With urllib, set an explicit User-Agent.
    out = subprocess.run(["curl", "-s", url], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def fetch_diary_totals() -> dict:
    totals = {}
    for slug, page in DIARY_AREA_PAGES.items():
        data = _fetch({"action": "parse", "page": page, "prop": "wikitext", "format": "json"})
        wt = data["parse"]["wikitext"]["*"]
        positions = [(t, m.start(), m.end()) if (m := re.search(rf"^==\s*{t}\s*==", wt, re.MULTILINE)) else (t, None, None) for t in TIER_NAMES]
        tiers = {}
        for i, (tier, start, end) in enumerate(positions):
            if start is None:
                raise RuntimeError(f"{page}: {tier} header not found")
            next_start = positions[i + 1][1] if i + 1 < len(positions) and positions[i + 1][1] else len(wt)
            section = wt[end:next_start]
            rewards_m = re.search(r"^===\s*Rewards\s*===", section, re.MULTILINE)
            if rewards_m:
                section = section[: rewards_m.start()]
            count = len(re.findall(r"^\|\s*(\d+)\.\s", section, re.MULTILINE))
            tiers[tier.lower()] = count
        totals[slug] = tiers
    return totals


def fetch_ca_totals() -> dict:
    data = _fetch({"action": "parse", "page": "Combat_Achievements", "prop": "text", "section": "1", "format": "json"})
    html = data["parse"]["text"]["*"]
    text = re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", html))
    totals = {}
    for tier in ["Easy", "Medium", "Hard", "Elite", "Master", "Grandmaster"]:
        m = re.search(rf"{tier} (\d+) \d+ \d+ \d+", text)
        if not m:
            raise RuntimeError(f"Combat Achievements: {tier} row not found in rendered text")
        totals[tier.lower()] = int(m.group(1))
    return totals


def main() -> None:
    diary_totals = fetch_diary_totals()
    DIARY_OUTPUT_PATH.write_text(json.dumps(diary_totals, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote diary tier totals ({sum(sum(t.values()) for t in diary_totals.values())} tasks total) to {DIARY_OUTPUT_PATH}")

    ca_totals = fetch_ca_totals()
    CA_OUTPUT_PATH.write_text(json.dumps(ca_totals, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote combat achievement tier totals ({sum(ca_totals.values())} tasks total) to {CA_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
