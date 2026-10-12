"""Loads the large page scripts kept as plain files in app/pages/assets/."""
import os
import textwrap
from functools import lru_cache
from typing import Optional

_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


@lru_cache(maxsize=None)
def read_asset(name: str, indent: int = 0, tail: Optional[int] = None) -> str:
    """The text of app/pages/assets/<name> as the page embeds it.

    The files are stored dedented so they read as ordinary .js/.html. This adds
    back what the embedding Python code had: a leading newline, every non-blank
    line indented by `indent` spaces, and `tail` spaces (default: `indent`) on
    the last line, where the closing quotes used to sit.
    """
    with open(os.path.join(_ASSET_DIR, name), encoding="utf-8", newline="") as f:
        text = f.read()
    return "\n" + textwrap.indent(text, " " * indent) + " " * (indent if tail is None else tail)
