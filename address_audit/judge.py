from __future__ import annotations
from typing import List, Tuple

from .models import AddressRecord, ParsedAddress, MatchResult
from .utils import jaccard_sim, haversine_m, geo_score

class Judge:
    def __init__(self, enable_llm: bool = False):
        self.enable_llm = enable_llm

    def judge(self,
              query: Tuple[AddressRecord, ParsedAddress],
              candidates: List[Tuple[AddressRecord, ParsedAddress]],
              pre_scores: List[MatchResult]) -> MatchResult:
        (qr, qp) = query
        best = None
        best_idx = 0

        for i, ((cr, cp), ms) in enumerate(zip(candidates, pre_scores)):
            # 楼栋是否一致
            building_ok = qp.building and cp.building and qp.building.upper() == cp.building.upper()
            # 楼层是否一致
            floor_ok = qp.floor and cp.floor and qp.floor == cp.floor
            # 房间是否一致
            room_ok = qp.room and cp.room and qp.room == cp.room
            # 区域是否相似（Jaccard 相似度 >= 0.65）
            aoi_ok = qp.aoi and cp.aoi and jaccard_sim(qp.aoi, cp.aoi, 2) >= 0.65

            geo_ok = 0.0
            if qr.lat is not None and qr.lon is not None and cr.lat is not None and cr.lon is not None:
                geo_ok = geo_score(haversine_m(qr.lat, qr.lon, cr.lat, cr.lon))

            if building_ok and floor_ok and (room_ok or geo_ok >= 0.7 or aoi_ok):
                return MatchResult(
                    decision="SAME",
                    score=max(ms.score, 0.90),
                    feature_scores=ms.feature_scores,
                    evidence={"judge": "rule_strong_fields", "best_rid": cr.rid}
                )

            if best is None or ms.score > best.score:
                best = ms
                best_idx = i

        if best is None:
            return MatchResult("DIFFERENT", 0.0, {}, {"judge": "empty_candidates"})

        cr, _cp = candidates[best_idx]
        best.evidence = {"judge": "best_prescore", "best_rid": cr.rid}
        return best
