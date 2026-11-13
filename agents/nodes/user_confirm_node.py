from agents.nodes.state import AgentState

def user_confirm_node(state: AgentState) -> AgentState:
    """
    用户确认节点：展示 param_body，等待用户 yes / 修改参数 / 自然语言修改。
    外部调用时，先读取 state["param_body"] 展示给用户；
    用户回复后，把修改后的参数写回 state["param_body"]，state["user_confirmed"]=True，
    再次调用 graph.invoke(state) 继续流转。
    """
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

    return {
        "status": "running",
        "logs": state["logs"] + [{"event": "user_confirm_passed"}],
    }