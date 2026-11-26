# -*- coding: utf-8 -*-
"""质量评价节点模板 — 复制到 agents/nodes/quality_eval_node.py 后按需修改。

要点（踩过的坑，改之前先读）:
  1. method 不在 operator_result 里 —— 从 state["recommendation"]["method"] 取，
     否则所有算子都拿默认阈值打分。
  2. CAL 统计单位不统一：StarCross 用 _m，SelfCross/OceanTide 用 _cm。
     比较前统一归一到米（_cm 除以 100）。
  3. OceanTide/YCZ 的 percent 是字符串 "12.34"，不是 float ——
     直接和阈值比大小会 TypeError，必须先 _as_float。
  4. 缺失指标 ≠ 0 分。Sig0Cross/OceanTide 没有 r_squared，
     缺指标要从分母里剔除，不是当 0 算。
  5. 阈值写在 config/quality_thresholds.yaml，不硬编码；
     method 名和配置键不是一一对应（ycz_match → ocean_tide），要显式映射。
  6. 所有早退分支必须返回同一套键（含 retry_count_after），
     否则上层读 quality["retry_count_after"] 直接 KeyError。
  7. 重试循环里不要调 interrupt()（web 线程无 UI handler）。
  8. 新节点的输出键必须先在 AgentState 里声明，否则 Pyright 报
     "is an undefined item in type AgentState"。
"""

import os
from typing import Any, Dict, Optional

from agents.nodes.state import AgentState

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


CONFIG_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "config", "quality_thresholds.yaml"
))

PASS_LINE = 60
MAX_RETRIES = 2

# 缺省阈值：配置文件不存在时兜底
DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "star_cross_cal": {
        "max_mean_diff_m": 3.0,
        "max_rmse_m": 5.0,
        "min_r_squared": 0.7,
        "min_valid_ratio": 0.6,
    },
    "sig0_cross": {"min_count": 5, "max_bias": 0.5, "min_corr_coef": 0.7},
    "ocean_tide": {
        "min_total_points": 10,
        "max_percent": 30.0,
        "max_global_std_cm": 10.0,
    },
}

# method -> 阈值配置键（不是一一对应，必须显式映射）
THRESHOLD_KEY = {
    "star_cross": "star_cross_cal",
    "self_cross": "star_cross_cal",
    "sig0_cross": "sig0_cross",
    "ycz_match": "ocean_tide",
    "tide_ext": "ocean_tide",
}


def load_thresholds(method: str) -> dict:
    """读 config/quality_thresholds.yaml，缺失的键用默认值补齐。"""
    key = THRESHOLD_KEY.get(method)
    if key is None:
        return {}
    default = dict(DEFAULT_THRESHOLDS.get(key, {}))
    if yaml is None or not os.path.exists(CONFIG_PATH):
        return default
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user = (yaml.safe_load(f) or {}).get(key, {}) or {}
    except Exception:
        return default
    default.update(user)
    return default


