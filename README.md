# Cal/Val Agent — 卫星高度计定标验证智能体

**LangGraph 驱动的自动化工作流**，支持星间交叉、星自交叉、SIG0 交叉和验潮站参考四种定标方法。

✨ **核心特性**: LLM 智能推荐 · 数据健康诊断 · 双星自动配对 · 一句话定标

---

## 🚀 快速开始

### 环境准备

```bash
# 核心依赖
pip install langgraph langchain langchain-core langchain-openai python-dotenv
pip install netCDF4 h5py python-docx openpyxl cartopy seaborn tables

# 配置 LLM API 密钥（默认 DeepSeek）
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

### 运行示例

```bash
# 星间交叉定标（S6A × JA3）
python main.py "用 S6A 和 JA3 做 2023 年 5 月的星间交叉"

# 星自交叉定标（单星漂移监测）
python main.py "用 JA3 做自交叉监测漂移"

# 验潮站绝对基准参考
python main.py "用 HY-2B 和验潮站做绝对基准参考"
```

---

## 📐 支持的算子

| 编号 | 名称 | 阶段 | 输入 | 输出 |
|------|------|------|------|------|
| **01** | 星间交叉 (Star Cross) | MATCH + CAL | 两星 NC 目录 | `match_result_*.npz` / `calibration_*.npz` |
| **02** | 星自交叉 (Self Cross) | MATCH + CAL | 同星 NC 目录 | `match_result_*.npz` / 漂移统计 |
| **03** | SIG0 交叉 | MATCH + CAL | 双星 H5/NC | `XOver_data_*.h5` / DOCX 报告 |
| **04** | 验潮站参考 (Tide Gauge) | MATCH + CAL | NC + 验潮 TXT | `MATCHED_*.npz` / 绝对偏差 |

> 每个算子均提供 `run()` 本地执行接口。**本版本已移除 SSH 远程模式**，全部走本地执行。

---

## 🏗️ 系统架构

### 层级视图

```
┌──────────────────────────────────────────────────────────────────┐
│                          用户界面层                                │
│   python main.py "用 S6A 和 JA3 做 2023 年 5 月的星间交叉"           │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│                  LangGraph 工作流引擎（7 个节点）                    │
│                                                                  │
│   [task_parser] → [data_discovery] → [method_recommendation]      │
│                                              ↓                   │
│   [result_summarizer] ← [execute_operator] ← [branch_decision]    │
│                              ↑                                    │
│                          [fallback]                               │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│                    核心能力层（层级 1 · 已完成）                     │
│   ├─ DataHealthChecker      NC/H5 完整性诊断                       │
│   ├─ MethodRecommendation   LLM 智能方法推荐                       │
│   ├─ BranchDecision         数据存在性与分支路由                    │
│   └─ AutoAbort              数据不合格时自动阻断                    │
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│                        算子包装器层                                │
│   4 个集成包装器（本地执行，支持 MATCH + CAL 双阶段）：
│   StarCrossPipline · SelfCrossPipline · Sig0CrossPipline · YczPipline
│   每个包装器使用 lazy import 避免循环导入，确保模块独立运行。
└──────────────────────────────────────────────────────────────────┘
                                ↓
