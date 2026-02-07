from __future__ import annotations
from typing import Dict, Optional

from .models import AddressRecord, ParsedAddress, MatchResult
from .utils import jaccard_sim, haversine_m, geo_score

class Scorer:
    def __init__(self, weights: Dict[str, float], thresholds: Dict[str, float]):
        self.w = weights
        self.th = thresholds

    def score_pair(self,
                   r1: AddressRecord, p1: ParsedAddress,
                   r2: AddressRecord, p2: ParsedAddress,
                   relative_anchor_bonus: float = 0.0) -> MatchResult:
        fs: Dict[str, float] = {}
        fs["district"] = 1.0 if (p1.district and p2.district and p1.district == p2.district) else 0.0
        fs["aoi"] = max(jaccard_sim(p1.aoi, p2.aoi, 2), jaccard_sim(p1.aoi, p2.aoi, 3)) if (p1.aoi and p2.aoi) else 0.0
        fs["building"] = 1.0 if (p1.building and p2.building and p1.building.upper() == p2.building.upper()) else 0.0
        fs["floor"] = 1.0 if (p1.floor and p2.floor and p1.floor == p2.floor) else 0.0
        fs["room"] = 1.0 if (p1.room and p2.room and p1.room == p2.room) else 0.0

        road_sim = 0.0
        if p1.road and p2.road:
            road_sim = max(road_sim, jaccard_sim(p1.road, p2.road, 2))
        if p1.road_no and p2.road_no and p1.road_no == p2.road_no:
            road_sim = max(road_sim, 1.0)
        fs["road"] = road_sim

        fs["shop"] = max(jaccard_sim(p1.shop_name, p2.shop_name, 2), jaccard_sim(p1.shop_name, p2.shop_name, 3)) if (p1.shop_name and p2.shop_name) else 0.0

        dist = None
        if r1.lat is not None and r1.lon is not None and r2.lat is not None and r2.lon is not None:
            dist = haversine_m(r1.lat, r1.lon, r2.lat, r2.lon)
        fs["geo"] = geo_score(dist)

        fs["relative_anchor"] = float(relative_anchor_bonus)

        denom = sum(max(0.0, float(v)) for v in self.w.values()) or 1.0
        num = 0.0
        for k, w in self.w.items():
            num += float(w) * float(fs.get(k, 0.0))
        score = num / denom

        # 阈值决策：根据预设的阈值把连续的相似度分数映射为离散的决策类别（SAME / UNSURE / DIFFERENT）
        # 可根据需要调整
        same_th = float(self.th.get("same", 0.78))
        unsure_th = float(self.th.get("unsure", 0.55))
        if score >= same_th:
            decision = "SAME"
        elif score >= unsure_th:
            decision = "UNSURE"
        else:
            decision = "DIFFERENT"

        return MatchResult(decision=decision, score=score, feature_scores=fs, evidence={})
