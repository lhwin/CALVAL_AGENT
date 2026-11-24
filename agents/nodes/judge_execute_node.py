from agents.nodes.state import AgentState
from langgraph.types import interrupt
from agents.nodes.llm_client import LLMClient
import re
import json

def judge_execute_node(state: AgentState) -> AgentState:
    text = state.get("task_text", "")
    data_summary = state.get("metadata", {}).get("data_summary", {})

    llm = LLMClient()

    judge_prompt = f"""
    下面是我们的数据统计结果
    data_summary: {data_summary["data_describe"] if data_summary else "无数据统计信息"}
    这是用户任务：{text},请根据数据统计结果，判断用户任务 现有数据是否可执行，是否需要用户确认，是否需要推荐方法。请返回 JSON 格式，包含以下字段：
    - "can_execute": true/false,  # 是否可以直接执行
    - "reason": "如果不能执行，请给出原因，否则为空",
    - "suggest": "如果需要修改，请给出修改建议，否则为空",
    """
    judge_res = llm.chat([{"role": "user", "content": judge_prompt}])
    json_str = re.sub(r'^[^{]*', '', judge_res)
    json_str = re.sub(r'[^}]*$', '', json_str)
    res = json.loads(json_str) if json_str else {}
    if not res["can_execute"]:
        user_reply = interrupt({
        "event": "user_confirm_pending",
        "messages": f"任务无法直接执行，原因：{res.get('reason', '未知')}\n 如果不继续执行 请按y 如果需要继续执行给出修改意见",
        })

        if user_reply == "y":
           return {"can_execute": False}
        
        else:
            suggest_prompt = f"这是我们原有的任务\n{text} \
                这是目前无法执行的原因 \n{res.get('reason')} \n \
                    这是目前的用户修改意见 {user_reply} 请你根据 这三条 重写用户的 任务描述"
            
            new_task = llm.chat(suggest_prompt)
            return {"task_text": new_task, "can_execute": True}
    else:
        return {"can_execute": True}


