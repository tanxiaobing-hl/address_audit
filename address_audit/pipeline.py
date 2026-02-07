from __future__ import annotations
import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import Config
from .models import AddressRecord, ParsedAddress, Conflict
from .db import (
    connect,
    init_db,
    list_records,
    upsert_parsed,
    insert_conflicts,
    insert_match_log,
    write_clusters,
    get_parsed,
    get_record,
    find_anchor_by_key,
)
from .base_data import load_alias_map
from .parser_llm import OpenAILLMParser
from .candidates import CandidateGenerator
from .scoring import Scorer
from .judge import Judge
from .conflicts import ConflictChecker
from .clustering import UnionFind


class AddressGovernancePipeline:
    """地址治理主流程：解析 -> 冲突检测 -> 候选召回 -> 评分裁决 -> 聚类输出。"""

    def __init__(self, cfg: Config, data_dir: str):
        self.cfg = cfg
        aoi_alias = load_alias_map(f"{data_dir}/alias_aoi.json")
        road_alias = load_alias_map(f"{data_dir}/alias_road.json")

        self.parser = OpenAILLMParser()
        self.cand_gen = CandidateGenerator(cfg.grid_precision, aoi_alias, road_alias)
        self.scorer = Scorer(cfg.weights, cfg.thresholds)
        self.judge = Judge(enable_llm=False)
        self.conflict_checker = ConflictChecker()

    def run(self) -> Dict[str, Any]:
        conn = connect(self.cfg.db_path)
        init_db(conn)

        rec_rows = list_records(conn)
        records: List[AddressRecord] = []
        parsed: Dict[str, ParsedAddress] = {}

        for row in rec_rows:
            rec = _row_to_record(row)
            records.append(rec)

            cached = get_parsed(conn, rec.rid)
            if cached:
                parsed[rec.rid] = _row_to_parsed(cached)
            else:
                p = self._alias_mapping_parsed_fields(self.parser.parse(rec.raw_address))
                upsert_parsed(conn, rec.rid, p)
                parsed[rec.rid] = p

        conflicts: List[Conflict] = []
        for rec in records:
            conflicts.extend(self.conflict_checker.check(rec, parsed[rec.rid]))
        if conflicts:
            insert_conflicts(conn, conflicts)

        pairs = [(rec, parsed[rec.rid]) for rec in records]
        indexes = self.cand_gen.build_indexes(pairs)

        uf = UnionFind([rec.rid for rec in records])
        seen: Set[str] = set()

        for rec in records:
            pr = parsed[rec.rid]
            anchor_bucket = self._resolve_anchor_bucket(conn, pr)

            cands = self.cand_gen.candidates_for(
                rec=rec,
                p=pr,
                indexes=indexes,
                seen=seen,
                anchor_bucket=anchor_bucket,
                max_candidates=self.cfg.candidate_max,
            )
            if not cands:
                seen.add(rec.rid)
                continue

            cand_pairs: List[Tuple[AddressRecord, ParsedAddress]] = []
            pre_scores = []
            for cid in cands:
                cr = _row_to_record(get_record(conn, cid))
                cp = parsed[cid]
                bonus = 0.0
                if anchor_bucket and cr.lat is not None and cr.lon is not None:
                    gb = self.cand_gen.geo_bucket(cr.lat, cr.lon)
                    if gb and gb in set(self.cand_gen.geo_neighbors(anchor_bucket)):
                        bonus = 1.0
                score = self.scorer.score_pair(rec, pr, cr, cp, relative_anchor_bonus=bonus)
                cand_pairs.append((cr, cp))
                pre_scores.append(score)

            ranked = sorted(
                list(zip(cand_pairs, pre_scores)),
                key=lambda x: x[1].score,
                reverse=True,
            )[: self.cfg.candidate_topn_for_llm]
            top_pairs = [item[0] for item in ranked]
            top_scores = [item[1] for item in ranked]

            final = self.judge.judge((rec, pr), top_pairs, top_scores)

            if final.decision == "SAME":
                best_rid = None
                if isinstance(final.evidence, dict):
                    best_rid = final.evidence.get("best_rid")
                if not best_rid and top_pairs:
                    best_rid = top_pairs[0][0].rid
                if best_rid:
                    uf.union(rec.rid, best_rid)

            insert_match_log(
                conn,
                rid_query=rec.rid,
                candidate_rids=[cr.rid for (cr, _) in top_pairs],
                pre_scores=[
                    {
                        "rid": cr.rid,
                        "decision": ms.decision,
                        "score": round(ms.score, 4),
                        "features": ms.feature_scores,
                    }
                    for (cr, _), ms in zip(top_pairs, top_scores)
                ],
                final={
                    "decision": final.decision,
                    "score": round(final.score, 4),
                    "evidence": final.evidence,
                },
            )

            seen.add(rec.rid)

        groups = uf.groups()
        clusters: Dict[str, List[str]] = {f"cluster_{root}": members for root, members in groups.items()}
        write_clusters(conn, clusters)

        return {
            "n_records": len(records),
            "n_conflicts": len(conflicts),
            "n_clusters_gt1": len([members for members in clusters.values() if len(members) > 1]),
        }

    def compare_addresses(self, addr1: str, addr2: str) -> Dict[str, Any]:
        """对两个地址文本执行与 run 相同的评分 + 裁决逻辑，返回判断结果。"""
        rec1 = AddressRecord(rid="addr_1", source="api", raw_address=addr1.strip())
        rec2 = AddressRecord(rid="addr_2", source="api", raw_address=addr2.strip())

        parsed1 = self._alias_mapping_parsed_fields(self.parser.parse(rec1.raw_address))
        parsed2 = self._alias_mapping_parsed_fields(self.parser.parse(rec2.raw_address))

        score = self.scorer.score_pair(rec1, parsed1, rec2, parsed2, relative_anchor_bonus=0.0)
        final = self.judge.judge((rec1, parsed1), [(rec2, parsed2)], [score])

        return {
            "decision": final.decision,
            "score": final.score,
            "feature_scores": final.feature_scores,
            "evidence": final.evidence,
            "addr1_parsed": asdict(parsed1),
            "addr2_parsed": asdict(parsed2),
        }

    def _alias_mapping_parsed_fields(self, parsed: ParsedAddress) -> ParsedAddress:
        if parsed.aoi:
            parsed.aoi = self.cand_gen.canonical_aoi(parsed.aoi)
        if parsed.road:
            parsed.road = self.cand_gen.canonical_road(parsed.road)
        return parsed

    def _resolve_anchor_bucket(self, conn, parsed: ParsedAddress) -> Optional[str]:
        if parsed.intersection and len(parsed.intersection) == 2:
            a, b = parsed.intersection
            if a and b:
                key = "|".join(sorted([a, b]))
                anchor = find_anchor_by_key(conn, key)
                if anchor and anchor.get("lat") is not None and anchor.get("lon") is not None:
                    return self.cand_gen.relative_anchor_bucket(
                        anchor["lat"],
                        anchor["lon"],
                        parsed.direction,
                        parsed.distance_m,
                    )

        if parsed.aoi:
            anchor = find_anchor_by_key(conn, parsed.aoi)
            if anchor and anchor.get("lat") is not None and anchor.get("lon") is not None:
                return self.cand_gen.relative_anchor_bucket(
                    anchor["lat"],
                    anchor["lon"],
                    parsed.direction,
                    parsed.distance_m,
                )
        return None


def _row_to_parsed(row: Dict[str, Any]) -> ParsedAddress:
    parsed = ParsedAddress(norm_text=row["norm_text"])
    for field in [
        "province",
        "city",
        "district",
        "street",
        "road",
        "road_no",
        "aoi",
        "building",
        "unit",
        "floor",
        "room",
        "shop_name",
        "direction",
    ]:
        setattr(parsed, field, row.get(field))
    if row.get("intersection_json"):
        try:
            inter = json.loads(row["intersection_json"])
            if isinstance(inter, list) and len(inter) == 2:
                parsed.intersection = (inter[0], inter[1])
        except Exception:
            pass
    parsed.distance_m = row.get("distance_m")
    return parsed


def _row_to_record(row: Dict[str, Any]) -> AddressRecord:
    extra = {}
    try:
        if row.get("extra_json"):
            extra = json.loads(row["extra_json"])
    except Exception:
        extra = {}
    return AddressRecord(
        rid=row["rid"],
        source=row["source"],
        raw_address=row["raw_address"],
        district_claim=row.get("district_claim"),
        grid_district=row.get("grid_district"),
        lat=row.get("lat"),
        lon=row.get("lon"),
        extra=extra,
    )
