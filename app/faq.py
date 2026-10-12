"""The Help & Support page's FAQ, loaded from app/data/faq.json.

Each entry is {id, category, question, answer, tags}. `answer` is plain text
with links written [label](url); `tags` are extra search keywords (synonyms,
misspellings, feature names) used by the search script in render_help_support
(app/pages.py).

To add or edit a question, edit app/data/faq.json: append an object with the
next id. Nothing else needs to change.
"""
import json
import os
import re
from functools import lru_cache
from html import escape

_FAQ_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "faq.json")

# [label](https://...) or [label](/path) is the only supported markup;
# everything else is escaped.
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)")
_OWN_SITE = "https://myscape.io"


def answer_to_html(text: str) -> str:
    """Escapes `text` and turns [label](url) into <a> tags. Links to myscape.io
    itself stay in the same tab (as site-relative paths); others open in a new
    one.
    """
    out = []
    pos = 0
    for match in _LINK_RE.finditer(text):
        out.append(escape(text[pos:match.start()]))
        label, url = match.group(1), match.group(2)
        if url.startswith(_OWN_SITE + "/") or url == _OWN_SITE:
            url = url[len(_OWN_SITE):] or "/"
            attrs = ""
        elif url.startswith("/"):
            attrs = ""
        else:
            attrs = ' target="_blank" rel="noopener noreferrer"'
        out.append(f'<a href="{escape(url, quote=True)}"{attrs}>{escape(label)}</a>')
        pos = match.end()
    out.append(escape(text[pos:]))
    return "".join(out)


@lru_cache(maxsize=1)
def get_faq_items() -> list:
    with open(_FAQ_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    items = []
    for entry in raw:
        items.append(
            {
                "id": entry["id"],
                "category": entry["category"],
                "question": entry["question"],
                "answer": entry["answer"],
                "answerHtml": answer_to_html(entry["answer"]),
                "tags": list(entry.get("tags", [])),
            }
        )
    return items
