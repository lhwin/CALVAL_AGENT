from agents.nodes.state import AgentState
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver
from agents.nodes import llm_client
import json
import re

def user_confirm_node(state: AgentState) -> AgentState:
    """
    用户确认节点：展示 param_body，等待用户 yes / 修改参数 / 自然语言修改。
    外部调用时，先读取 state["param_body"] 展示给用户；
    用户回复后，把修改后的参数写回 state["param_body"]，state["user_confirmed"]=True，
    再次调用 graph.invoke(state) 继续流转。
    """
     # 自动重试轮：不打断用户，直接放行
    if (state.get("retry_count") or 0) > 0:
        return {
            "user_confirmed": True,
            "status": "running",
            "logs": state.get("logs", []) + [{
                "event": "user_confirm_auto_passed",
                "retry_count": state.get("retry_count"),
            }],
        }

    param_body = state.get("param_body", {})
    user_confirmed = state.get("user_confirmed", False)

    if not user_confirmed:
        return {
            "status": "blocked",
            "logs": state["logs"] + [{
                "event": "user_confirm_pending",
                "param_body": param_body,
            }],
        }
    
    user_reply = interrupt({
        "event": "user_confirm_pending",
        "param_body": param_body,
        "message": "请确认以下参数体。回复 yes 执行，或用自然语言修改（如：把 start_date 改成 20230601）",
    })

    if not user_reply or str(user_reply).strip().lower() in ("yes", "y", "确认", "ok"):# 直接确认，不修改

        return {
            "user_confirmed": True,
            "status": "running",
            "logs": state["logs"] + [{"event": "user_confirm_passed"}],
        }
    
    llm = llm_client()
    prompt = (
        f"用户要求修改以下参数：\n"
        f"当前参数：{json.dumps(param_body, ensure_ascii=False)}\n"
        f"用户修改要求：{user_reply}\n\n"
        f"请返回 JSON patch，只包含需要修改的字段，格式：{{\"field_name\": \"new_value\"}}"
    )
    response = llm.chat([{"role": "user", "content": prompt}])
    patch_match = re.search(r'\{[^{}]*\}', response)
    patch = json.loads(patch_match.group()) if patch_match else {}

    
    # 应用 patch
    param_body = dict(param_body)
    param_body.update(patch)

    return {
        "param_body": param_body,
        "user_confirmed": True,
        "status": "running",
        "logs": state["logs"] + [
            {"event": "user_confirm_modified", "patch": patch},
            {"event": "user_confirm_passed"},
        ],
    }