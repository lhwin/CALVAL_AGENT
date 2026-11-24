"""
Cal/Val Agent — Web 后端服务（FastAPI）
提供数据发现、任务解析、知识库、方法推荐、参数填充、算子执行等接口，
供 web/ 前端页面调用。

启动方式：
    D:/Software/anaconda3/envs/llm/python.exe web/server.py
    或
    cd <项目根>
    D:/Software/anaconda3/envs/llm/python.exe -m uvicorn web.server:app --host 0.0.0.0 --port 8088
"""
import os
import sys
import json
import time
import uuid
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 确保项目根在 sys.path，允许从 web/ 目录内 import agents.* / operators.* / core.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 兼容算子源码里的 `from src.Xxx import ...` 写法：
# 把 operators/ 加入 sys.path，并将 `src` 别名指向 operators.src
_OPERATORS_DIR = PROJECT_ROOT / "operators"
if str(_OPERATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPERATORS_DIR))
try:
    import src as _src_pkg  # operators/src（operators/ 已在 sys.path 上）
    sys.modules.setdefault("src", _src_pkg)
except Exception:
    pass

from agents.data_adapter.explorer import LocalDataExplorer
from agents.nodes.task_parser import parse_task
from agents.nodes.llm_client import LLMClient
from agents.nodes import judge_execute_node as judge_mod
from agents.nodes import method_recommendation_node as rec_mod
from agents.nodes import knowledge_base_node as kb_mod
from agents.nodes import param_fill_node as pf_mod
import yaml

app = FastAPI(title="Cal/Val Agent Web API", version="1.0.0")

WEB_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
KB_PATH = PROJECT_ROOT / "data" / "kb_cases.json"


# ───────────────────────── 工具函数 ─────────────────────────

def load_settings() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_discovery(mode: str) -> dict:
    """执行数据发现，返回 report 与 data_summary。"""
    settings = load_settings()
    if mode == "remote":
        from core.utils.utils import request_data
        config = settings["serverdata"]
        item = {
            "satelite_dir": config["satelite"],
            "oceantide_dir": config["oceantide"],
        }
        api = config["api_address"] + "/data/discover"
        report = request_data(api, item)
        if report is None:
            raise HTTPException(502, "远程数据发现接口不可达")
    else:
        ld = settings["localdata"]
        explorer = LocalDataExplorer(ld["satelite"], ld["ocean_tide"])
        report = explorer.discover_data()

    data_summary = {
        "satellite_stats": report.get("satellite_stats", {}),
        "tide_summary": report.get("tide_summary", {}),
        "total_nc_files": report.get("total_nc_files", 0),
        "total_txt_files": report.get("total_txt_files", 0),
        "matched_sats": report.get("matched_sats", []),
    }
    return {"report": report, "data_summary": data_summary}


# ───────────────────────── API ─────────────────────────

@app.get("/api/settings")
def get_settings():
    s = load_settings()
    return {
        "localdata": s.get("localdata", {}),
        "serverdata": s.get("serverdata", {}),
    }


