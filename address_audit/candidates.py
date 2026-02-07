from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple

from .models import AddressRecord, ParsedAddress
from .utils import offset_latlon
from .base_data import build_reverse_alias_map

def _key(s: str) -> str:
    return "".join((s or "").lower().split())

class CandidateGenerator:
    """负责“候选召回”，即在消歧前为每条地址挑出少量可能的同实体记录，减少后续评分/裁决的计算量。"""
    def __init__(self, grid_precision: int, aoi_alias_map: Dict[str, List[str]], road_alias_map: Dict[str, List[str]]):
        self.grid_precision = grid_precision
        # 构建 AOI/道路“别名->主名”反向索引，便于后续统一名称
        self.aoi_rev = build_reverse_alias_map(aoi_alias_map)
        self.road_rev = build_reverse_alias_map(road_alias_map)

    def canonical_aoi(self, aoi: Optional[str]) -> Optional[str]:
        """把解析出的 AOI 名字映射到主名，减少别名差异"""
        if not aoi:
            return None
        return self.aoi_rev.get(_key(aoi), aoi)

    def canonical_road(self, road: Optional[str]) -> Optional[str]:
        """道路同理，去除大小写/空格等差异"""
        if not road:
            return None
        return self.road_rev.get(_key(road), road)

    def geo_bucket(self, lat: Optional[float], lon: Optional[float]) -> Optional[str]:
        if lat is None or lon is None:
            return None
        # 将经纬度按精度取整，形成 geo bucket（地理网格 ID）
        return f"{round(lat, self.grid_precision)}_{round(lon, self.grid_precision)}"

    def geo_neighbors(self, bucket: str) -> List[str]:
        try:
            a, b = bucket.split("_")
            lat = float(a); lon = float(b)
        except Exception:
            return [bucket]
        step = 10 ** (-self.grid_precision)
        out = []
        for dlat in (-step, 0.0, step):
            for dlon in (-step, 0.0, step):
                out.append(f"{round(lat + dlat, self.grid_precision)}_{round(lon + dlon, self.grid_precision)}")
        return out

    def build_indexes(self, rows: List[Tuple[AddressRecord, ParsedAddress]]) -> Dict[str, Dict[str, List[str]]]:
        # 基于多种字段构建倒排索引，用于快速召回候选；得到【蜀山区】→[rid1, rid2,...]等映射
        idx: Dict[str, Dict[str, List[str]]] = {"district": {}, "aoi": {}, "building": {}, "road": {}, "geo": {}}
        for rec, p in rows:
            rid = rec.rid
            if p.district:
                idx["district"].setdefault(p.district, []).append(rid)
            if p.aoi:
                canon = self.canonical_aoi(p.aoi)
                idx["aoi"].setdefault(_key(canon), []).append(rid)
            if p.building:
                idx["building"].setdefault(p.building.upper(), []).append(rid)
            if p.road:
                canon_r = self.canonical_road(p.road)
                idx["road"].setdefault(_key(canon_r), []).append(rid)
            g = self.geo_bucket(rec.lat, rec.lon)
            if g:
                idx["geo"].setdefault(g, []).append(rid)
        return idx

    def relative_anchor_bucket(self, anchor_lat: float, anchor_lon: float,
                               direction: Optional[str], distance_m: Optional[int]) -> str:
        """把模糊地理描述（如“东南方向100米”）转换为具体的地理网格 ID"""
        if direction and distance_m:
            lat2, lon2 = offset_latlon(anchor_lat, anchor_lon, direction, float(distance_m))
        else:
            lat2, lon2 = anchor_lat, anchor_lon
        return self.geo_bucket(lat2, lon2) or ""

    def candidates_for(self,
                       rec: AddressRecord,
                       p: ParsedAddress,
                       indexes: Dict[str, Dict[str, List[str]]],
                       seen: Set[str],
                       anchor_bucket: Optional[str],
                       max_candidates: int) -> List[str]:
        """给定一条待匹配的地址记录，结合多种条件（行政区、AOI、楼栋、道路、地理网格、锚点附近范围）
        从之前建好的倒排索引里快速找出可能是同一实体的其它记录 rid。 
        解决了“从海量记录中高效召回少量可能同实体对象”的问题"""
        cand: Set[str] = set()

        if p.district and p.district in indexes["district"]:
            cand |= set(indexes["district"][p.district])

        if p.aoi:
            canon = self.canonical_aoi(p.aoi)
            cand |= set(indexes["aoi"].get(_key(canon), []))

        if p.building:
            cand |= set(indexes["building"].get(p.building.upper(), []))

        if p.road:
            canon_r = self.canonical_road(p.road)
            cand |= set(indexes["road"].get(_key(canon_r), []))

        g = self.geo_bucket(rec.lat, rec.lon)
        if g:
            for nb in self.geo_neighbors(g):
                cand |= set(indexes["geo"].get(nb, []))

        if anchor_bucket:
            for nb in self.geo_neighbors(anchor_bucket):
                cand |= set(indexes["geo"].get(nb, []))

        # 去掉自身，并且只保留“已解析完成”的记录（seen 是可匹配集合）
        cand.discard(rec.rid)
        cand &= set(seen)

        out = list(cand)
        return out[:max_candidates]
