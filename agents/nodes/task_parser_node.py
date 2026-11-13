from agents.nodes.state import AgentState
from agents.nodes.task_parser import parse_task

def task_parser_node(state: AgentState) -> AgentState:
    """任务解析节点：用大模型解析用户自然语言，判断关键字段是否缺失，设置分流标记。"""
    text = state.get("task_text", "")
    if not text:
        return {
            "parsed_task": {"method": None, "error": "Empty task text"},
            "status": "failed",
            "logs": state["logs"] + [{"event": "task_parsed", "status": "error"}],
        }

    # 获取数据分析结果
    data_summary = state.get("metadata", {}).get("data_summary", {})

    parsed = parse_task(text, data_summary)
    parsed["task_text"] = text

    # 判断缺失关键字段
    required = ["method", "primary_sat", "start_date", "end_date"]
    missing = [f for f in required if not parsed.get(f)]

    branch = "ready_to_execute" if not missing else "need_user_input"
    recommendation = None
    if parsed.get("method") and branch == "ready_to_execute":
        recommendation = {
            "action": "proceed",
            "method": parsed["method"],
            "confidence": "high",
            "reasoning": ["task_parser已识别方法，跳过LLM推荐"],
        }

    return {
        "parsed_task": parsed,
        "recommendation": recommendation,
        "missing_fields": missing,
        "branch_path": branch,
        "logs": state["logs"] + [
            {
                "event": "task_parsed",
                "method": parsed.get("method"),
                "branch": branch,
                "missing_fields": missing,
            },
        ],
    }