@app.get("/api/discover")
def discover(mode: str = "local"):
    try:
        res = run_discovery(mode)
        return {
            "ok": True,
            "satellite": res["report"].get("satellite", []),
            "tide": res["report"].get("tide", []),
            "tide_summary": res["report"].get("tide_summary", {}),
            "data_summary": res["data_summary"],
            "total_nc_files": res["report"].get("total_nc_files", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"数据发现失败: {e}")


@app.post("/api/parse")
def parse(body: dict):
    text = (body.get("task_text") or "").strip()
    if not text:
        raise HTTPException(400, "task_text 不能为空")
    data_summary = body.get("data_summary") or {}
    try:
        parsed = parse_task(text, data_summary)
        return {"ok": True, "parsed": parsed}
    except Exception as e:
        raise HTTPException(500, f"解析失败: {e}")


@app.post("/api/kb")
def kb_query(body: dict):
    """返回与 parsed_task 匹配的历史案例、建议、警告。"""
    parsed = body.get("parsed_task") or {}
    try:
        cases = kb_mod._load_kb_cases()
        similar = kb_mod._match_similar_cases(cases, parsed)
        suggestions, warnings = kb_mod._extract_suggestions(similar, parsed)
        return {
            "ok": True,
            "kb_cases": similar,
            "kb_suggestions": suggestions,
            "kb_warnings": warnings,
        }
    except Exception as e:
        raise HTTPException(500, f"知识库查询失败: {e}")


@app.post("/api/judge")
def judge(body: dict):
    """LLM 判断任务能否执行。返回 can_execute/reason/suggest。"""
    text = (body.get("task_text") or "").strip()
    data_summary = body.get("data_summary") or {}
    if not text:
        raise HTTPException(400, "task_text 不能为空")
    try:
        llm = LLMClient()
        prompt = f"""
        下面是数据统计结果
        data_summary: {data_summary.get('data_describe', '无')}
        这是用户任务：{text}
        请判断现有数据是否可执行。返回 JSON：
        {{"can_execute": true/false, "reason": "...", "suggest": "..."}}
        """
        res = llm.chat([{"role": "user", "content": prompt}])
        s = res[res.find("{"): res.rfind("}") + 1] if "{" in res else "{}"
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            data = {"can_execute": True, "reason": "", "suggest": ""}
        return {"ok": True, **data}
    except Exception as e:
        return {"ok": False, "can_execute": True, "reason": f"judge 失败(降级可执行): {e}", "suggest": ""}


@app.post("/api/recommend")
def recommend(body: dict):
    parsed = body.get("parsed_task") or {}
    datasets = body.get("available_datasets") or []
    data_summary = body.get("data_summary") or {}
    try:
        # 情况 A：无 method，用 LLM 推断
        if not parsed.get("method"):
            rec = rec_mod._recommend_via_llm(parsed, datasets, data_summary)
            return {"ok": True, "recommendation": rec}
        # 情况 B：已有 method，校验数据条件
        rec = rec_mod._validate_and_score(parsed["method"], datasets, data_summary)
        return {"ok": True, "recommendation": rec}
    except Exception as e:
        raise HTTPException(500, f"推荐失败: {e}")


_STR_FIELDS = {
    "Sat_ID", "AUX_Sat", "Data_version", "Match_Data_Type", "Product_Type",
    "Start_date", "End_date", "Match_time", "Template_docx", "template_doc",
    "order_id", "input", "input_AUX", "output", "outputFileType",
    "proc_name", "version", "Select_Area", "wind_speed", "AUX_YCZ",
    "MSS_PATH", "FES2014_PATH", "operation_type",
}
_INT_FIELDS = {"distance_to_coast", "ocean_depth"}


def _to_bracket_str(v):
    """list/tuple -> '[-60,60,-180,180]' 形式的字符串（GPF 约定，无空格）。"""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(str(x) for x in v) + "]"
    return str(v)


def normalize_param_body(pb: dict) -> dict:
    """
    把参数体归一化到 pydantic 模型要求的类型：
      - 字符串字段（Match_time / Select_Area / wind_speed / order_id 等）统一转 str
      - int 字段（distance_to_coast / ocean_depth）统一转 int
    """
    out = {}
    for k, v in (pb or {}).items():
        if k in _INT_FIELDS:
            if v is None or v == "":
                continue
            try:
                out[k] = int(float(v))
            except (TypeError, ValueError):
                out[k] = v
        elif k in _STR_FIELDS:
            if v is None:
                if k in ("Select_Area", "wind_speed", "Template_docx", "template_doc"):
                    continue
                out[k] = ""
            else:
                out[k] = _to_bracket_str(v)
        else:
            out[k] = v
    return out


@app.post("/api/param_modify")
def param_modify(body: dict):
    """根据自然语言修改参数体（对应 user_confirm 节点的 LLM patch 逻辑）。"""
    param_body = normalize_param_body(body.get("param_body") or {})
    user_reply = (body.get("user_reply") or "").strip()
    if not user_reply:
        raise HTTPException(400, "user_reply 不能为空")
    try:
        llm = LLMClient()
        prompt = (
            f"用户要求修改以下参数：\n"
            f"当前参数：{json.dumps(param_body, ensure_ascii=False)}\n"
            f"用户修改要求：{user_reply}\n\n"
            f"请返回 JSON patch，只包含需要修改的字段，格式：{{\"field_name\": \"new_value\"}}"
        )
        response = llm.chat([{"role": "user", "content": prompt}])
        patch_match = __import__("re").search(r"\{[^{}]*\}", response)
        patch = json.loads(patch_match.group()) if patch_match else {}
        patched = dict(param_body)
        patched.update(patch)
        return {"ok": True, "param_body": normalize_param_body(patched), "patch": patch}
    except Exception as e:
        raise HTTPException(500, f"修改失败: {e}")


@app.post("/api/param_fill")
def param_fill(body: dict):
    parsed = body.get("parsed_task") or {}
    datasets = body.get("available_datasets") or []
    selected = body.get("selected_data") or {}
    data_summary = body.get("data_summary") or {}
    use_llm = body.get("use_llm", True)

    method = parsed.get("method")
    sat_id = parsed.get("primary_sat", "UNKNOWN")
    aux_type = parsed.get("aux_data_type", "UNKNOWN")
    start_date = parsed.get("start_date", "20230101")
    end_date = parsed.get("end_date", "20231231")

    primary_input_dir, aux_input_dir = "", ""
    for ds in datasets:
        if ds.get("sat_id", "").upper() == sat_id.upper():
            primary_input_dir = ds.get("path", "") or ds.get("input_dir", "")
        if aux_type and ds.get("sat_id", "").upper() == aux_type.upper():
            aux_input_dir = ds.get("path", "") or ds.get("input_dir", "")
    if not primary_input_dir and selected:
        primary_input_dir = selected.get("path", "") or selected.get("input_dir", "")
    if not aux_input_dir:
        aux_input_dir = primary_input_dir

    param_body: Dict[str, Any] = {}
    if method == "star_cross":
        param_body = {
            "Sat_ID": sat_id, "AUX_Sat": aux_type, "Data_version": "V001",
            "Match_Data_Type": aux_type, "Product_Type": "SSH",
            "Start_date": start_date, "End_date": end_date, "Match_time": "2.0",
            "Template_docx": "", "order_id": "0", "input": primary_input_dir,
            "input_AUX": aux_input_dir, "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_STAR_CROSS_MATCH_RESULT",
            "proc_name": "gl_ssh_cross_match_pro", "version": "1.0",
            "Select_Area": "[-60,60,-180,180]", "distance_to_coast": 50,
            "ocean_depth": 1000, "wind_speed": "[0,40]",
        }
    elif method == "self_cross":
        param_body = {
            "Sat_ID": sat_id, "Data_version": "V001", "Product_Type": "SSH",
            "Start_date": start_date, "End_date": end_date, "Match_time": "2.0",
            "Template_docx": "", "order_id": "0", "input": primary_input_dir,
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_SELF_CROSS_MATCH_RESULT",
            "proc_name": "gl_ssh_self_cross_match_pro", "version": "1.0",
            "Select_Area": "[-60,60,-180,180]", "distance_to_coast": 50,
            "ocean_depth": 1000, "wind_speed": "[0,40]",
        }
    elif method == "sig0_cross":
        param_body = {
            "Sat_ID": sat_id, "AUX_Sat": aux_type, "Data_version": "V001",
            "Product_Type": "SIG0", "Start_date": start_date, "End_date": end_date,
            "Match_time": "2.0", "Template_docx": "", "order_id": "0",
            "input": primary_input_dir, "input_AUX": aux_input_dir,
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_SIG0_CROSS_MATCH_RESULT",
            "proc_name": "gl_ssh_sig0_cross_match_pro", "version": "1.0",
        }
    elif method in ("ycz_match", "tide_ext"):
        tide_summary = data_summary.get("tide_summary", {})
        param_body = {
            "Sat_ID": sat_id, "Data_version": "V001", "Product_Type": "SSH",
            "Start_date": start_date, "End_date": end_date, "order_id": "0",
            "operation_type": "match", "input": primary_input_dir,
            "input_AUX": selected.get("wstg_dir", "") if selected else "",
            "AUX_YCZ": selected.get("wstg_dir", "zhiwan") if selected else "zhiwan",
            "MSS_PATH": tide_summary.get("mss_path", "") or selected.get("mss_path", "") if selected else "",
            "FES2014_PATH": tide_summary.get("fes2014_path", "") or selected.get("fes2014_path", "") if selected else "",
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_YCZ_MATCH_RESULT",
            "proc_name": "gl_ssh_ycz_match_pro", "version": "1.0",
        }
    else:
        param_body = {
            "Sat_ID": sat_id, "AUX_Sat": aux_type, "Start_date": start_date,
            "End_date": end_date, "input": primary_input_dir,
            "input_AUX": aux_input_dir, "output": f"output_local_test/{method}_0",
        }

    if use_llm:
        try:
            llm = LLMClient()
            prompt = f"""
            请根据以下信息生成定标检验最终的参数体 JSON。
            目前已经确定的参数：{param_body}
            你需要微调的参数：Match_time Select_Area distance_to_coast ocean_depth wind_speed
            只返回 JSON。
            """
            resp = llm.chat([{"role": "user", "content": prompt}])
            s = resp[resp.find("{"): resp.rfind("}") + 1] if "{" in resp else ""
            if s:
                patch = json.loads(s)
                # 只接受微调白名单字段
                for k in ("Match_time", "Select_Area", "distance_to_coast", "ocean_depth", "wind_speed"):
                    if k in patch:
                        param_body[k] = patch[k]
        except Exception as e:
            print(f"[param_fill] LLM 微调失败(保留模板): {e}")

    return {"ok": True, "param_body": normalize_param_body(param_body)}


# ───────────────────────── 算子执行（后台线程） ─────────────────────────

JOBS: Dict[str, Dict[str, Any]] = {}


def _run_job(job_id: str, method: str, param_body: dict, mode: str):
    try:
        JOBS[job_id]["status"] = "running"
        # 按需导入 pipeline，避免 sig0/ocean 的导入错误
        if method == "star_cross":
            from operators.star_cross_pipline import StarCrossCalibration
            op = StarCrossCalibration(param_body)
        elif method == "self_cross":
            from operators.self_cross_pipline import SelfCrossCalibration
            op = SelfCrossCalibration(param_body)
        elif method == "sig0_cross":
            from operators.sig0_cross_pipline import Sig0CrossCalibration
            op = Sig0CrossCalibration(param_body)
        elif method in ("ycz_match", "tide_ext"):
            from operators.ocean_tide_pipline import OceanTideCalibration
            op = OceanTideCalibration(param_body)
        else:
            raise ValueError(f"未知方法: {method}")

        if mode == "remote":
            result = op.run()
        else:
            if hasattr(op, "run_local"):
                result = op.run_local()
            else:
                result = op.run()

        JOBS[job_id].update({
            "status": "done",
            "result": _make_jsonable(result),
            "finished_at": time.time(),
        })
    except Exception as e:
        JOBS[job_id].update({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()[:2000],
            "finished_at": time.time(),
        })


def _make_jsonable(obj):
    """递归把 numpy/Path 等转为 JSON 可序列化，并把项目根内绝对路径转相对路径。"""
    root = str(PROJECT_ROOT)
    if isinstance(obj, dict):
        return {k: _make_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_jsonable(x) for x in obj]
    if isinstance(obj, Path):
        obj = str(obj)
    if isinstance(obj, str):
        # 绝对路径 -> 相对项目根（用于 /api/file?path=）
        norm = obj.replace("\\", "/")
        root_n = root.replace("\\", "/")
        if norm.startswith(root_n):
            rel = norm[len(root_n):].lstrip("/")
            return rel
        return obj
    try:
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except Exception:
        pass
    return obj


@app.post("/api/execute")
def execute(body: dict):
    method = body.get("method")
    param_body = normalize_param_body(body.get("param_body") or {})
    mode = body.get("mode", "local")
    if not method:
        raise HTTPException(400, "method 不能为空")
    if not param_body:
        raise HTTPException(400, "param_body 不能为空")

    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "method": method,
        "mode": mode,
        "param_body": _make_jsonable(param_body),
        "started_at": time.time(),
    }
    th = threading.Thread(target=_run_job, args=(job_id, method, param_body, mode), daemon=True)
    th.start()
    return {"ok": True, "job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "任务不存在")
    return JOBS[job_id]


@app.get("/api/kb/all")
def kb_all():
    try:
        cases = kb_mod._load_kb_cases()
        return {"ok": True, "count": len(cases), "cases": cases}
    except Exception as e:
        raise HTTPException(500, f"读取知识库失败: {e}")


@app.get("/api/health")
def health():
    return {"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S")}


# ───────────────────────── 静态文件 ─────────────────────────

# 静态前端（web 目录）
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(WEB_DIR / "index.html"))


# 供下载/预览算子输出文件（限制在项目根内，防路径穿越）
@app.get("/api/file")
def serve_file(path: str = Query(..., description="相对项目根的路径")):
    full = (PROJECT_ROOT / path).resolve()
    try:
        full.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        raise HTTPException(403, "禁止访问项目外文件")
    if not full.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(str(full))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("CALVAL_WEB_PORT", "8088"))
    print(f"Cal/Val Agent Web 启动于 http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")