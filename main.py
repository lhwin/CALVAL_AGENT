from agents.workflow import create_workflow
from langgraph.checkpoint.memory import MemorySaver
import json

config = {"configurable": {"thread_id": "calval_001"}}

graph = create_workflow(checkpointer=MemorySaver())

initial_state = {
    "task_text": "I want 做一下 星间交叉",
    "parsed_task": None,
    "param_body": None,
    "user_confirmed": False,
    "missing_fields": [],
    "branch_path": None,
    "available_datasets": [],
    "selected_data": None,
    "metadata": None,
    "recommendation": None,
    "operator_result": None,
    "logs": [],
    "status": "pending",
    "mode": "remote"
}

# 第一步：运行到 user_confirm 暂停
result = graph.invoke(initial_state, config)
print("status after first invoke:", result.get("status"))
print("branch_path:", result.get("branch_path"))
print("recommendation:", result.get("recommendation"))

# 用户确认后，再次 invoke：应该走到 execute_operator
graph.update_state(config, {"user_confirmed": True})
result2 = graph.invoke(None, config)
print("status after second invoke:", result2.get("status"))
print("operator_result:", json.dumps(result2.get("operator_result", {}), indent=2, ensure_ascii=False) if result2.get("operator_result") else "operator_result is None")

# 向用户展示 param_body
print(f"match result {result}")