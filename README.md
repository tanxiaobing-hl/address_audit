# 地址数据治理

这个工程演示一套地址治理流水线：Excel/SQLite + 解析 + 候选生成 + 判同去重 + 冲突校验 + 评测/调参
- **LLM 解析（OpenAI 规范接口）**：输出结构化字段
- **候选生成增强**：区县/AOI/楼栋/道路别名、地理桶 + 邻域桶、相对位置(交口/地标/方位/距离)锚点候选
- **可配置的权重与阈值**：从 `data/config.default.json` 加载；提供 `grid search` 在模拟标注集上选最优阈值/权重
- **SQLite 存储**：原始记录、解析结果、匹配日志、冲突、聚类簇、基础POI/道路/交口锚点、标注数据；
- **Excel存储**：底层存储可以把SQLite数据库换成Excel文件

---

## 快速开始

### 0) 环境准备

- 在根目录下运行如下指令，安装所需要的依赖，构建运行环境。

```bash
uv sync
```
- 设置环境变量
执行如下命令，创建环境变更。再设置正确的环境变量。
```bash
mv .env_example .env
```
​       设置大模型调用的环境变量：OPENAI_API_KEY、OPENAI_MODEL、OPENAI_BASE_URL等。

### 1) 初始化数据库 + 生成模拟基础数据与地址记录
```bash
python cli_seed.py
```
生成模拟数据的过程中会使用配置信息：data/config.default.json
### 2) 运行治理流水线（解析 -> 冲突 -> 候选 -> 打分 -> 裁决 -> 聚类）

会把address_records中的所有地址记录进行聚类。即把属于同一地点的地址聚到同一类。

```bash
python  cli_run.py
```

### 3) 运行评测 + 调参（grid search）并产出最优 config
```bash
python  cli_eval.py
```

评测会在 `data/config.best.json` 输出一份“更适配模拟数据”的配置（阈值与权重）。



## 界面操作
### 1) 运行如下命令，启动后台服务器
```bash
python app.py
```
### 2) 在浏览器中打开服务器地址并进行操作