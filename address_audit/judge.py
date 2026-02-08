from __future__ import annotations
import json
import logging
import os
import urllib.request
from dataclasses import asdict
from typing import List, Optional, Tuple

from .models import AddressRecord, ParsedAddress, MatchResult, Conflict
from .utils import jaccard_sim, haversine_m, geo_score


logger = logging.getLogger(__name__)


class ConflictChecker:
    """既用于单记录质量检查，也用于判定两条地址是否存在黑名单冲突。"""

    def check(self, rec: AddressRecord, parsed: ParsedAddress) -> List[Conflict]:
        conflicts: List[Conflict] = []
        if rec.grid_district and parsed.district and rec.grid_district != parsed.district:
            conflicts.append(
                Conflict(
                    rec.rid,
                    "GRID_DISTRICT_MISMATCH",
                    f"grid_district={rec.grid_district} vs parsed_district={parsed.district}",
                )
            )
        if rec.district_claim and parsed.district and rec.district_claim != parsed.district:
            conflicts.append(
                Conflict(
                    rec.rid,
                    "CLAIM_DISTRICT_MISMATCH",
                    f"district_claim={rec.district_claim} vs parsed_district={parsed.district}",
                )
            )
        return conflicts

    def pair_conflict_reason(
        self,
        query_rec: AddressRecord,
        query_parsed: ParsedAddress,
        cand_rec: AddressRecord,
        cand_parsed: ParsedAddress,
    ) -> Optional[str]:
        if query_rec.grid_district and cand_rec.grid_district and query_rec.grid_district != cand_rec.grid_district:
            return f"GRID_DISTRICT_CONFLICT: {query_rec.grid_district} vs {cand_rec.grid_district}"
        if query_rec.district_claim and cand_rec.district_claim and query_rec.district_claim != cand_rec.district_claim:
            return f"DISTRICT_CLAIM_CONFLICT: {query_rec.district_claim} vs {cand_rec.district_claim}"
        if (
            query_parsed.district
            and cand_parsed.district
            and query_parsed.district != cand_parsed.district
        ):
            return f"PARSED_DISTRICT_CONFLICT: {query_parsed.district} vs {cand_parsed.district}"
        return None


class Judge:
    def __init__(self) -> None:
        self.llm_base_url = os.getenv("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
        self.llm_model = os.getenv("OPENAI_MODEL", "qwen3-max")
        self.llm_api_key = os.getenv("OPENAI_API_KEY", "")
        self.blacklist_checker = ConflictChecker()

    def judge(
        self,
        query: Tuple[AddressRecord, ParsedAddress],
        candidates: List[Tuple[AddressRecord, ParsedAddress]],
        pre_scores: List[MatchResult],
        use_llm: bool = False,
    ) -> MatchResult:
        (qr, qp) = query
        best = None
        best_idx = 0
        last_conflict_reason: Optional[str] = None

        for i, ((cr, cp), ms) in enumerate(zip(candidates, pre_scores)):
            conflict_reason = self.blacklist_checker.pair_conflict_reason(qr, qp, cr, cp)
            if conflict_reason:
                logger.debug("Candidate %s rejected by blacklist: %s", cr.rid, conflict_reason)
                last_conflict_reason = conflict_reason
                continue

            building_ok = qp.building and cp.building and qp.building.upper() == cp.building.upper()
            floor_ok = qp.floor and cp.floor and qp.floor == cp.floor
            room_ok = qp.room and cp.room and qp.room == cp.room
            aoi_ok = qp.aoi and cp.aoi and jaccard_sim(qp.aoi, cp.aoi, 2) >= 0.65

            geo_ok = 0.0
            if qr.lat is not None and qr.lon is not None and cr.lat is not None and cr.lon is not None:
                geo_ok = geo_score(haversine_m(qr.lat, qr.lon, cr.lat, cr.lon))

            if building_ok and floor_ok and (room_ok or geo_ok >= 0.7 or aoi_ok):
                logger.debug("Whitelist matched with %s", cr.rid)
                return MatchResult(
                    decision="SAME",
                    score=max(ms.score, 0.90),
                    feature_scores=ms.feature_scores,
                    evidence={"judge": "rule_whitelist", "best_rid": cr.rid},
                )

            if best is None or ms.score > best.score:
                best = ms
                best_idx = i

        if use_llm and candidates:
            logger.debug("Invoking LLM judge for query %s", qr.rid)
            llm_decision = self._judge_via_llm(query, candidates, pre_scores)
            if llm_decision:
                if llm_decision.decision == "SAME":
                    best_rid = None
                    if isinstance(llm_decision.evidence, dict):
                        best_rid = llm_decision.evidence.get("best_rid")
                    if best_rid:
                        for cr, cp in candidates:
                            if cr.rid == best_rid:
                                reason = self.blacklist_checker.pair_conflict_reason(qr, qp, cr, cp)
                                if reason:
                                    logger.info("LLM decision rejected by blacklist: %s", reason)
                                    return MatchResult(
                                        decision="DIFFERENT",
                                        score=0.0,
                                        feature_scores={},
                                        evidence={"judge": "blacklist", "reason": reason},
                                    )
                                break
                return llm_decision

        if best is None:
            if last_conflict_reason:
                logger.debug("All candidates rejected by blacklist: %s", last_conflict_reason)
                return MatchResult(
                    "DIFFERENT",
                    0.0,
                    {},
                    {"judge": "blacklist", "reason": last_conflict_reason},
                )
        else:
            cr, _cp = candidates[best_idx]
            best.evidence = {"judge": "best_prescore", "best_rid": cr.rid}
            return best

        return MatchResult("DIFFERENT", 0.0, {}, {"judge": "empty_candidates"})

    def _judge_via_llm(
        self,
        query: Tuple[AddressRecord, ParsedAddress],
        candidates: List[Tuple[AddressRecord, ParsedAddress]],
        pre_scores: List[MatchResult],
    ) -> Optional[MatchResult]:
        if not self.llm_api_key:
            return None

        payload = {
            "query": {"record": asdict(query[0]), "parsed": asdict(query[1])},
            "candidates": [
                {"record": asdict(rec), "parsed": asdict(parsed), "pre_score": ms.score}
                for (rec, parsed), ms in zip(candidates, pre_scores)
            ],
        }
        system = (
            "你是地址匹配裁判。根据输入的结构化字段判断两条地址是否描述同一实体。"
            '仅返回 JSON，例如 {"decision": "SAME", "best_idx": 0, "reason": "...", "score": 0.9}。'
        )
        user = json.dumps(payload, ensure_ascii=False)

        body = json.dumps(
            {
                "model": self.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.0,
            }
        ).encode("utf-8")

        req = urllib.request.Request(f"{self.llm_base_url}/chat/completions", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.llm_api_key}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            obj = json.loads(content)
        except Exception as exc:
            logger.exception("LLM judge request failed: %s", exc)
            return None

        decision = str(obj.get("decision", "DIFFERENT")).upper()
        best_idx = int(obj.get("best_idx", 0))
        if best_idx < 0 or best_idx >= len(candidates):
            best_idx = 0
        score = float(obj.get("score", pre_scores[best_idx].score))
        reason = obj.get("reason", "")

        cr, _cp = candidates[best_idx]
        ms = pre_scores[best_idx]
        return MatchResult(
            decision="SAME" if decision == "SAME" else "DIFFERENT",
            score=score,
            feature_scores=ms.feature_scores,
            evidence={"judge": "llm", "reason": reason, "best_rid": cr.rid},
        )

