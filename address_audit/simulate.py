from __future__ import annotations
import random
import uuid
from typing import Dict, List, Tuple

from .models import AddressRecord


"""
地址数据合成器
核心功能
1. 生成基础地理参考数据（seed_base_entities()）
    道路（roads）：含名称、行政区、别名（如"创新大道" 和 "Chuangxin Ave"）
    兴趣点（POIs）：含AOI/POI类型、坐标、别名（如"高新创新园" 和 "创新园"）
    锚点（anchors）：交叉路口或关键POI作为定位参考（如"科学大道|天波路"交口）

2. 生成带噪声的地址记录（generate_address_records()）
    创建 n_entities 个“真实”地址实体（默认30个），每个包含结构化信息：
        AOI（如"高新创新园"）、楼栋、楼层、房间号、道路、门牌号、商铺等
        地理坐标（在基础坐标上添加微小扰动模拟测量误差）
    为每个实体生成 variants_per_entity 种文本变体（默认5种），模拟真实场景中的表达多样性：
        楼层："1楼" / "一层" / "一樓"
        楼栋："F9A" / "F9A栋" / "F9A号楼"
        地址模板多样化（3种格式随机选择）
        添加交叉路口描述作为补充定位信息
        模拟数据源差异（高德、CRM、人工录入等6种来源）
        注入噪声：8%概率将行政区错误标记为"瑶海区"（实际应为"蜀山区"）

3. 生成监督学习标签
    正样本（label=1）：同一实体的不同变体两两配对，标记为“应匹配”
    负样本（label=0）：不同实体的变体随机配对，标记为“不应匹配”
    正负样本数量大致平衡，用于训练二分类模型
"""

_rid_counter = 0
def _rid() -> str:
    # return uuid.uuid4().hex[:10]
    
    global _rid_counter
    _rid_counter += 1
    return f"rid{_rid_counter:04d}"

def seed_base_entities() -> Dict[str, List[Dict]]:
    # 道路数据，用于地址解析中的参考点
    roads = [
        {"road_id":"r1","name":"创新大道","district":"蜀山区","aliases":["创新大街","Chuangxin Ave"]},
        {"road_id":"r2","name":"科学大道","district":"蜀山区","aliases":["KeXue Ave"]},
        {"road_id":"r3","name":"天波路","district":"蜀山区","aliases":["Tianbo Rd"]},
        {"road_id":"r4","name":"文昌路","district":"蜀山区","aliases":[]},
        {"road_id":"r5","name":"永乐北路","district":"蜀山区","aliases":["永乐北街"]},
    ]

    # POI数据，用于地址解析中的参考点
    pois = [
        {"poi_id":"p1","name":"高新创新园","poi_type":"AOI","district":"蜀山区","lat":31.8200,"lon":117.1299,
         "aliases":["创新园","合肥高新创新园","高新区创新园"]},
        {"poi_id":"p2","name":"蜀峰广场","poi_type":"AOI","district":"蜀山区","lat":31.8160,"lon":117.1250,
         "aliases":["蜀峰广场一期","蜀峰广场(一期)","蜀峰广场·一期"]},
        {"poi_id":"p3","name":"名儒学校中学部","poi_type":"POI","district":"蜀山区","lat":31.8120,"lon":117.1320,
         "aliases":["名儒学校","名儒中学部"]},
    ]

    # 锚点数据，用于地址解析中的参考点
    anchors = [
        {"anchor_id":"a1","anchor_type":"intersection","key_text":"科学大道|天波路","district":"蜀山区","lat":31.8204,"lon":117.1292},
        {"anchor_id":"a2","anchor_type":"intersection","key_text":"文昌路|永乐北路","district":"蜀山区","lat":31.8115,"lon":117.1330},
        {"anchor_id":"a3","anchor_type":"poi","key_text":"名儒学校中学部","district":"蜀山区","lat":31.8120,"lon":117.1320},
    ]
    return {"roads": roads, "pois": pois, "anchors": anchors}

