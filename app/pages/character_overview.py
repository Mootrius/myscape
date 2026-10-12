"""Character Overview: the page, its public profile, and the landing preview."""
import json
import os
from html import escape
from typing import TYPE_CHECKING, Optional, Tuple

from app.pages.asset_loader import read_asset
from app.pages.icons import _wiki_icon_url
from app.pages.player import PlayerView
from app.pages.shell import _shell

if TYPE_CHECKING:
    from app.models import GameAccount


_CHARACTER_OVERVIEW_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "character-overview.css"
)

try:
    _CHARACTER_OVERVIEW_CSS_VERSION = int(os.path.getmtime(_CHARACTER_OVERVIEW_CSS_PATH))
except OSError:
    _CHARACTER_OVERVIEW_CSS_VERSION = 0

# Snapshot for the landing Character Overview preview: real summary, progress,
# skills and collection-log pulls in one JSON file. The 3D model is a separate
# binary asset (app/static/img/landing-character-overview-demo-model.glb) the
# preview's extra_head points the viewer at directly.
_LANDING_CHARACTER_OVERVIEW_DEMO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "landing_character_overview_demo.json"
)

_landing_character_overview_demo_data = None


def _get_landing_character_overview_demo_data() -> Optional[dict]:
    global _landing_character_overview_demo_data
    if _landing_character_overview_demo_data is None:
        try:
            with open(_LANDING_CHARACTER_OVERVIEW_DEMO_PATH, "r") as f:
                _landing_character_overview_demo_data = json.load(f)
        except (OSError, ValueError):
            return None
    return _landing_character_overview_demo_data


_ICON_SUMMARY_COMBAT_LEVEL = _wiki_icon_url("Character_Summary_-_Combat_Level_icon.png")

_ICON_SUMMARY_TOTAL_LEVEL = _wiki_icon_url("Character_Summary_-_Total_Level.png")

_ICON_SUMMARY_TOTAL_XP = _wiki_icon_url("Character_Summary_-_Total_XP_icon.png")

_ICON_SUMMARY_QUESTS = _wiki_icon_url("Quest_List_tab_icon.png")

_ICON_SUMMARY_ACHIEVEMENTS = _wiki_icon_url("Achievement_Diaries_tab_icon.png")

_ICON_SUMMARY_COMBAT_TASKS = _wiki_icon_url("Character_Summary_-_Combat_Tasks_Completed_icon.png")

_ICON_SUMMARY_COLLECTIONS = _wiki_icon_url("Character_Summary_-_Collections_Logged_icon.png")

# Account-type tile: one icon per GameAccount.account_type code (app/models.py)
# plus the all-caps value label (e.g. "UGIM"). The icon is part of the value, so
# the script (ACCOUNT_TYPE_INFO, baked from this dict) swaps the <img>
# src/alt/title once account_type is fetched. MAIN's coin is the pre-fetch
# default.
_ACCOUNT_TYPE_INFO = {
    "MAIN": (_wiki_icon_url("Coins_10000.png"), "MAIN"),
    "IRONMAN": (_wiki_icon_url("Ironman_helm.png"), "IRONMAN"),
    "UIM": (_wiki_icon_url("Ultimate_ironman_helm.png"), "UIM"),
    "HCIM": (_wiki_icon_url("Hardcore_ironman_helm.png"), "HCIM"),
    "GIM": (_wiki_icon_url("Group_ironman_helm.png"), "GIM"),
    "HCGIM": (_wiki_icon_url("Hardcore_group_ironman_helm.png"), "HCGIM"),
    "UGIM": (_wiki_icon_url("Group_ironman_helm_(unranked).png"), "UGIM"),
}

_SUMMARY_STATS = (
    # (element key, icon, alt text), all from /api/character-overview/summary
    # (GameAccount.character_summary_* plus account_type, synced by
    # MyscapeClient#syncCharacterSummary in myscape-plugin). For accountType the
    # script swaps icon and alt (see _ACCOUNT_TYPE_INFO).
    ("accountType", _ACCOUNT_TYPE_INFO["MAIN"][0], "Account type"),
    ("combatLevel", _ICON_SUMMARY_COMBAT_LEVEL, "Combat level"),
    ("totalLevel", _ICON_SUMMARY_TOTAL_LEVEL, "Total level"),
    ("totalXp", _ICON_SUMMARY_TOTAL_XP, "Total experience"),
    ("quests", _ICON_SUMMARY_QUESTS, "Quests completed"),
    ("achievements", _ICON_SUMMARY_ACHIEVEMENTS, "Achievements completed"),
    ("combatTasks", _ICON_SUMMARY_COMBAT_TASKS, "Combat tasks completed"),
    ("collections", _ICON_SUMMARY_COLLECTIONS, "Collections logged"),
)

