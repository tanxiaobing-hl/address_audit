from __future__ import annotations
import math
import re
from typing import Optional, Set, Tuple, Any
from dataclasses import asdict, is_dataclass
import json


_CN_NUM = {
    "零": 0, "〇": 0,
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    "十": 10
}

def cn_to_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if len(s) == 1 and s in _CN_NUM:
        return _CN_NUM[s]
    if "十" in s:
        parts = s.split("十")
        if len(parts) != 2:
            return None
        left, right = parts[0], parts[1]
        tens = 1 if left == "" else _CN_NUM.get(left)
        ones = 0 if right == "" else _CN_NUM.get(right)
        if tens is None or ones is None:
            return None
        return tens * 10 + ones
    return None

def normalize_text(text: str) -> str:
    """清洗和标准化文本"""
    if text is None:
        return ""
    t = text.strip()  

    # 全角括号/方括号转半角
    t = t.replace("（", "(").replace("）", ")").replace("【", "[").replace("】", "]")

    # 移除括号及其内容
    t2 = re.sub(r"\([^)]*\)", " ", t)    
    t2 = re.sub(r"\[[^\]]*\]", " ", t2)

    # 压缩空白字符
    t2 = re.sub(r"\s+", " ", t2)  

    # 全角数字转半角数字
    t2 = t2.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

    return t2.lower().strip()

def char_ngram_set(s: str, n: int = 2) -> Set[str]:
    s = re.sub(r"\s+", "", s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i+n] for i in range(len(s) - n + 1)}

def jaccard_sim(a: str, b: str, n: int = 2) -> float:
    if not a or not b:
        return 0.0
    A, B = char_ngram_set(a, n), char_ngram_set(b, n)
    if not A or not B:
        return 0.0
    return len(A & B) / max(1, len(A | B))

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def geo_score(dist_m: Optional[float]) -> float:
    if dist_m is None:
        return 0.0
    if dist_m <= 30:
        return 1.0
    if dist_m <= 80:
        return 0.7
    if dist_m <= 200:
        return 0.4
    return 0.0

def direction_to_vector(direction: str) -> Tuple[float, float]:
    # 方向向量转换（direction_to_vector），将中文方位映射为笛卡尔坐标系单位向量。
    # 纬度：北正南负， 经度：东正西负
    d = (direction or "").strip()
    if d == "东": return (0.0, 1.0)
    if d == "西": return (0.0, -1.0)
    if d == "南": return (-1.0, 0.0)
    if d == "北": return (1.0, 0.0)
    if d == "东北": return (1.0, 1.0)
    if d == "西北": return (1.0, -1.0)
    if d == "东南": return (-1.0, 1.0)
    if d == "西南": return (-1.0, -1.0)
    return (0.0, 0.0)

def offset_latlon(lat: float, lon: float, direction: str, dist_m: float) -> Tuple[float, float]:
    # 经纬度偏移量计算（offset_latlon）， 采用球面近似模型（适用于<1km短距离）
    # 极简近似：1 deg lat ~ 111km, 1 deg lon ~ 111km*cos(lat)
    from math import cos, radians, sqrt
    dlat_u, dlon_u = direction_to_vector(direction)

    # 向量归一化（避免对角线距离膨胀）
    norm = sqrt(dlat_u*dlat_u + dlon_u*dlon_u) or 1.0
    dlat_u /= norm
    dlon_u /= norm

    # 1度纬度 ≈ 111 km（全球恒定）
    dlat = (dist_m * dlat_u) / 111000.0

    # 1度经度 ≈ 111 km × cos(纬度)（随纬度变化）
    dlon = (dist_m * dlon_u) / (111000.0 * max(0.2, cos(radians(lat))))

    return (lat + dlat, lon + dlon)

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, tuple):
            return list(obj)  # 将 tuple 转为 list
        return super().default(obj)