┌──────────────────────────────────────────────────────────────────┐
│                         数据适配层                                 │
│   ├─ LocalDataExplorer   卫星文件夹扫描（每星一个目录）              │
│   └─ XMLGenerator        GPF 工单生成（支持主/辅双目录输入）          │
└──────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
calval_agent/
├── agents/                          # LangGraph 工作流
│   ├── workflow.py                  # 7 个节点的图定义 + 路由
│   ├── state.py                     # AgentState 状态定义
│   ├── task_parser.py               # 自然语言 → 结构化任务
│   ├── llm_client.py                # LLM 统一客户端（DeepSeek/OpenAI/…）
│   └── data_health_check.py         # 层级 1: 数据健康诊断
├── operators/
│   ├── gpf_src/                     # GPF 原始源码（从服务器拷入）
│   │   ├── 01_star_cross/{match,cal}/
│   │   ├── 02_self_cross/{match,cal}/
│   │   ├── 03_sig0_cross/{match,cal}/
│   │   └── 04_ycz/{match,cal}/
│   ├── star_cross_pipline.py        # 01 包装器（集成 MATCH + CAL）
│   ├── self_cross_pipline.py        # 02 包装器（集成 MATCH + CAL）
│   ├── sig0_cross_pipline.py        # 03 包装器（集成 MATCH + CAL）
│   └── ycz_pipline.py               # 04 包装器（集成 MATCH + CAL）
├── core/
│   ├── base_operator.py             # 算子抽象基类
│   ├── op_config.py                 # LocalConfig 数据类
│   ├── config.py                    # 配置加载
│   ├── models.py                    # 数据模型
│   └── operators_map.py             # 算子元信息映射
├── data_adapter/
│   ├── explorer.py                  # 本地数据扫描（卫星文件夹模式）
│   └── xml_generator.py             # GPF 工单 XML 生成
├── configs/
│   ├── settings.yaml                # 数据路径 / QC 阈值 / 回退策略
│   └── llm_settings.yaml            # LLM 提供商与模型配置
├── docs/
│   ├── architecture.md              # 技术架构图
│   └── functional_spec.md           # 功能规格书（层级 1/2）
├── tests/                           # 测试脚本
├── .env                             # API 密钥（已 gitignore）
├── .env.example                     # 密钥模板
├── main.py                          # 命令行入口
├── requirements.txt
├── .gitignore
└── LICENSE                          # 非商用许可
```

---

## 💾 数据目录结构

**v2.0 采用「每颗卫星一个文件夹」的组织方式**，选取数据时只需指定卫星文件夹：

```
D:/BaiduSyncdisk/project/202610/data/
├── satelite/                        # 卫星测高数据根目录
│   ├── S6A/                         # Sentinel-6 Michael Freilich
│   │   ├── S6A_P4_2__LR_STD__NT_091_053_20230501T024147_....nc
│   │   └── ... （76 个 NC）
│   └── JA3/                         # Jason-3
│       ├── JA3_GPN_2PfP338_002_20230501_023625_....nc
│       └── ... （76 个 NC）
├── HY-2BGDR/                        # HY-2B GDR（验潮站模块）
├── WSTG/                            # 验潮站水位数据
├── FES2014/                         # 潮汐模型
└── DTU18MSS_1min.nc                 # 平均海面高模型
```

**配置方式** — 编辑 `configs/settings.yaml`：

```yaml
data:
  base_dir:   "D:/BaiduSyncdisk/project/202610/data/satelite"
  star_cross: "D:/BaiduSyncdisk/project/202610/data/satelite"
  self_cross: "D:/BaiduSyncdisk/project/202610/data/satelite"
  sig0_cross: "D:/BaiduSyncdisk/project/202610/data/satelite"
  ycz_match:  "D:/BaiduSyncdisk/project/202610/data"
  tide_ext:   "D:/BaiduSyncdisk/project/202610/data"
  hy2bgdr:    "D:/BaiduSyncdisk/project/202610/data/HY-2BGDR"
  wstg:       "D:/BaiduSyncdisk/project/202610/data/WSTG"
  mss:        "D:/BaiduSyncdisk/project/202610/data/DTU18MSS_1min.nc"
  fes2014:    "D:/BaiduSyncdisk/project/202610/data/FES2014"
```

---

## 🔄 工作流节点详解

### 节点 1 · Task Parser

**功能**: 自然语言 → 结构化任务  
**输入**: `"用 S6A 和 JA3 做 2023 年 5 月的星间交叉"`

```python
{
  "primary_sat": "S6A",
  "aux_data_type": "JA3",
  "method": "star_cross",
  "start_date": "20230501",
  "end_date": "20230531"
}
```

### 节点 2 · Data Discovery

**功能**: 扫描 `data/satelite/` 下的卫星文件夹  
**行为**:
- **星间交叉 / 自交叉**：列出所有卫星目录，按目标星过滤（星间交叉保留主星 + 辅星两个目录）
- **其他方法**：按主星 ID 过滤

**输出**:
```python
available_datasets = [
  {"sat_id": "JA3", "path": ".../satelite/JA3", "nc_count": 76, "start_date": "20230501", ...},
  {"sat_id": "S6A", "path": ".../satelite/S6A", "nc_count": 76, "start_date": "20230501", ...},
]
metadata["data_summary"] = {
  "primary_sat": "S6A", "aux_sat": "JA3",
  "satellite_stats": {"JA3": 76, "S6A": 76},
  "total_files": 152,
}
```

### 节点 3 · Method Recommendation ✨ 层级 1

**功能**: 结合数据统计与 LLM 分析，给出方法推荐  
**逻辑**:
1. 组装上下文（任务信息 + 卫星统计 + 数据集摘要）
2. 调用 `LLMClient.generate_recommendation()`
3. 从回复文本中提取信号：数据不足 → `confidence=low`；"不建议" → `action=review`
4. **无可用数据集 → 强制 `action=abort`**
5. LLM 调用异常 → 回退基础规则（`fallback_used=True`）

**输出**:
```python
{
  "action": "proceed",          # proceed | review | abort
  "method": "star_cross",
  "confidence": "medium",
  "reasoning": ["<LLM 分析文本>"],
  "alternative_methods": [],
  "warnings": []
}
```

### 节点 4 · Branch Decision

**功能**: 依据推荐结果与数据集数量路由  
**分支**: `execute_<method>` → 执行；`fallback_relax_params` → 放宽参数重试（≤3 次）；`fail_exhausted` → 终止

### 节点 5 · Execute Operator

**功能**：构造 `LocalConfig` 并调用算子包装器。

**关键点 · 双星目录配对**：
- 星间交叉 / 自交叉会自动从 `available_datasets` 中分别取出**主星**和**辅星**目录。

**示例代码**:
```python
from operators.self_cross_pipline import SelfCrossCalibration
from core.op_config import LocalConfig

