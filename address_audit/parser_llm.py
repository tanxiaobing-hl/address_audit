from __future__ import annotations
import json
import os
import urllib.request
from dataclasses import fields as dataclass_fields
from typing import List

from .models import ParsedAddress

LLM_PARSE_SCHEMA_HINT = {
    "province": "安徽省",
    "city": "合肥市",
    "district": "蜀山区",
    "road": "创新大道",
    "road_no": "110",
    "aoi": "蜀峰广场",
    "building": "F9A",
    "floor": "2",
    "room": "203",
    "shop_name": "惠康大药房",
    "intersection": ["科学大道", "天波路"],
    "direction": "西北",
    "distance_m": 40
}

LLM_ASSIGN_FIELDS = tuple(
    f.name
    for f in dataclass_fields(ParsedAddress)
    if f.name not in {"norm_text", "intersection"}
)


class OpenAILLMParser:
    """LLM 解析器，支持单条或批量地址的结构化解析。"""

    def __init__(self) -> None:
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    def parse(self, raw: str) -> ParsedAddress:
        api_key = self._require_key()
        obj = self._request_single(raw or "", api_key)
        return self._build_parsed(raw or "", obj)

    def parse_batch(self, raws: List[str]) -> List[ParsedAddress]:
        if not raws:
            return []
        api_key = self._require_key()
        results = self._request_batch(raws, api_key)
        parsed: List[ParsedAddress] = []
        for raw, obj in zip(raws, results):
            parsed.append(self._build_parsed(raw or "", obj or {}))
        return parsed

    def _require_key(self) -> str:
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("环境变量 OPENAI_API_KEY 未设置，无法调用 LLM 解析地址")
        return api_key

    def _request_single(self, raw: str, api_key: str) -> dict:
        system = (
            "你是地址结构化解析器。必须返回合法 JSON 字符串，不得包含注释或多余文字。\n"
            "字段：province, city, district, road, road_no, aoi, building, floor, room, shop_name, "
            "intersection(长度恰好为 2 的数组), direction, distance_m。\n"
            "若字段缺失请置为 null。"
        )
        user = (
            "请把以下地址解析为 JSON：\n"
            f"raw=\"{raw}\"\n"
            f"示例：{json.dumps(LLM_PARSE_SCHEMA_HINT, ensure_ascii=False)}"
        )
        payload = self._chat_payload(system, user)
        resp = self._call_openai(payload, api_key)
        return self._extract_obj(resp)

    def _request_batch(self, raws: List[str], api_key: str) -> List[dict]:
        addr_lines = "\n".join(f"{idx+1}. {text}" for idx, text in enumerate(raws))
        system = (
            "你是地址结构化解析器。请按输入顺序解析多个地址，并返回 JSON 数组，数组长度与输入一致。\n"
            "每个元素须包含：province, city, district, road, road_no, aoi, building, floor, room, shop_name, "
            "intersection(数组且长度为 2), direction, distance_m。\n"
            "若字段缺失请填 null。只输出 JSON 数组，不要其他文字。"
        )
        user = (
            f"地址列表：\n{addr_lines}\n"
            f"示例输出：[{json.dumps(LLM_PARSE_SCHEMA_HINT, ensure_ascii=False)}]"
        )
        payload = self._chat_payload(system, user)
        resp = self._call_openai(payload, api_key)
        data = self._extract_obj(resp)
        if not isinstance(data, list):
            raise ValueError("LLM 返回结果不是 JSON 数组")
        return data

    def _chat_payload(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
        }

    def _call_openai(self, payload: dict, api_key: str) -> dict:
        url = f"{self.base_url}/chat/completions"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = resp.read().decode("utf-8")
        return json.loads(out)

    def _extract_obj(self, response: dict) -> dict:
        content = response["choices"][0]["message"]["content"]
        return json.loads(content)

    def _build_parsed(self, raw: str, obj: dict) -> ParsedAddress:
        parsed = ParsedAddress(norm_text=raw)
        for key in LLM_ASSIGN_FIELDS:
            if key in obj and obj[key] not in (None, ""):
                value = str(obj[key]) if key in {"road_no", "floor", "room"} else obj[key]
                setattr(parsed, key, value)
        if isinstance(obj.get("intersection"), list) and len(obj["intersection"]) == 2:
            parsed.intersection = (obj["intersection"][0], obj["intersection"][1])
        return parsed
