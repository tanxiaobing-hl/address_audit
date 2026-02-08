from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .models import AddressRecord, ParsedAddress, Conflict

TABLE_SCHEMAS: Dict[str, List[str]] = {
    "address_records": ["rid", "source", "raw_address", "district_claim", "grid_district", "lat", "lon", "extra_json", "created_at"],
    "parsed_addresses": [
        "rid", "norm_text", "province", "city", "district", "street",
        "road", "road_no", "aoi", "building", "unit", "floor", "room",
        "shop_name", "intersection_json", "direction", "distance_m",
        "parsed_at"
    ],
    "roads": ["road_id", "name", "district", "aliases_json"],
    "pois": ["poi_id", "name", "poi_type", "district", "lat", "lon", "aliases_json"],
    "anchors": ["anchor_id", "anchor_type", "key_text", "district", "lat", "lon"],
    "conflicts": ["id", "rid", "conflict_type", "detail", "created_at"],
    "match_logs": ["id", "rid_query", "candidate_rids_json", "pre_scores_json", "final_json", "created_at"],
    "clusters": ["cluster_id", "rid"],
    "pair_labels": ["id", "rid1", "rid2", "label"],
}

def _now_str() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def _empty_table(name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=TABLE_SCHEMAS[name])

def _ensure_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    result = df.copy()
    for col in columns:
        if col not in result.columns:
            result[col] = None
    return result[columns]

def _clean_value(val: Any) -> Any:
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    return val

def _row_to_dict(row: pd.Series) -> Dict[str, Any]:
    return {k: _clean_value(v) for k, v in row.to_dict().items()}

def _next_pk(df: pd.DataFrame, column: str = "id") -> int:
    if df.empty or column not in df.columns:
        return 1
    max_val = pd.to_numeric(df[column], errors="coerce").max()
    if pd.isna(max_val):
        return 1
    return int(max_val) + 1

class ExcelConnection:
    """简单的 Excel “连接”对象，维护内存表缓存并提供保存方法。"""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tables: Dict[str, pd.DataFrame] = {
            name: _empty_table(name) for name in TABLE_SCHEMAS
        }
        if self.path.exists():
            xls = pd.read_excel(self.path, sheet_name=None)
            for name, cols in TABLE_SCHEMAS.items():
                if name in xls:
                    self.tables[name] = _ensure_columns(xls[name], cols)

    def save(self) -> None:
        with pd.ExcelWriter(self.path, engine="openpyxl") as writer:
            for name, df in self.tables.items():
                df.to_excel(writer, sheet_name=name, index=False)

def connect(db_path: str | Path) -> ExcelConnection:
    return ExcelConnection(db_path)

def init_db(conn: ExcelConnection) -> None:
    conn.save()

def _upsert_row(df: pd.DataFrame, row: Dict[str, Any], key_field: str) -> pd.DataFrame:
    mask = df[key_field] == row[key_field]
    if mask.any():
        idx = df.index[mask][0]
        for col in df.columns:
            df.at[idx, col] = row.get(col)
        return df
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)

def upsert_record(conn: ExcelConnection, r: AddressRecord) -> None:
    df = conn.tables["address_records"]
    row = {
        "rid": r.rid,
        "source": r.source,
        "raw_address": r.raw_address,
        "district_claim": r.district_claim,
        "grid_district": r.grid_district,
        "lat": r.lat,
        "lon": r.lon,
        "extra_json": json.dumps(r.extra, ensure_ascii=False),
        "created_at": _now_str()
    }
    mask = df["rid"] == r.rid
    if mask.any():
        row["created_at"] = _clean_value(df.loc[mask, "created_at"].iloc[0])
    df = _upsert_row(df, row, "rid")
    conn.tables["address_records"] = df
    conn.save()

def list_records(conn: ExcelConnection) -> List[Dict[str, Any]]:
    df = conn.tables["address_records"]
    if "created_at" in df.columns:
        df = df.sort_values(by="created_at", na_position="last")
    return [_row_to_dict(row) for _, row in df.iterrows()]

def get_record(conn: ExcelConnection, rid: str) -> Optional[Dict[str, Any]]:
    df = conn.tables["address_records"]
    match = df[df["rid"] == rid]
    if match.empty:
        return None
    return _row_to_dict(match.iloc[0])

