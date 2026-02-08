from __future__ import annotations
from pathlib import Path

from address_audit.config import load_config
from address_audit.db import (
    connect,
    init_db,
    clear_table,
    upsert_record,
    upsert_road,
    upsert_poi,
    upsert_anchor,
    insert_pair_labels,
)
from address_audit.simulate import seed_base_entities, generate_address_records

"""
地址稽核系统的仿真数据初始化脚本：生成样例地址后写入 Excel 工作簿，便于快速搭建可复用的测试环境。
1) 加载 config.default.json，确定 Excel 文件路径与运行参数；
2) 初始化 Excel（创建/清空 address_records、roads、pair_labels 等工作表）；
3) 写入道路/POI/锚点等基础实体，作为解析阶段的知识库；
4) 生成 30 个实体 × 5 种变体的地址记录以及配对标签，并写入工作簿；
5) 输出写入统计并提示下一步运行 cli_run。
"""

def main():
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    cfg = load_config(data_dir / "config.default.json")

    conn = connect(cfg.db_path)
    init_db(conn)

    for t in ["address_records","parsed_addresses","roads","pois","anchors","conflicts","match_logs","clusters","pair_labels"]:
        clear_table(conn, t)

    base = seed_base_entities()
    for r in base["roads"]:
        upsert_road(conn, r["road_id"], r["name"], r.get("district"), r.get("aliases", []))
    for p in base["pois"]:
        upsert_poi(conn, p["poi_id"], p["name"], p.get("poi_type"), p.get("district"), p["lat"], p["lon"], p.get("aliases", []))
    for a in base["anchors"]:
        upsert_anchor(conn, a["anchor_id"], a.get("anchor_type"), a["key_text"], a.get("district"), a["lat"], a["lon"])

    records, labels = generate_address_records(n_entities=6, variants_per_entity=5, seed=7)
    for rec in records:
        upsert_record(conn, rec)
    insert_pair_labels(conn, labels)

    print(f"Excel 数据写入: {cfg.db_path}")
    print(f"Inserted records: {len(records)}")
    print(f"Inserted pair labels: {len(labels)}")
    print("Next: python cli_run")

if __name__ == "__main__":
    main()
