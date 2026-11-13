from agents.nodes.state import AgentState
from core.op_config import LocalConfig
from operators.src.config import *

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
        result = op_cls.run()
    except Exception as e:
        result = {"status": "failed", "error": str(e)}

    return {
        "operator_result": result,
        "status": "success" if result.get("status") == "success" else "failed",
        "logs": state["logs"] + [{"event": "operator_executed", "operator": method, "status": result.get("status")}],
    }