def upsert_parsed(conn: ExcelConnection, rid: str, p: ParsedAddress) -> None:
    df = conn.tables["parsed_addresses"]
    row = {
        "rid": rid,
        "norm_text": p.norm_text,
        "province": p.province,
        "city": p.city,
        "district": p.district,
        "street": p.street,
        "road": p.road,
        "road_no": p.road_no,
        "aoi": p.aoi,
        "building": p.building,
        "unit": p.unit,
        "floor": p.floor,
        "room": p.room,
        "shop_name": p.shop_name,
        "intersection_json": json.dumps(p.intersection, ensure_ascii=False) if p.intersection else None,
        "direction": p.direction,
        "distance_m": p.distance_m,
        "parsed_at": _now_str()
    }
    df = _upsert_row(df, row, "rid")
    conn.tables["parsed_addresses"] = df
    conn.save()

def get_parsed(conn: ExcelConnection, rid: str) -> Optional[Dict[str, Any]]:
    df = conn.tables["parsed_addresses"]
    match = df[df["rid"] == rid]
    if match.empty:
        return None
    return _row_to_dict(match.iloc[0])


def clear_table(conn: ExcelConnection, table: str) -> None:
    if table not in TABLE_SCHEMAS:
        raise ValueError(f"Unknown table: {table}")
    conn.tables[table] = _empty_table(table)
    conn.save()

def insert_match_log(conn: ExcelConnection, rid_query: str, candidate_rids: List[str],
                     pre_scores: List[Dict[str, Any]], final: Dict[str, Any]) -> None:
    df = conn.tables["match_logs"]
    row = {
        "id": _next_pk(df),
        "rid_query": rid_query,
        "candidate_rids_json": json.dumps(candidate_rids, ensure_ascii=False),
        "pre_scores_json": json.dumps(pre_scores, ensure_ascii=False),
        "final_json": json.dumps(final, ensure_ascii=False),
        "created_at": _now_str()
    }
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    conn.tables["match_logs"] = df
    conn.save()

def write_clusters(conn: ExcelConnection, clusters: Dict[str, List[str]]) -> None:
    rows = []
    for cid, rids in clusters.items():
        for rid in rids:
            rows.append({"cluster_id": cid, "rid": rid})
    conn.tables["clusters"] = pd.DataFrame(rows, columns=TABLE_SCHEMAS["clusters"])
    conn.save()

def upsert_road(conn: ExcelConnection, road_id: str, name: str, district: str | None, aliases: List[str]) -> None:
    df = conn.tables["roads"]
    row = {
        "road_id": road_id,
        "name": name,
        "district": district,
        "aliases_json": json.dumps(aliases, ensure_ascii=False)
    }
    df = _upsert_row(df, row, "road_id")
    conn.tables["roads"] = df
    conn.save()

def upsert_poi(conn: ExcelConnection, poi_id: str, name: str, poi_type: str | None, district: str | None,
               lat: float, lon: float, aliases: List[str]) -> None:
    df = conn.tables["pois"]
    row = {
        "poi_id": poi_id,
        "name": name,
        "poi_type": poi_type,
        "district": district,
        "lat": lat,
        "lon": lon,
        "aliases_json": json.dumps(aliases, ensure_ascii=False)
    }
    df = _upsert_row(df, row, "poi_id")
    conn.tables["pois"] = df
    conn.save()

def upsert_anchor(conn: ExcelConnection, anchor_id: str, anchor_type: str | None, key_text: str,
                  district: str | None, lat: float, lon: float) -> None:
    df = conn.tables["anchors"]
    row = {
        "anchor_id": anchor_id,
        "anchor_type": anchor_type,
        "key_text": key_text,
        "district": district,
        "lat": lat,
        "lon": lon
    }
    df = _upsert_row(df, row, "anchor_id")
    conn.tables["anchors"] = df
    conn.save()

def find_anchor_by_key(conn: ExcelConnection, key_text: str) -> Optional[Dict[str, Any]]:
    df = conn.tables["anchors"]
    match = df[df["key_text"] == key_text]
    if match.empty:
        return None
    return _row_to_dict(match.iloc[0])

def insert_pair_labels(conn: ExcelConnection, labels: List[Tuple[str, str, int]]) -> None:
    if not labels:
        return
    df = conn.tables["pair_labels"]
    next_id = _next_pk(df)
    rows = []
    for rid1, rid2, label in labels:
        rows.append({"id": next_id, "rid1": rid1, "rid2": rid2, "label": int(label)})
        next_id += 1
    df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    conn.tables["pair_labels"] = df
    conn.save()

def list_pair_labels(conn: ExcelConnection) -> List[Dict[str, Any]]:
    df = conn.tables["pair_labels"]
    return [_row_to_dict(row) for _, row in df.iterrows()]
