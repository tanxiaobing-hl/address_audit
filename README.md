# 地址数据治理流水线

一个演示型项目，覆盖地址解析、候选生成、冲突检测、实体消歧与聚类等步骤，所有数据保存在 Excel（原 SQLite 版本已替换）。

## 核心组件
- **LLM 解析**：通过 OpenAI 兼容接口输出结构化字段（省/市/区/道路等），现已取消规则解析与 evidence span。
- **候选生成 & 打分**：结合别名、地理桶、锚点邻域等策略筛选候选并打分。
- **裁决/聚类**：基于得分和裁决器（可扩展 LLM）决定是否为同一实体，再写入聚类表。
- **可配置权重/阈值**：读取 `data/config.default.json`，可用 `cli_eval.py` 进行 grid search。

## 快速开始
```bash
python cli_seed      # 初始化 Excel + 生成模拟数据
python cli_run       # 运行治理流水线
python cli_eval      # 评测 + grid search
```
运行结束后，可在 `data/address_governance.xlsx` 查看所有表。

## 生产落地的三个升级方向
1. **LLM Parser**：结合更强提示词、批量策略或自建模型，获得更准确可靠的解析。
2. **Candidate Generator**：根据业务特征（如网格、POI 层级、历史对齐）设计更高质量的 blocking。
3. **权重/阈值配置化 + 评测调参**：沉淀评测集、调参与可视化工具，持续验证治理效果。