cfg = LocalConfig(
    sat_id="JA3",
    aux_data_type="JA3",
    start_date="20230501", end_date="20230503",
    input_dir="D:/BaiduSyncdisk/project/202610/data/satelite/JA3",
    output_dir="output_local_test/self_cross",
)

result = SelfCrossCalibration(cfg).run()
print(result["status"])  # success
```

### 节点 6 · Fallback

**功能**: 参数放宽重试（当前为占位实现，层级 2 将接入真实重试）

```python
retry 1: distance_to_coast  50 → 100 km
retry 2: ocean_depth       1000 → 2000 m
retry 3: wind_speed        [2,40] → [0,50] m/s
```

### 节点 7 · Result Summarizer

**功能**: 汇总任务、方法、状态、算子结果与日志，写入 `results`

---

## 🎯 核心特性

### 1. LLM 智能推荐

```python
from agents.llm_client import LLMClient

llm = LLMClient()
text = llm.generate_recommendation({
    "primary_satellite": "S6A",
    "auxiliary_data": "JA3",
    "requested_method": "star_cross",
    "data_summary": {"satellite_stats": {"S6A": 76, "JA3": 76}},
})
print(text)
```

配置位于 `configs/llm_settings.yaml`，密钥经 `.env` 注入（`DEEPSEEK_API_KEY`）。

### 2. 卫星文件夹扫描

```python
from data_adapter.explorer import LocalDataExplorer

explorer = LocalDataExplorer("D:/BaiduSyncdisk/project/202610/data/satelite")
for ds in explorer.discover_satellite_folders(date_range=("20230501", "20230531")):
    print(f"{ds['sat_id']}: {ds['nc_count']} 个 NC, {ds['total_size_bytes']/1e6:.1f} MB")
# JA3: 76 个 NC, ...
# S6A: 76 个 NC, ...
```

### 3. 双星输入支持

```python
from operators.star_cross_pipline import StarCrossPipline
from core.op_config import LocalConfig

cfg = LocalConfig(
    sat_id="S6A",
    aux_data_type="JA3",
    start_date="20230501", end_date="20230531",
    input_dir="D:/BaiduSyncdisk/project/202610/data/satelite/S6A",       # 主星
    aux_input_dir="D:/BaiduSyncdisk/project/202610/data/satelite/JA3",   # 辅星
    output_dir="output_local_test/star_cross",
)
result = StarCrossPipline(cfg).run()
print(result["status"])   # success
```

### 4. 一句话定标（完整链路）

```python
from agents.workflow import run_agent

r = run_agent("用 S6A 和 JA3 做 2023 年 5 月的星间交叉")
```

实测输出：

```
[task_parsed]              method=star_cross
[datasets_found]           count=2 stats={'JA3': 76, 'S6A': 76}
[recommendation_generated] action=proceed
[branch_decision]          decision=execute
[operator_executed]        op=star_cross_match status=success
[result_summarized]

产物:
output_local_test/star_cross_0/MDS_S6A_JA3_L2A_MATCH_20230501_20230531_V001/
├── match_result_S6A_vs_JA3_20230501_20230531.npz   # 1605 个交叉点
└── match_result_S6A_vs_JA3_20230501_20230531.csv
```

NPZ 字段：`lon, lat, time_primary, time_aux, ssh_primary, ssh_aux, ssh_diff, distance, distance_to_coast, depth, wind_speed, match_stats`

---

## 🛠️ 配置 LLM

### DeepSeek（默认）

```yaml
# configs/llm_settings.yaml
llm:
  provider: "deepseek"
  api_key_env: "DEEPSEEK_API_KEY"
  base_url: "https://api.deepseek.com/v1"
  model_name: "deepseek-chat"
  temperature: 0.7
```

```bash
echo "DEEPSEEK_API_KEY=sk-xxxx" >> .env
```

### OpenAI（可选）

```yaml
llm:
  provider: "openai"
  api_key_env: "OPENAI_API_KEY"
  base_url: "https://api.openai.com/v1"
  model_name: "gpt-4o-mini"
