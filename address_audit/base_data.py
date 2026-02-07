from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

def load_alias_map(path: str | Path) -> Dict[str, List[str]]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))

def build_reverse_alias_map(canonical_to_aliases: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Return: alias -> canonical (all lower-case, no spaces)
    """
    rev: Dict[str, str] = {}
    for canon, aliases in canonical_to_aliases.items():
        canon_key = _key(canon)
        rev[canon_key] = canon
        for a in aliases:
            rev[_key(a)] = canon
    return rev

def _key(s: str) -> str:
    return "".join((s or "").lower().split())
