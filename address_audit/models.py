from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

@dataclass
class AddressRecord:
    rid: str
    source: str
    raw_address: str
    district_claim: Optional[str] = None
    grid_district: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ParsedAddress:
    norm_text: str
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    street: Optional[str] = None
    road: Optional[str] = None
    road_no: Optional[str] = None
    aoi: Optional[str] = None
    building: Optional[str] = None
    unit: Optional[str] = None
    floor: Optional[str] = None
    room: Optional[str] = None
    shop_name: Optional[str] = None
    intersection: Optional[Tuple[str, str]] = None
    direction: Optional[str] = None
    distance_m: Optional[int] = None

@dataclass
class MatchResult:
    decision: str
    score: float
    feature_scores: Dict[str, float]
    evidence: Dict[str, Any]

@dataclass
class Conflict:
    rid: str
    conflict_type: str
    detail: str
