from __future__ import annotations
import json
from typing import Any, Dict

from .config import Config
from .db import list_pair_labels, get_record, get_parsed
from .pipeline import _row_to_record, _row_to_parsed
from .scoring import Scorer

def evaluate_current(conn, cfg: Config) -> Dict[str, Any]:
    labels = list_pair_labels(conn)
    scorer = Scorer(cfg.weights, cfg.thresholds)

    tp=fp=tn=fn=0
    for row in labels:
        rid1, rid2, y = row["rid1"], row["rid2"], int(row["label"])
        r1 = _row_to_record(get_record(conn, rid1))
        r2 = _row_to_record(get_record(conn, rid2))
        p1 = _row_to_parsed(get_parsed(conn, rid1))
        p2 = _row_to_parsed(get_parsed(conn, rid2))
        ms = scorer.score_pair(r1, p1, r2, p2, relative_anchor_bonus=0.0)
        pred = 1 if ms.decision == "SAME" else 0
        if pred==1 and y==1: tp+=1
        elif pred==1 and y==0: fp+=1
        elif pred==0 and y==0: tn+=1
        elif pred==0 and y==1: fn+=1

    prec = tp / (tp+fp) if (tp+fp) else 0.0
    rec  = tp / (tp+fn) if (tp+fn) else 0.0
    f1   = (2*prec*rec/(prec+rec)) if (prec+rec) else 0.0
    return {"tp":tp,"fp":fp,"tn":tn,"fn":fn,"precision":prec,"recall":rec,"f1":f1}

def grid_search(conn, cfg: Config) -> Dict[str, Any]:
    base_w = dict(cfg.weights)
    same_grid = [0.70, 0.74, 0.78, 0.82]
    unsure_grid = [0.50, 0.55, 0.60]
    w_scales = [
        {"geo": 1.0, "building": 1.0, "aoi": 1.0},
        {"geo": 1.2, "building": 1.0, "aoi": 1.0},
        {"geo": 1.0, "building": 1.2, "aoi": 1.0},
        {"geo": 1.0, "building": 1.0, "aoi": 1.2},
        {"geo": 1.2, "building": 1.1, "aoi": 1.1},
    ]

    best = {"f1": -1.0}
    for th_same in same_grid:
        for th_unsure in unsure_grid:
            if th_unsure >= th_same:
                continue
            for scale in w_scales:
                w = dict(base_w)
                for k, s in scale.items():
                    if k in w:
                        w[k] = float(w[k]) * float(s)

                cfg2 = Config(
                    db_path=cfg.db_path,
                    grid_precision=cfg.grid_precision,
                    candidate_max=cfg.candidate_max,
                    candidate_topn_for_llm=cfg.candidate_topn_for_llm,
                    weights=w,
                    thresholds={"same": th_same, "unsure": th_unsure},
                    parser=cfg.parser
                )
                metrics = evaluate_current(conn, cfg2)
                if metrics["f1"] > best["f1"]:
                    best = {"f1": metrics["f1"], "precision": metrics["precision"], "recall": metrics["recall"],
                            "tp": metrics["tp"], "fp": metrics["fp"], "tn": metrics["tn"], "fn": metrics["fn"],
                            "thresholds": cfg2.thresholds, "weights": cfg2.weights}
    return best
