from agents.nodes.state import AgentState
from core.op_config import LocalConfig
from operators.src.config import *
import json
import os
from datetime import datetime

KB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "kb_cases.json")

def execute_operator_node(state: AgentState) -> AgentState:
    """根据推荐的方法，调用对应算子执行定标任务。"""
    parsed = state.get("parsed_task", {})
    selected = state.get("selected_data") or {}
    metadata = state.get("metadata", {})
    recommendation = state.get("recommendation", {})

    if not recommendation or recommendation["action"] != "proceed":
        return {
            "operator_result": {"status": "failed", "error": "No valid recommendation"},
            "status": "failed",
        }

    method = recommendation["method"]
    sat_id = parsed.get("primary_sat", "UNKNOWN")
    aux_type = parsed.get("aux_data_type", "UNKNOWN")
    
    item = state.get("param_body")

    # 根据方法选择对应算子
    if method == "star_cross":
        from operators.star_cross_pipline import StarCrossCalibration
        op_cls = StarCrossCalibration(item)
    elif method == "self_cross":
        from operators.self_cross_pipline import SelfCrossCalibration
        op_cls = SelfCrossCalibration(item)
    elif method == "tide_ext":
        from operators.ocean_tide_pipline import OceanTideCalibration
        op_cls = OceanTideCalibration(item)
    else:
        return {
            "operator_result": {"status": "failed", "error": f"Unknown method: {method}"},
            "status": "failed",
        }

    # 构建配置
    cfg_kwargs = {
        "sat_id": sat_id,
        "aux_data_type": aux_type,
        "start_date": parsed.get("start_date", "20230101"),
        "end_date": parsed.get("end_date", "20231231"),
        "output_dir": f"output_local_test/{method}",
        "input_dir": selected.get("path", ""),
    }

    # 根据方法补充特定配置
    if method in ("star_cross", "self_cross"):
        cfg_kwargs["input_AUX"] = selected.get("path", "")
    elif method == "tide_ext":
        cfg_kwargs.update({
            "yz_data_dir": selected.get("wstg_dir", ""),
            "mss_path": selected.get("mss_path", ""),
            "fes2014_path": selected.get("fes2014_path", ""),
        })

    try:
        if state["mode"] == "remote":
            result = op_cls.run()
        if state["mode"] == "local":
            result = op_cls.run_local()
    except Exception as e:
        result = {"status": "failed", "error": str(e)}

    result = dict(result)
    result["method"] = method

    return {
        "operator_result": result,
        "quality_status": "pending",
        "status": "success" if result.get("status") == "success" else "failed",
        "logs": state["logs"] + [
            {"event": "operator_executed", "operator": method, "status": result.get("status")}
        ],
    }



def _save_kb_case(state: AgentState, method: str, parsed: dict, selected: dict, recommendation: dict, result: dict) -> dict:
    """把本次执行案例追加到知识库，避免重复条目，保留最近 200 条。"""
    new_case = {
        "case_id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "task_text": parsed.get("task_text", ""),
        "method": method,
        "primary_sat": parsed.get("primary_sat"),
        "aux_data_type": parsed.get("aux_data_type"),
        "start_date": parsed.get("start_date"),
        "end_date": parsed.get("end_date"),
        "operator_config": state.get("param_body", {}),
        "status": result.get("status", "unknown"),
        "failure_reason": result.get("error") if result.get("status") == "failed" else None,
        "match_result": (result.get("match_result") or {}).get("statistics"),
        "cal_result": (result.get("cal_result") or {}).get("statistics"),
        "created_at": datetime.now().isoformat(),
    }

    if not os.path.exists(os.path.dirname(KB_PATH)):
        os.makedirs(os.path.dirname(KB_PATH), exist_ok=True)

    cases = []
    if os.path.exists(KB_PATH):
        try:
            with open(KB_PATH, "r", encoding="utf-8") as f:
                cases = json.load(f)
        except (json.JSONDecodeError, IOError):
            cases = []

    # 去重：相同 method+sat+dates+status 不重复写入
    fingerprint = (
        new_case["method"],
        new_case["primary_sat"],
        new_case["start_date"],
        new_case["end_date"],
        new_case["status"],
    )
    if any(
        (c.get("method"), c.get("primary_sat"), c.get("start_date"), c.get("end_date"), c.get("status")) == fingerprint
        for c in cases
    ):
        return {}

    cases.append(new_case)
    cases.sort(key=lambda c: c.get("case_id", ""), reverse=True)
    cases = cases[:200]

    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)

    return {}