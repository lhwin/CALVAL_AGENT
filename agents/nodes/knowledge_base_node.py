from agents.nodes.state import AgentState
import json
import os
from datetime import datetime


KB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "kb_cases.json")


def knowledge_base_node(state: AgentState) -> AgentState:
    """
    历史案例记忆与复用节点。
    根据当前 parsed_task 匹配相似历史案例，输出建议参数和历史失败提醒。
    """
    parsed = state.get("parsed_task", {}) or {}
    logs = state.get("logs", [])

    # 1. 加载历史案例
    cases = _load_kb_cases()

    # 2. 匹配相似案例（方法 + 主卫星相同优先，其次方法相同）
    similar = _match_similar_cases(cases, parsed)

    # 3. 生成建议和警告
    suggestions, warnings = _extract_suggestions(similar, parsed)

    return {
        "kb_cases": similar,
        "kb_suggestions": suggestions,
        "kb_warnings": warnings,
        "logs": logs + [
            {"event": "kb_query", "matched_count": len(similar), "method": parsed.get("method")},
        ],
    }


def _load_kb_cases() -> list:
    """从文件加载历史案例。"""
    if not os.path.exists(KB_PATH):
        return []
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _match_similar_cases(cases: list, parsed: dict) -> list:
    """匹配相似历史案例。"""
    method = parsed.get("method")
    primary_sat = parsed.get("primary_sat")
    
    # 先匹配 方法+主卫星 都相同的
    exact = [c for c in cases if c.get("method") == method and c.get("primary_sat") == primary_sat]
    if exact:
        return exact[:5]
    
    # 再匹配 方法相同的
    same_method = [c for c in cases if c.get("method") == method]
    return same_method[:5]


def _extract_suggestions(similar: list, parsed: dict) -> tuple:
    """从历史案例提取参数建议和失败警告。"""
    suggestions = {}
    warnings = []
    
    for case in similar:
        if case.get("status") == "success" and case.get("operator_config"):
            # 取最近一次成功的参数作为建议
            suggestions.update(case["operator_config"])
        if case.get("status") == "failed" and case.get("failure_reason"):
            warnings.append({
                "case_id": case.get("case_id"),
                "reason": case["failure_reason"],
                "avoid": "避免重复相同参数配置",
            })
    
    return suggestions, warnings