def _as_float(value: Any) -> Optional[float]:
    """'12.34' / 12.34 / np.float64 统一成 float；转不了返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    val = _as_float(value)
    return int(val) if val is not None else None


def _to_meters(stats: dict) -> dict:
    """把 _cm 变体归一到米，返回统一单位后的视图。"""
    out = dict(stats)
    for cm_key, m_key in (
        ("mean_diff_cm", "mean_diff_m"),
        ("rmse_cm", "rmse_m"),
        ("std_diff_cm", "std_diff_m"),
    ):
        if out.get(cm_key) is not None and out.get(m_key) is None:
            out[m_key] = out[cm_key] / 100.0
    return out


def _build(method: str, passed: bool, rating: int,
           issues: list, can_retry: bool, retry_count: int) -> Dict[str, Any]:
    """统一组装返回值，保证字段齐全（上层不会 KeyError）。"""
    return {
        "pass": passed,
        "score": rating,
        "rating": rating,
        "issues": issues,
        "retry": can_retry,
        "retry_count_after": retry_count,
        "method": method,
    }


def flatten_operator_result(result: dict) -> dict:
    """把算子返回的嵌套结构压平成 check 期望的形状。

    算子返回：{status, execution_time, match_result:{statistics}, cal_result:{statistics}}
    评价函数只读顶层 statistics，优先取 CAL（定标结论），缺则退 MATCH。
    """
    if not isinstance(result, dict):
        return {}
    cal_stats = (result.get("cal_result") or {}).get("statistics") or {}
    mat_stats = (result.get("match_result") or {}).get("statistics") or {}
    stats = dict(cal_stats) if cal_stats else dict(mat_stats)
    # StarCross 的 CAL 统计里没有总匹配点数，用 MATCH 的补上，有效点占比才有分母
    if mat_stats:
        for k in ("total_match", "pass_all", "total_match_points"):
            if k not in stats and mat_stats.get(k) is not None:
                stats[k] = mat_stats[k]
    flat = dict(result)
    flat["statistics"] = stats
    return flat


def evaluate_quality(result: dict, method: str, retry_count: int = 0) -> dict:
    """纯函数，图和 web 的 _run_job 都可调用。"""
    method = (method or "").strip()
    retry_count = _as_int(retry_count) or 0

    if not isinstance(result, dict) or not result:
        return _build(method, False, 0, ["算子无返回结果"], False, retry_count)
    if result.get("status") != "success":
        return _build(method, False, 0,
                      ["算子执行失败：%s" % (result.get("error") or "未知错误")],
                      False, retry_count)

    stats = _to_meters((result.get("statistics") or {}))
    if not isinstance(stats, dict) or not stats:
        return _build(method, False, 0, ["结果缺少 statistics 字段"], False, retry_count)

    thr = load_thresholds(method)
    if not thr:
        return _build(method, False, 0,
                      ["未知算子方法：%s" % (method or "(空)")], False, retry_count)

    issues: list = []
    passed = 0
    checks = 0

    def check(name, value, limit, lower_is_better):
        """value 为 None 时跳过（缺失指标不计 0 分）。"""
        nonlocal passed, checks
        if value is None:
            issues.append("缺少 %s 字段，无法判定" % name)
            return
        checks += 1
        bad = value < limit if lower_is_better else value > limit
        if bad:
            issues.append("%s=%s 越过阈值 %s" % (name, value, limit))
        else:
            passed += 1

    if method in ("star_cross", "self_cross"):
        check("mean_diff_m", _as_float(stats.get("mean_diff_m")), thr["max_mean_diff_m"], False)
        check("rmse_m", _as_float(stats.get("rmse_m")), thr["max_rmse_m"], False)
        check("r_squared", _as_float(stats.get("r_squared") or (stats.get("regression") or {}).get("r_squared")),
              thr["min_r_squared"], True)
        total = _as_int(
            stats.get("total_match_points")
            or stats.get("total_crossover_points")
            or stats.get("total_match")
            or stats.get("total_num")
        ) or 0
        valid = _as_int(stats.get("num_valid_points") or stats.get("valid_points")) or 0
        if total:
            check("valid_ratio", valid / total, thr["min_valid_ratio"], True)
        # total_match 缺失时（StarCross 本地跑只返回 CAL 统计）跳过占比判定，不算失败
    elif method == "sig0_cross":
        check("count", _as_int(stats.get("count")), thr["min_count"], True)
        check("bias", _as_float(stats.get("bias")), thr["max_bias"], False)
        check("corr_coef", _as_float(stats.get("corr_coef")), thr["min_corr_coef"], True)
    else:  # ycz_match / tide_ext
        check("total_match_points",
              _as_int(stats.get("total_match_points") or stats.get("total_num")),
              thr["min_total_points"], True)
        check("percent", _as_float(stats.get("percent")), thr["max_percent"], False)
        check("global_std_cm", _as_float(stats.get("global_std_cm")),
              thr["max_global_std_cm"], False)

    rating = int(round(passed / checks * 100)) if checks else 0
    is_pass = rating >= PASS_LINE
    can_retry = (not is_pass) and (retry_count < MAX_RETRIES)
    return _build(method, is_pass, rating, issues, can_retry,
                  retry_count + 1 if can_retry else retry_count)


def quality_eval_node(state: AgentState) -> AgentState:
    """LangGraph 节点：execute_operator 之后、END 之前。"""
    state = state or {}
    result = flatten_operator_result(state.get("operator_result") or {})
    method = ((state.get("recommendation") or {}).get("method")
              or (state.get("operator_result") or {}).get("method")
              or (state.get("parsed_task") or {}).get("method")
              or "")
    retry_count = _as_int(state.get("retry_count")) or 0

    q = evaluate_quality(result, method, retry_count)

    if q["pass"]:
        quality_status, new_status = "pass", "success"
    elif q["retry"]:
        quality_status, new_status = "fail", "retry_needed"
    else:
        quality_status, new_status = "failed", "failed"

    logs = list(state.get("logs") or []) + [{
        "event": "quality_evaluated",
        "method": method,
        "pass": q["pass"],
        "rating": q["rating"],
        "issues": q["issues"],
        "retry_count": q["retry_count_after"],
    }]

    return {
        "quality_status": quality_status,
        "quality_rating": q["rating"],
        "quality_issues": q["issues"],
        "retry_count": q["retry_count_after"],
        "status": new_status,
        "logs": logs,
    }