def generate_address_records(n_entities: int = 30, variants_per_entity: int = 5, seed: int = 7) -> Tuple[List[AddressRecord], List[Tuple[str,str,int]]]:
    random.seed(seed)
    base_lat, base_lon = 31.8200, 117.1299

    entities = []
    for _ in range(n_entities):
        aoi = random.choice(["高新创新园","蜀峰广场","百盛山甄选自助餐厅-城南店","创新园"])
        building = random.choice(["F9A","F9B","A12","B7","5#","3#"])
        floor = random.choice(["1","2","3","4","5"])
        room = random.choice(["101","203","305","508","1203"])
        road = random.choice(["创新大道","科学大道","文昌路"])
        road_no = str(random.choice([66, 88, 110, 120, 188]))
        shop = random.choice(["惠康大药房","益康大药房","便利店","咖啡馆","自助餐厅"])
        lat = base_lat + random.uniform(-0.01, 0.01)
        lon = base_lon + random.uniform(-0.01, 0.01)
        entities.append({"aoi": aoi, "building": building, "floor": floor, "room": room,
                         "road": road, "road_no": road_no, "shop": shop,
                         "lat": lat, "lon": lon, "district": "蜀山区"})

    records: List[AddressRecord] = []
    entity_to_rids: List[List[str]] = []

    def variant_text(e: Dict) -> str:
        floor_cn = {"1":"一","2":"二","3":"三","4":"四","5":"五"}[e["floor"]]
        floor_style = random.choice([f"{e['floor']}楼", f"{e['floor']}层", f"{floor_cn}楼", f"{floor_cn}层"])
        room_style = random.choice([f"{e['room']}室", f"房{e['room']}", f"{e['room']}"])
        building_style = random.choice([e["building"], f"{e['building']}栋", f"{e['building']}号楼"])
        aoi_style = random.choice([e["aoi"], e["aoi"]+"一期" if e["aoi"]=="蜀峰广场" else e["aoi"]])
        inter = random.choice([
            "（科学大道与天波路交口西北40米）",
            "（文昌路与永乐北路交叉口东南60米）",
            "（名儒学校中学部东侧110米）",
            ""
        ])
        shop_style = e["shop"]
        if e["shop"] in ["惠康大药房","益康大药房"] and random.random() < 0.3:
            shop_style = random.choice(["惠康大药房","益康大药房"])
        if e["aoi"].startswith("百盛山") and random.random() < 0.5:
            shop_style = random.choice(["百盛山海鲜","百盛山甄选自助餐厅-城南店"])
        return random.choice([
            f"合肥市蜀山区{e['road']}{e['road_no']}号 {aoi_style} {building_style} {floor_style} {room_style} {shop_style}{inter}",
            f"安徽省合肥市蜀山区{aoi_style}{building_style}{floor_style}{room_style}（{e['road']}{e['road_no']}号附近）{shop_style}{inter}",
            f"合肥蜀山区 {e['road']} {building_style} {floor_style} {room_style} {shop_style}{inter}",
        ])

    sources = ["gaode","manual","crm","delivery","network_grid","poi"]

    for e in entities:
        rids = []
        for _ in range(variants_per_entity):
            rid = _rid()
            raw = variant_text(e)
            lat = e["lat"] + random.uniform(-0.0002, 0.0002)
            lon = e["lon"] + random.uniform(-0.0002, 0.0002)
            grid = "瑶海区" if random.random() < 0.08 else "蜀山区"
            rec = AddressRecord(rid=rid, source=random.choice(sources), raw_address=raw,
                                district_claim="蜀山区", grid_district=grid, lat=lat, lon=lon)
            records.append(rec)
            rids.append(rid)
        entity_to_rids.append(rids)

    labels: List[Tuple[str,str,int]] = []
    for rids in entity_to_rids:
        for i in range(len(rids)):
            for j in range(i+1, len(rids)):
                labels.append((rids[i], rids[j], 1))

    all_rids = [rid for group in entity_to_rids for rid in group]
    for _ in range(len(labels)):
        a = random.choice(all_rids); b = random.choice(all_rids)
        if a == b:
            continue
        same_cluster = any(a in g and b in g for g in entity_to_rids)
        if not same_cluster:
            labels.append((a, b, 0))

    random.shuffle(labels)
    return records, labels
