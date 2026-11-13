from agents.nodes.state import AgentState
from agents.nodes.llm_client import LLMClient
import re


def method_recommendation_node(state: AgentState) -> AgentState:
    """基于 LLM + 已有数据，智能推荐最佳定标方法。"""
    parsed = state.get("parsed_task", {}) or {}
    available_datasets = state.get("available_datasets", [])
    metadata = state.get("metadata", {}) or {}
    data_summary = metadata.get("data_summary", {}) or {}
    logs = state.get("logs", [])

    # --- 情况 A：task_parser 还没给出 method，用 LLM 推断 ---
    suggested_method = parsed.get("method")

    if not suggested_method:
        try:
            recommendation = _recommend_via_llm(parsed, available_datasets, data_summary)
            return {
                "recommendation": recommendation,
                "parsed_task": {**parsed, "method": recommendation["method"]},  # 回填到 state
                "logs": logs + [{"event": "recommendation_generated_by_llm", "method": recommendation["method"], "confidence": recommendation["confidence"]}],
                "status": recommendation["action"],
            }
        except Exception as e:
            logs.append({"event": "llm_recommendation_failed", "error": str(e)})

    # --- 情况 B：已知道 method，校验数据是否够用 ---
    recommendation = _validate_and_score(suggested_method, available_datasets, data_summary)
    return {
        "recommendation": recommendation,
        "logs": logs + [{"event": "recommendation_validated", "method": recommendation["method"], "confidence": recommendation["confidence"]}],
        "status": recommendation["action"],
    }


def _recommend_via_llm(parsed: dict, datasets: list, data_summary: dict) -> dict:
    """用 LLM 分析数据和任务上下文，推荐最优方法。"""
    llm = LLMClient()

    sat_info = []
    for ds in datasets:
        sat_info.append(f"  - {ds.get('sat_id', '?')}: {ds.get('path', '?')} ({ds.get('file_count', 0)} files)")
    satellites_str = "\n".join(sat_info) if sat_info else "  (无卫星数据)"

    tide_has_wstg = data_summary.get("tide_summary", {}).get("has_wstg", False)
    nc_count = data_summary.get("tide_summary", {}).get("nc_count", 0)

    system_prompt = """你是一个卫星高度计定标验证专家助手。
请根据可用的卫星数据和潮汐站数据，推荐最合适的定标方法。
可选方法：star_cross(星间交叉)、self_cross(自交叉)、sig0_cross(σ⁰交叉)、tide_ext(验潮站外推)。
选择依据：
- star_cross：需要≥2颗卫星的 GDR 数据
- self_cross：需要≥1颗卫星的 GDR 数据
- sig0_cross：需要≥2颗卫星的 SIG0 数据
- tide_ext：需要有 WSTG 验潮站数据(NC 文件)
只返回 JSON，不要解释。"""
    prompt = f"""用户任务参数：{parsed}

可用卫星数据：
{satellites_str}

潮汐站数据：WSTG={'有' if tide_has_wstg else '无'}，NC文件数={nc_count}

请返回 JSON：{{"method": "...", "reasoning": ["..."], "confidence": "high|medium|low", "action": "proceed|review"}}"""

    response = llm.chat([{"role": "user", "content": prompt}], system_prompt=system_prompt)
    json_match = re.search(r'\{[^{}]*\}', response)
    result = json.loads(json_match.group()) if json_match else {"method": "self_cross", "confidence": "low", "action": "review", "reasoning": ["LLM解析失败，降级为自交叉"]}

    return {
        "action": result.get("action", "review"),
        "method": result.get("method", "self_cross"),
        "confidence": result.get("confidence", "low"),
        "reasoning": result.get("reasoning", []),
    }


def _validate_and_score(method: str, datasets: list, data_summary: dict) -> dict:
    """校验已有 method 所需的数据条件是否满足。"""
    n_sats = len(datasets)
    has_wstg = data_summary.get("tide_summary", {}).get("has_wstg", False)

    required = {
        "star_cross": lambda: n_sats >= 2,
        "self_cross": lambda: n_sats >= 1,
        "sig0_cross": lambda: n_sats >= 2,
        "tide_ext": lambda: has_wstg,
    }
    condition_ok = required.get(method, lambda: True)()

    action = "proceed" if condition_ok else "review"
    reasoning = [f"{method}需要{2 if method in ('star_cross','sig0_cross') else 1}颗卫星(现有{n_sats})" if method in ("star_cross", "self_cross", "sig0_cross")
                 else "有验潮站数据" if method == "tide_ext" else "方法未知"]
    if not condition_ok:
        reasoning.append("数据不足，建议重新评估")

    return {
        "action": action,
        "method": method,
        "confidence": "high" if condition_ok else "low",
        "reasoning": reasoning,
    }
