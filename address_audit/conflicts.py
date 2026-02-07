from __future__ import annotations
from typing import List
from .models import AddressRecord, ParsedAddress, Conflict

class ConflictChecker:
    def check(self, rec: AddressRecord, parsed: ParsedAddress) -> List[Conflict]:
        conflicts: List[Conflict] = []

        # 冲突1：网格行政区 ≠ 解析行政区
        if rec.grid_district and parsed.district and rec.grid_district != parsed.district:
            conflicts.append(Conflict(rec.rid, "GRID_DISTRICT_MISMATCH",
                                     f"grid_district={rec.grid_district} vs parsed_district={parsed.district}"))
        
        # 冲突2：声明行政区 ≠ 解析行政区
        if rec.district_claim and parsed.district and rec.district_claim != parsed.district:
            conflicts.append(Conflict(rec.rid, "CLAIM_DISTRICT_MISMATCH",
                                     f"district_claim={rec.district_claim} vs parsed_district={parsed.district}"))
        return conflicts