```

> **安全约定**: 密钥只写在 `.env`（已加入 `.gitignore`），任何情况下都不进代码或 `llm_settings.yaml`。

---

## 📊 已知问题与解决方案

| 现象 | 原因 | 解决 |
|------|------|------|
| `ModuleNotFoundError`    | 模块未正确导入                             | 使用 `lazy import` 避免循环导入，确保模块在运行时动态加载。                             |
| `循环导入`              | 算子包装器间相互导入                       | 将导入逻辑放在 `run()` 方法内，避免模块层面的循环导入。                                   |
| `KeyError: 'AUX_Sat'`    | `IPFUtils` 未从 XML 读到该参数             | 确认 XML 工单的 `Dynamic_Processing_Parameters` 包含 `AUX_Sat` 参数。                     |
| `IndexError: list index out of range` | 工单只有 1 个 `<Input>` 节点          | 生成 2 个 `<Input>` 节点，分别对应主星和辅星目录。                                           |
| `ModuleNotFoundError: tables` | 缺 PyTables 依赖                          | `pip install tables`。                                                                     |
| LLM 调用失败 | 密钥缺失 / 网络不通 | 检查 `.env` 与网络；失败会自动回退规则 |

---

## 🧪 测试

```bash
# 包装器实例化
python tests/test_wrappers.py

# 本地执行（01/02 MATCH/CAL）
python tests/test_operators.py

# 完整工作流
python main.py "用 S6A 和 JA3 做 2023 年 5 月的星间交叉"
```

---

## 📈 演进路线

### ✨ 层级 1（已完成）— 数据智能与诊断

| 模块 | 功能 | 状态 |
|------|------|------|
| `DataHealthChecker` | NC/H5 完整性诊断 | ✅ |
| `MethodRecommendation` | LLM 智能方法推荐 | ✅ |
| `BranchDecision` | 数据存在性判断与路由 | ✅ |
| `AutoAbort` | 数据不合格自动阻断 | ✅ |
| `LocalDataExplorer` | 卫星文件夹扫描 | ✅ |
| 双星目录配对 | 星间交叉主/辅目录自动绑定 | ✅ |

**核心价值**: 避免无效计算，提前识别数据质量问题，让智能体真正参与「选方法」。

### 🟡 层级 2（规划中）— 自适应与优化

| 模块 | 功能 | 计划 |
|------|------|------|
| `ParamOptimizer` | 依数据特征动态调参 | Week 5–6 |
| `ChainExecution` | MATCH → CAL 自动链式执行 | Week 5–6 |
| `QualityEvaluator` | 结果质量评分（RMSE / R² / 残差分布） | Week 6 |
| `SmartRetry` | 基于失败原因的自适应重试 | Week 6 |
| `KnowledgeBase` | 历史案例记忆与复用 | Week 7–8 |

**预期效果**: 一句话定标，全流程无需人工干预。

---

## 📝 开发指南

### 添加新算子

1. 从服务器拷源码到 `operators/gpf_src/<module>/{match,cal}/`。
2. 新建包装器 `operators/<module>_pipline.py`，继承 `BaseOperator`。
3. 实现 `run()` 方法，使用 `lazy import` 避免循环导入。
4. 在 `operators/__init__.py` 的 `ALL_OPERATORS` 注册。

### 调试技巧

```python
import sys
sys.path.insert(0, "operators/gpf_src/02_self_cross/match")

# 清理模块缓存（多次运行后 IPFUtils 易被污染）
for k in list(sys.modules.keys()):
    if k.startswith("func_") or k == "IPFUtils":
        del sys.modules[k]

# 使用 lazy import 方式加载模块
import importlib
mod = importlib.import_module("func_GLSY_ALT_GDR_AUX_SAT_MATCH")
func_self_cross_matching_pro = getattr(mod, "func_self_cross_matching_pro")

# 执行算子
from IPFUtils import MyIPFConfig
func_self_cross_matching_pro(MyIPFConfig("job.xml"))
```

---

## 🤝 贡献说明

1. **本地优先**: 全部走本地执行，不依赖远程 SSH
2. **逐层验证**: MATCH → CAL 逐个验证，禁止跳步
3. **忠实封装**: 保持 GPF 原始逻辑，最小化修改
4. **可复现**: 测试数据与配置可追溯

---

## 📄 许可证

**本项目为非商业许可**：仅供学术研究与教学使用。

**任何商业用途均须事先取得作者书面许可。** 联系方式：1097304039@qq.com

（同样的限制声明亦见于 `.gitignore` 头部与 `LICENSE` 文件。）

---

## 📞 联系方式

1097304039@qq.com

---

**Last Updated**: 2026-11-02 · **Version**: 2.0（LLM 集成 + 卫星文件夹模式）
