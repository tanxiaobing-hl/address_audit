from __future__ import annotations
import json
from pathlib import Path

from address_audit.config import load_config
from address_audit.db import connect, init_db
from address_audit.evaluate import evaluate_current, grid_search

def main():
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    cfg = load_config(data_dir / "config.default.json")

    conn = connect(cfg.db_path)
    init_db(conn)

    cur = evaluate_current(conn, cfg)
    print("Current config metrics:", json.dumps(cur, ensure_ascii=False, indent=2))

    best = grid_search(conn, cfg)
    print("Best (grid search):", json.dumps(best, ensure_ascii=False, indent=2))

    best_cfg = {
        "db_path": cfg.db_path,
        "grid_precision": cfg.grid_precision,
        "candidate_max": cfg.candidate_max,
        "candidate_topn_for_llm": cfg.candidate_topn_for_llm,
        "weights": best["weights"],
        "thresholds": best["thresholds"],
        "parser": cfg.parser
    }
    out_path = data_dir / "config.best.json"
    out_path.write_text(json.dumps(best_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote:", str(out_path))

if __name__ == "__main__":
    main()
