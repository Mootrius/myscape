"""The Help & Support page."""
import json
import os

from app.faq import get_faq_items
from app.pages.asset_loader import read_asset
from app.pages.player import PlayerView
from app.pages.shell import _shell

_HELP_SUPPORT_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "help-support.css"
)

try:
    _HELP_SUPPORT_CSS_VERSION = int(os.path.getmtime(_HELP_SUPPORT_CSS_PATH))
except OSError:
    _HELP_SUPPORT_CSS_VERSION = 0

# Help & Support's FAQ search. Plain (non-f-string) script so braces and regexes
# need no escaping; __FAQ_JSON__ is swapped for the entries (app/faq.py) in
# render_help_support.
#
# Ranking: typed words (minus filler) match each FAQ's question, tags and
# answer, question/tag hits counting double; a word matches on a shared stem or
# prefix, or (longer words) a one-letter typo. An FAQ must match every word,
# else the closest partial matches show, flagged as such.
_HELP_SUPPORT_SCRIPT = read_asset("help_support.js", indent=4, tail=0)

_HELP_SUPPORT_HEAD = f'<link rel="stylesheet" href="/static/css/help-support.css?v={_HELP_SUPPORT_CSS_VERSION}" />'

# FAQ search box, results and notes, shared by Help & Support and the landing
# page's "GOT QUESTIONS?" panel.
_HELP_SUPPORT_SEARCH_MARKUP = """
    <div class="hs-search-group">
      <input type="text" class="hs-search" id="hsSearch" placeholder="Search the FAQ" autocomplete="off" />
      <button type="button" class="hs-search-clear" id="hsSearchClear" style="display:none;">Clear</button>
    </div>
    <p class="hs-status" id="hsStatus"></p>
    <div class="hs-results" id="hsResults"></div>
    <p class="hs-note" id="hsNote"></p>
"""


def _help_support_script() -> str:
    """The FAQ search script with the FAQ entries embedded."""
    faq_json = json.dumps(get_faq_items(), ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return _HELP_SUPPORT_SCRIPT.replace("__FAQ_JSON__", faq_json)


def render_help_support(player: PlayerView) -> str:
    """The Help & Support page: a client-side search over the FAQ embedded in the
    page (app/faq.py, app/data/faq.json); see _HELP_SUPPORT_SCRIPT.
    """
    extra_head = _HELP_SUPPORT_HEAD
    script = _help_support_script()
    body = '<h2 class="page-title">Help &amp; Support</h2>' + _HELP_SUPPORT_SEARCH_MARKUP
    return _shell(
        title="Help & Support — myscape",
        player=player,
        body=body,
        extra_script=script,
        extra_head=extra_head,
    )