_SKILL_GRID_ORDER = (
    # Row-major order for the 3x8 skill card in render_character_overview,
    # matching the in-game Skills tab. Sailing (the 24th skill) takes the slot
    # of the omitted "Total level" footer. SKILL_NAMES (app/mindmaps.py) is a
    # set, so this tuple holds the order.
    "attack", "hitpoints", "mining",
    "strength", "agility", "smithing",
    "defence", "herblore", "fishing",
    "ranged", "thieving", "cooking",
    "prayer", "crafting", "firemaking",
    "magic", "fletching", "woodcutting",
    "runecraft", "slayer", "farming",
    "construction", "hunter", "sailing",
)

# Backgrounds the shuffle button picks from (app/static/img/model-viewer-bg/):
# decorative, same for every player. Index 0 is the first-visit default; order
# otherwise doesn't matter.
_MODEL_VIEWER_BACKGROUNDS = (
    "/static/img/model-viewer-bg/castle-courtyard.jpg",
    "/static/img/model-viewer-bg/garden-bridge.jpg",
    "/static/img/model-viewer-bg/scene-01.jpg",
    "/static/img/model-viewer-bg/scene-02.jpg",
    "/static/img/model-viewer-bg/scene-03.jpg",
    "/static/img/model-viewer-bg/scene-04.jpg",
    "/static/img/model-viewer-bg/scene-05.jpg",
    "/static/img/model-viewer-bg/scene-06.jpg",
    "/static/img/model-viewer-bg/scene-07.jpg",
    "/static/img/model-viewer-bg/scene-08.jpg",
    "/static/img/model-viewer-bg/scene-09.jpg",
    "/static/img/model-viewer-bg/scene-10.jpg",
    "/static/img/model-viewer-bg/scene-11.jpg",
    "/static/img/model-viewer-bg/scene-12.jpg",
    "/static/img/model-viewer-bg/scene-13.jpg",
    "/static/img/model-viewer-bg/scene-14.jpg",
    "/static/img/model-viewer-bg/scene-15.jpg",
    "/static/img/model-viewer-bg/scene-16.jpg",
    "/static/img/model-viewer-bg/scene-17.jpg",
    "/static/img/model-viewer-bg/scene-18.jpg",
    "/static/img/model-viewer-bg/scene-19.jpg",
    "/static/img/model-viewer-bg/scene-20.jpg",
    "/static/img/model-viewer-bg/scene-21.jpg",
    "/static/img/model-viewer-bg/scene-22.jpg",
    "/static/img/model-viewer-bg/scene-23.jpg",
    "/static/img/model-viewer-bg/scene-24.jpg",
    "/static/img/model-viewer-bg/scene-25.jpg",
    "/static/img/model-viewer-bg/scene-26.jpg",
    "/static/img/model-viewer-bg/scene-27.jpg",
    "/static/img/model-viewer-bg/scene-28.jpg",
    "/static/img/model-viewer-bg/scene-29.jpg",
    "/static/img/model-viewer-bg/scene-30.jpg",
    "/static/img/model-viewer-bg/scene-31.jpg",
    "/static/img/model-viewer-bg/scene-32.jpg",
    "/static/img/model-viewer-bg/scene-33.jpg",
    "/static/img/model-viewer-bg/scene-34.jpg",
    "/static/img/model-viewer-bg/scene-35.jpg",
    "/static/img/model-viewer-bg/scene-36.jpg",
    "/static/img/model-viewer-bg/scene-37.jpg",
    "/static/img/model-viewer-bg/scene-38.jpg",
    "/static/img/model-viewer-bg/scene-39.jpg",
    "/static/img/model-viewer-bg/scene-40.jpg",
    "/static/img/model-viewer-bg/scene-41.jpg",
    "/static/img/model-viewer-bg/scene-42.jpg",
    "/static/img/model-viewer-bg/scene-43.jpg",
    "/static/img/model-viewer-bg/scene-44.jpg",
    "/static/img/model-viewer-bg/scene-45.jpg",
    "/static/img/model-viewer-bg/scene-46.jpg",
    "/static/img/model-viewer-bg/scene-47.jpg",
    "/static/img/model-viewer-bg/scene-48.jpg",
    "/static/img/model-viewer-bg/scene-49.jpg",
    "/static/img/model-viewer-bg/scene-50.jpg",
    "/static/img/model-viewer-bg/scene-51.jpg",
    "/static/img/model-viewer-bg/scene-52.jpg",
    "/static/img/model-viewer-bg/scene-53.jpg",
    "/static/img/model-viewer-bg/scene-54.jpg",
    "/static/img/model-viewer-bg/scene-55.jpg",
    "/static/img/model-viewer-bg/scene-56.jpg",
    "/static/img/model-viewer-bg/scene-57.jpg",
    "/static/img/model-viewer-bg/scene-58.jpg",
    "/static/img/model-viewer-bg/scene-59.jpg",
    "/static/img/model-viewer-bg/scene-60.jpg",
    "/static/img/model-viewer-bg/scene-61.jpg",
    "/static/img/model-viewer-bg/scene-62.jpg",
    "/static/img/model-viewer-bg/scene-63.jpg",
    "/static/img/model-viewer-bg/scene-64.jpg",
    "/static/img/model-viewer-bg/scene-65.jpg",
    "/static/img/model-viewer-bg/scene-66.jpg",
    "/static/img/model-viewer-bg/scene-67.jpg",
    "/static/img/model-viewer-bg/scene-68.jpg",
    "/static/img/model-viewer-bg/scene-69.jpg",
    "/static/img/model-viewer-bg/scene-70.jpg",
    "/static/img/model-viewer-bg/scene-71.jpg",
    "/static/img/model-viewer-bg/scene-72.jpg",
    "/static/img/model-viewer-bg/scene-73.jpg",
    "/static/img/model-viewer-bg/scene-74.jpg",
    "/static/img/model-viewer-bg/scene-75.jpg",
)

