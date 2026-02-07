import dotenv
dotenv.load_dotenv()

import json

from address_audit.parser_llm import OpenAILLMParser
from address_audit.utils import EnhancedJSONEncoder


if __name__ == "__main__":
    llm_parser = OpenAILLMParser()
    raw_addresses = [
        "蜀山区创新大道100号高新创新园A座01室",
        "瑶海区长江东路800号名儒学校中学部",
        "庐阳区科学大道与天波路交口东北侧高新创新园",
        "包河区文昌路50号永乐北路口东南侧名儒学校",
        "广州市天河区高塘路8号中国移动南方基地",
    ]

    try:
        llm_results = llm_parser.parse_batch(raw_addresses)
    except Exception as exc:
        print(f"LLM 解析失败: {exc}")
        llm_results = [None] * len(raw_addresses)

    for raw, llm_rst in zip(raw_addresses, llm_results):
        print(f"Raw: {raw}")
        if llm_rst is not None:
            print("llm_parsed_rst:")
            print(json.dumps(llm_rst, cls=EnhancedJSONEncoder, ensure_ascii=False, indent=2))
        else:
            print("llm_parsed_rst: None")
        print("-" * 40)
