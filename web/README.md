# Cal/Val Agent Web 前端

本项目基于 **FastAPI + 原生 HTML/CSS/JS**，为 LangGraph 定标智能体提供图形化操作界面。
无需 Node/构建工具，浏览器直接访问即可。

## 启动

```bash
# 推荐：用项目指定的 Python 解释器
cd D:/BaiduSyncdisk/project/202610/calval_agent
"D:/Software/anaconda3/envs/llm/python.exe" web/server.py

# 或指定端口/地址
CALVAL_WEB_PORT=8088 "D:/Software/anaconda3/envs/llm/python.exe" -m uvicorn web.server:app --host 0.0.0.0 --port 8088
```

启动后访问：<http://127.0.0.1:8088>

## 页面流程（与后端节点一一对应）

| 步骤 | 页面区块 | 调用接口 | 说明 |
|------|----------|----------|------|
| 1 | 数据发现 | `GET /api/discover?mode=local\|remote` | 扫描卫星/验潮站目录，生成 data_summary |
| 2 | 可执行性判断 | `POST /api/judge` | LLM 判断现有数据是否可执行 |
| 2 | 解析任务 | `POST /api/parse` | 自然语言 → 结构化 method/卫星/日期 |
| 2 | 查询知识库 | `POST /api/kb` | 匹配历史案例 + 失败警告 |
| 2 | 推荐方法 | `POST /api/recommend` | LLM 推荐或校验方法 |
| 2 | 填充参数 | `POST /api/param_fill` | 生成完整参数体（可编辑） |
| 3 | 参数确认 | 前端 textarea | 用户确认/修改参数体 |
| 3 | 执行定标 | `POST /api/execute` → 轮询 `GET /api/jobs/{id}` | 后台线程执行 MATCH→CAL |
| 4 | 结果展示 | 前端渲染 | 统计表格 + 图片预览 + 文件下载 |

## 目录

```
web/
├── server.py     # FastAPI 后端（数据发现/解析/知识库/执行/文件服务）
├── index.html    # 单页界面
├── styles.css    # 深色主题样式
├── app.js        # 前端逻辑（fetch + 渲染）
├── run.bat       # Windows 一键启动
├── run.sh        # Linux/macOS 一键启动
└── README.md
```

## 依赖

```bash
"D:/Software/anaconda3/envs/llm/python.exe" -m pip install fastapi uvicorn
```

（其余依赖 langgraph / langchain-openai / numpy / h5py / matplotlib 等项目已装。）

## 接口速查

- `GET  /api/health` — 健康检查
- `GET  /api/settings` — 本地/远程数据路径配置
- `GET  /api/discover?mode=local` — 数据发现
- `POST /api/parse` — 任务解析
- `POST /api/judge` — 可执行性判断
- `POST /api/kb` — 知识库查询
- `POST /api/recommend` — 方法推荐
- `POST /api/param_fill` — 参数体生成
- `POST /api/execute` — 提交执行（后台线程）
- `GET  /api/jobs/{id}` — 轮询执行状态
- `GET  /api/kb/all` — 全部历史案例
- `GET  /api/file?path=<相对项目根路径>` — 预览/下载输出文件

## 说明

- 执行为**后台线程 + 轮询**，MATCH→CAL 耗时较长时可安全等待。
- 参数体 `input / input_AUX / output` 等使用**绝对路径**，请与 `config/settings.yaml` 的数据目录保持一致。
- 结果图片自动从 `result.cal_result.output_files.plots` 等字段收集，经 `/api/file` 提供预览。
- 远程模式（remote）依赖 `config/settings.yaml` 中 `serverdata.api_address` 指向的算子服务。README 标注「本版本已移除 SSH 远程模式」，远程接口需自行部署。