_MODEL_VIEWER_HEAD = read_asset("model_viewer_head.html", indent=0)


def _character_overview_panel_markup(preview: bool = False, public_code: Optional[str] = None, public_character_name: Optional[str] = None) -> Tuple[str, str, str]:
    """Character Overview's real body/script, split out so the landing preview
    (render_landing_character_overview_preview) can reuse it verbatim.
    render_character_overview is this plus a _shell(...) call.
    
    preview=True (landing preview only) renders the same six sections; only
    two extra_head _MODEL_VIEWER_HEAD substitutions differ (background storage
    key and model-fetch URL), so the viewer opens on the default courtyard
    with the frozen demo model.
    
    public_code (render_public_character_overview only, never with preview)
    points those substitutions at another account's live model: GET
    /api/public/<code>/model and a per-code background key
    (myscape.modelViewerBgIndex.public.<code>). The owner-only settings card
    (public_profile_settings_btn) is omitted here and in preview.
    
    public_character_name (only with public_code) replaces the <h2> with the
    visited character's name; it is escape()'d like other player-controlled
    strings.
    
    Summary row (.co-summary-row): eight icon+stat pairs (_SUMMARY_STATS), alt
    text as hover tooltip (accountType excepted, see _ACCOUNT_TYPE_INFO).
    Values start as em dashes and are filled from
    /api/character-overview/summary. Combat level is rounded and total level
    has no thousands separator, unlike formatInt.
    
    Skills card (.skills-card in .co-left-col): 3x8 grid of .skill-cell in
    _SKILL_GRID_ORDER, each level a fixed 3ch wide. Shows VIRTUAL levels
    (levelForXp; xp table duplicated from Mindmaps), so maxed reads 126. Icons
    are app/static/skill-icons; data from GET /api/players/me/skills. Cells
    link to the wiki in a new tab; data-tooltip (.myscape-tooltip, _shell's
    shared_script) starts as the skill name and gains XP in setSkillTooltip.
    
    The collection log card (.clog-card) sits beside .co-left-col in
    .co-main-row; see character-overview.css.
    """
    stat_tiles = "\n      ".join(
        f"""<div class="co-stat">
        <img class="co-stat-icon" src="{escape(icon)}" alt="{escape(alt)}" data-tooltip="{escape(alt)}" {f'id="co-icon-{key}"' if key == "accountType" else ""} />
        <div class="co-stat-value" id="co-{key}">&mdash;</div>
      </div>"""
        for key, icon, alt in _SUMMARY_STATS
    )

    skill_cells = "\n      ".join(
        f"""<a class="skill-cell" id="skill-cell-{key}" data-tooltip="{key.capitalize()}" href="https://oldschool.runescape.wiki/w/{key.capitalize()}" target="_blank" rel="noopener">
        <img class="skill-cell-icon" src="/static/skill-icons/{key}.png" alt="{key.capitalize()}" />
        <span class="skill-cell-level" id="skill-{key}">&mdash;</span>
      </a>"""
        for key in _SKILL_GRID_ORDER
    )

    # Skills/Quests/Achievement Diaries/Combat Achievements (.co-quad-row)
    # render unconditionally, including in the landing preview, whose fetch shim
    # answers GET /api/character-overview/progress and /api/players/me/skills
    # (DEMO_PROGRESS / DEMO_SKILLS).
    quad_row_section = f"""
    <div class="co-quad-row" id="coQuadRow">
      <div class="skills-card" id="skillsCard">
        <div class="skills-grid">
          {skill_cells}
        </div>
      </div>

      <div class="quests-card" id="questsCard">
        <div class="quests-empty" id="questsEmpty">No quest data yet &mdash; open your quest list in-game with the myscape RuneLite plugin running, then refresh this page.</div>
        <div class="quests-list" id="questsList"></div>
      </div>

      <div class="diaries-card" id="diariesCard">
        <div class="diaries-list" id="diariesList"></div>
      </div>

      <div class="ca-card" id="caCard">
        <div class="ca-list" id="caList"></div>
      </div>
    </div>"""

    # The "i" tooltip and shuffle-background buttons are omitted for public_code
    # visitors (kept in preview as marketing): the plugin hint doesn't apply to
    # them and shuffling only changes their local pick. Omitting the markup is
    # safe because the script guards `if (bgShuffleBtn)`; the "i" button needs
    # no guard since its data-tooltip is read by the shared hover listener.
    mv_info_btn = "" if public_code else '<button class="model-viewer-btn" id="mvInfoBtn" type="button" data-tooltip="Set your character model in the myscape\nplugin sidebar on RuneLite." aria-label="Set your character model in the myscape\nplugin sidebar on RuneLite."><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="11"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg></button>'
    mv_shuffle_btn = "" if public_code else '<button class="model-viewer-btn" id="mvBgShuffleBtn" type="button" data-tooltip="Shuffle background" aria-label="Shuffle background"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 3 21 3 21 8"></polyline><line x1="4" y1="20" x2="21" y2="3"></line><polyline points="21 16 21 21 16 21"></polyline><line x1="15" y1="15" x2="21" y2="21"></line><line x1="4" y1="4" x2="9" y2="9"></line></svg></button>'

    # Owner's settings cog, absent in preview and public_code modes. The script
    # guards on `if (publicProfileSettingsBtn)`. Looks like the Storages
    # Viewer's .pm-settings-btn (see .co-settings-btn in character-overview.css)
    # and is a cog because it is opened rarely. The private/public card is
    # appended to this same wrap span below.
    public_profile_settings_btn = "" if (preview or public_code) else (
        ' <span class="co-settings-wrap">'
        '<button type="button" class="co-settings-btn" id="publicProfileSettingsBtn" aria-label="Public profile settings" data-tooltip="Public profile settings">'
        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M8.65 6.20 L9.54 2.82 L14.46 2.82 L15.35 6.20 L18.72 5.28 L21.18 9.54 L18.70 12.00 L21.18 14.46 L18.72 18.72 L15.35 17.80 L14.46 21.18 L9.54 21.18 L8.65 17.80 L5.28 18.72 L2.82 14.46 L5.30 12.00 L2.82 9.54 L5.28 5.28 Z"></path>'
        '<circle cx="12" cy="12" r="3.1"></circle>'
        '</svg></button>'
    )

    # Public visitors see the character's name instead of "Character Overview".
    page_heading = escape(public_character_name) if public_character_name else "Character Overview"

    # Floats under the cog (position: absolute, see .public-profile-card in
    # character-overview.css) as a sibling of publicProfileSettingsBtn in
    # .co-settings-wrap. PRIVATE/PUBLIC segmented control (markup duplicated
    # from Mindmaps' .mm-segment-group), a readonly link field and two buttons.
    if not (preview or public_code):
        public_profile_settings_btn += (
            '<div class="public-profile-card" id="publicProfileCard" hidden>'
            '<div class="public-profile-seg-group">'
            '<button type="button" class="public-profile-seg-btn active" id="publicProfileSegPrivate" data-segment-value="private" data-tooltip="Makes your profile invisible to everyone\n(except those on your friends list)" data-tooltip-wide>Private</button>'
            '<button type="button" class="public-profile-seg-btn" id="publicProfileSegPublic" data-segment-value="public" data-tooltip="Makes your profile visible\nto anyone with your URL">Public</button>'
            '</div>'
            '<button type="button" class="public-profile-link-btn public-profile-link-display" id="publicProfileLinkBtn" disabled></button>'
            '<button class="public-profile-link-btn" id="publicProfileRegenerateBtn" type="button" data-tooltip="Generating a new link will render your old link\nobsolete. You can do this once every 24 hours.">Generate new link</button>'
            '</div>'
            '</span>'
        )

    body = f"""
    <h2 class="page-title">{page_heading}{public_profile_settings_btn}</h2>

    <div class="co-summary-row" id="coSummaryRow">
      {stat_tiles}
    </div>

    <div class="co-main-row">
      <div class="co-left-col">
        <div class="model-viewer-card" id="modelViewerCard">
          <div class="model-viewer-canvas-wrap" id="modelViewerCanvasWrap">
            <div class="model-viewer-bg" id="modelViewerBg"></div>
            <canvas id="modelViewerCanvas"></canvas>
            <div class="model-viewer-controls" id="modelViewerControls">
              {mv_info_btn}
              {mv_shuffle_btn}
              <button class="model-viewer-btn" id="mvPlayPauseBtn" type="button" data-tooltip="Pause rotation" aria-label="Pause rotation"><svg id="mvPlayIcon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none" hidden><polygon points="6 3 20 12 6 21 6 3"></polygon></svg><svg id="mvPauseIcon" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg></button>
              <button class="model-viewer-btn" id="mvResetBtn" type="button" data-tooltip="Reset rotation" aria-label="Reset rotation"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg></button>
            </div>
          </div>
          <div class="model-viewer-empty" id="modelViewerEmpty">No 3D model captured yet &mdash; use the &ldquo;Export 3D model&rdquo; button in the myscape RuneLite plugin&rsquo;s sidebar, then refresh this page.</div>
        </div>
      </div>

      <div class="clog-card" id="clogCard">
        <div class="clog-empty" id="clogEmpty">No collection log data yet &mdash; open your collection log in-game with the myscape RuneLite plugin running, then refresh this page.</div>
        <div class="clog-body" id="clogBody">
          <div class="clog-toolbar">
            <div class="clog-tabs-wrap" id="clogTabsWrap">
              <div class="clog-tabs" id="clogTabs"></div>
              <span class="clog-tabs-arrow clog-tabs-arrow--left" aria-hidden="true"></span>
              <span class="clog-tabs-arrow clog-tabs-arrow--right" aria-hidden="true"></span>
            </div>
            <button class="clog-sync-btn" id="clogSyncBtn" type="button" data-tooltip="Refresh kill counts from official hiscores"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg></button>
          </div>
          <div class="clog-panes">
            <div class="clog-pages" id="clogPages"></div>
            <div class="clog-items-col" id="clogItemsCol">
              <div class="clog-items-header" id="clogItemsHeader"></div>
              <div class="clog-items" id="clogItems"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
    {quad_row_section}
    """

    script = read_asset("character_overview.js", indent=4).replace("__ACCOUNT_TYPE_INFO_JSON__", json.dumps(_ACCOUNT_TYPE_INFO))

    extra_head = (
        f'<link rel="stylesheet" href="/static/css/character-overview.css?v={_CHARACTER_OVERVIEW_CSS_VERSION}" />'
        + _MODEL_VIEWER_HEAD.replace(
            "__MODEL_VIEWER_BACKGROUNDS_JSON__", json.dumps(_MODEL_VIEWER_BACKGROUNDS)
        ).replace(
            "__MODEL_VIEWER_BG_STORAGE_KEY_JSON__",
            json.dumps(
                None if preview
                else f"myscape.modelViewerBgIndex.public.{public_code}" if public_code
                else "myscape.modelViewerBgIndex"
            ),
        ).replace(
            "__MODEL_VIEWER_MODEL_URL_JSON__",
            json.dumps(
                "/static/img/landing-character-overview-demo-model.glb" if preview
                else f"/api/public/{public_code}/model" if public_code
                else "/api/character-overview/model"
            ),
        )
    )
    return extra_head, body, script


