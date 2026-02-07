from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

@dataclass
class Config:
    db_path: str
    grid_precision: int
    candidate_max: int
    candidate_topn_for_llm: int
    weights: Dict[str, float]
    thresholds: Dict[str, float]
    parser: Dict[str, Any]

def load_config(path: str | Path) -> Config:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    return Config(
        db_path=raw["db_path"],
        grid_precision=int(raw["grid_precision"]),
        candidate_max=int(raw["candidate_max"]),
        candidate_topn_for_llm=int(raw["candidate_topn_for_llm"]),
        weights=dict(raw["weights"]),
        thresholds=dict(raw["thresholds"]),
        parser=dict(raw["parser"]),
    )