def render_character_overview(player: PlayerView) -> str:
    """The real, authenticated Character Overview page:
    _character_overview_panel_markup's default output in the page shell. The
    landing preview (render_landing_character_overview_preview) and public
    view (render_public_character_overview) reuse the same body/script.
    """
    extra_head, body, script = _character_overview_panel_markup()
    return _shell(
        title="Character Overview — myscape",
        player=player,
        body=body,
        extra_head=extra_head,
        extra_script=script,
    )


def render_public_character_overview(game_account: "GameAccount", viewer: Optional[PlayerView]) -> str:
    """myscape.io/c/<code>: a visitor's view of someone else's public Character
    Overview. public_character_overview_page in app/main.py resolves the code
    and 404s if missing/private; viewer is whoever is signed in, used only for
    nav state.
    
    Reuses _character_overview_panel_markup(public_code=...) with a wrapper
    fetch shim that calls the code-scoped endpoints (GET
    /api/public/<code>/summary|progress|skills|collection-log in app/main.py)
    instead of the "me" endpoints. `fetch` is shadowed only inside this IIFE;
    window.fetch is untouched (see _MODEL_VIEWER_HEAD).
    
    accountType rides in the public summary response (low exposure).
    #clogSyncBtn gets the same hoverable-but-inert cloneNode+replaceWith
    treatment as the landing preview.
    """
    code = game_account.public_code
    display_name = game_account.runescape_name or "This player"
    extra_head, body, script = _character_overview_panel_markup(
        public_code=code, public_character_name=display_name
    )

    wrapper_script = f"""
    (function () {{
      var PUBLIC_CODE = {json.dumps(code)};

      // fetch shim: forwards to the real, public endpoints
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function fail() {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{}}); }} }}); }}

        if (url === '/api/character-overview/summary' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/summary').then(function (r) {{
            // Hands the owner's synced model-viewer background
            // (modelViewerBackgroundIndex in this response, see app/main.py) to
            // the 3D viewer, since a visitor has no shuffle history of their own
            // (see myscapeApplyModelViewerBackground in _MODEL_VIEWER_HEAD).
            // r.clone() because the reused script still reads this body and a
            // Response body can be consumed once.
            if (r.ok) {{
              r.clone().json().then(function (data) {{
                // Stashed on window whether or not the bridge function exists
                // yet: this fetch can resolve before the deferred module script
                // runs (see the handshake next to
                // window.myscapeApplyModelViewerBackground in
                // _MODEL_VIEWER_HEAD).
                window.__myscapePendingModelViewerBg = data.modelViewerBackgroundIndex;
                if (window.myscapeApplyModelViewerBackground) {{
                  window.myscapeApplyModelViewerBackground(data.modelViewerBackgroundIndex);
                }}
              }}).catch(function () {{}});
            }}
            return r;
          }});
        }}
        if (url === '/api/character-overview/progress' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/progress');
        }}
        if (url === '/api/players/me/skills' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/skills');
        }}
        if (url === '/api/players/me/collection-log' && method === 'GET') {{
          return window.fetch('/api/public/' + PUBLIC_CODE + '/collection-log');
        }}
        // #clogSyncBtn's click listener would fire this; unreachable in practice
        // (see the cloneNode+replaceWith strip below), answered with a graceful
        // failure anyway.
        if (url === '/api/players/me/hiscores/sync' && method === 'POST') {{
          return fail();
        }}
        // Anything else the reused script could call beyond the cases above.
        return fail();
      }};

      {script}

      var clogSyncBtn = document.getElementById('clogSyncBtn');
      if (clogSyncBtn) {{
        clogSyncBtn.replaceWith(clogSyncBtn.cloneNode(true));
      }}

      // friend-request button, next to the character's name. Uses the real
      // window.fetch on purpose (the local `fetch` answers only the Character
      // Overview endpoints).
      (function () {{
        var title = document.querySelector('h2.page-title');
        if (!title) return;
        var wrap = document.createElement('span');
        wrap.className = 'co-friend-wrap';
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'co-friend-btn';
        btn.id = 'friendRequestBtn';
        btn.hidden = true;
        wrap.appendChild(btn);
        title.appendChild(document.createTextNode(' '));
        title.appendChild(wrap);

        var ICON_ADD = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M19 8v6"></path><path d="M22 11h-6"></path></svg>';
        var ICON_DONE = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M16 11l2 2 4-4"></path></svg>';

        var state = 'none';
        var restoreTimer = null;
        function setState(next) {{
          state = next;
          btn.classList.remove('co-friend-btn--done');
          btn.disabled = false;
          if (next === 'self' || next === 'own') {{ btn.hidden = true; return; }}
          btn.hidden = false;
          var tip;
          if (next === 'friends') {{
            btn.innerHTML = ICON_DONE; tip = 'Friends';
            btn.classList.add('co-friend-btn--done'); btn.disabled = true;
          }} else if (next === 'pending_out') {{
            btn.innerHTML = ICON_DONE; tip = 'Friend request sent';
            btn.classList.add('co-friend-btn--done'); btn.disabled = true;
          }} else if (next === 'pending_in') {{
            btn.innerHTML = ICON_ADD; tip = 'Accept friend request';
          }} else if (next === 'anonymous') {{
            btn.innerHTML = ICON_ADD; tip = 'Log in to send a friend request';
          }} else {{
            btn.innerHTML = ICON_ADD; tip = 'Send friend request';
          }}
          btn.setAttribute('data-tooltip', tip);
          btn.setAttribute('aria-label', tip);
        }}

        window.fetch('/api/friends/status/' + encodeURIComponent(PUBLIC_CODE))
          .then(function (r) {{ return r.ok ? r.json() : null; }})
          .then(function (d) {{ if (d && d.state) setState(d.state); }})
          .catch(function () {{}});

        btn.addEventListener('click', function () {{
          if (state === 'anonymous') {{ window.location.href = '/login'; return; }}
          if (state !== 'none' && state !== 'pending_in') return;
          btn.disabled = true;
          window.fetch('/api/friends/requests', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ code: PUBLIC_CODE }}),
          }}).then(function (r) {{
            return r.json().catch(function () {{ return {{}}; }}).then(function (d) {{ return {{ ok: r.ok, data: d }}; }});
          }}).then(function (res) {{
            if (res.ok) {{
              if (window.myscapePollFriendNotifications) window.myscapePollFriendNotifications();
              setState(res.data.status === 'accepted' ? 'friends' : 'pending_out');
              return;
            }}
            var msg = (res.data && typeof res.data.detail === 'string') ? res.data.detail : 'Could not send that request.';
            btn.disabled = false;
            var previous = btn.getAttribute('data-tooltip');
            btn.setAttribute('data-tooltip', msg);
            clearTimeout(restoreTimer);
            restoreTimer = setTimeout(function () {{ btn.setAttribute('data-tooltip', previous); }}, 3500);
          }}).catch(function () {{ btn.disabled = false; }});
        }});
      }})();
    }})();
    """

    return _shell(
        title=f"{display_name} — myscape",
        player=viewer,
        body=body,
        extra_head=extra_head,
        extra_script=wrapper_script,
        meta_description=(
            f"{display_name}'s public myscape page — complete with their "
            "collection log data, skill levels, quest completions, "
            "achievement diary tiers, and combat task tiers."
        ),
    )


def render_landing_character_overview_preview() -> Optional[Tuple[str, str, str]]:
    """Landing page's interactive Character Overview preview: reuses
    _character_overview_panel_markup(preview=True) unmodified with a demo
    wrapper script. Backed by app/data/landing_character_overview_demo.json
    (real summary, progress and collection log snapshot; see
    _get_landing_character_overview_demo_data) plus a static .glb model.
    Returns (extra_head, body, script) for render_landing, or None if the
    snapshot is missing. First preview on the page, ahead of Loot Tracker.
    
    All six sections work like the real page; background shuffle works but
    never persists (see __MODEL_VIEWER_BG_STORAGE_KEY_JSON__). The container
    uses the usual fixed-height/clipped/feathered treatment
    (.landing-character-overview-preview in character-overview.css), so extra
    cards are reached by touch drag/keyboard. #clogSyncBtn stays visible and
    hoverable but inert (cloneNode+replaceWith strip, as for Loot Tracker's
    range button).
    
    1. A scoped `fetch` shim answers GET /api/character-overview/summary,
    /api/character-overview/progress, /api/players/me/skills and
    /api/players/me/collection-log from the snapshot, and fails the
    hiscores-sync POST gracefully. The 3D model bypasses the shim
    (__MODEL_VIEWER_MODEL_URL_JSON__ points at a static asset).
    2. No polling interval: each endpoint is fetched once on load.
    """
    demo = _get_landing_character_overview_demo_data()
    if demo is None:
        return None
    extra_head, body, script = _character_overview_panel_markup(preview=True)

    # Hero row: tagline wrap first, character second so the character lands on
    # the right; same flex/bottom-align as other previews (see
    # .loot-preview-hero in loot-tracker.css). The reused body's <h2> is hidden
    # via .landing-character-overview-preview .page-title.
    hero_markup = """
    <div class="co-preview-hero">
      <div class="co-preview-tagline-wrap">
        <p class="co-preview-tagline">
          <span class="co-preview-tagline-gold">CHARACTER OVERVIEWS</span> <span class="co-preview-tagline-white">that you can share with your friends.</span>
        </p>
      </div>
      <picture class="co-preview-char">
        <source srcset="/static/img/landing-character-overview-preview-char.webp" type="image/webp">
        <img src="/static/img/landing-character-overview-preview-char.png" alt="" />
      </picture>
    </div>
    """
    body = hero_markup + body

    summary_json = json.dumps(demo.get("summary") or {})
    progress_json = json.dumps(demo.get("progress") or {})
    skills_json = json.dumps(demo.get("skills") or {})
    collection_log_json = json.dumps(demo.get("collectionLog") or {})
    wrapper_script = f"""
    (function () {{
      // The captured snapshot (see _get_landing_character_overview_demo_data for
      // the sources). Static, since nothing in this preview mutates it.
      var DEMO_SUMMARY = {summary_json};
      var DEMO_PROGRESS = {progress_json};
      var DEMO_SKILLS = {skills_json};
      var DEMO_COLLECTION_LOG = {collection_log_json};

      // fetch shim
      var fetch = function (url, options) {{
        var opts = options || {{}};
        var method = (opts.method || 'GET').toUpperCase();
        function ok(data) {{ return Promise.resolve({{ ok: true, json: function () {{ return Promise.resolve(data); }} }}); }}
        function fail() {{ return Promise.resolve({{ ok: false, json: function () {{ return Promise.resolve({{}}); }} }}); }}

        if (url === '/api/character-overview/summary' && method === 'GET') {{
          return ok(DEMO_SUMMARY);
        }}
        if (url === '/api/character-overview/progress' && method === 'GET') {{
          return ok(DEMO_PROGRESS);
        }}
        if (url === '/api/players/me/skills' && method === 'GET') {{
          return ok(DEMO_SKILLS);
        }}
        if (url === '/api/players/me/collection-log' && method === 'GET') {{
          return ok(DEMO_COLLECTION_LOG);
        }}
        // Hiscores-sync POST from #clogSyncBtn's click listener; unreachable in
        // practice (see the cloneNode+replaceWith strip below), answered
        // gracefully anyway.
        if (url === '/api/players/me/hiscores/sync' && method === 'POST') {{
          return fail();
        }}
        // Fallback: a harmless failure for anything unexpected.
        return fail();
      }};

      {script}

      // Neutralizes the collection log's hiscores refresh button. Runs after the
      // reused script has wired its click listener, so the node is replaced
      // outright (cloneNode(true) copies markup but not listeners), as for Loot
      // Tracker's range button (render_landing_loot_preview). The button keeps
      // its hover styling and tooltip but does nothing on click.
      var clogSyncBtn = document.getElementById('clogSyncBtn');
      if (clogSyncBtn) {{
        clogSyncBtn.replaceWith(clogSyncBtn.cloneNode(true));
      }}

      // accountType ("MAIN", summary.accountType in
      // app/data/landing_character_overview_demo.json) flows through the summary
      // shim above like every other stat; no override needed.
    }})();
    """
    return extra_head, body, wrapper_script
