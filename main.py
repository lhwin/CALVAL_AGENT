from agents.workflow import create_workflow
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
import json

config = {"configurable": {"thread_id": "calval_001"}}

graph = create_workflow(checkpointer=MemorySaver())

initial_state = {
    "task_text": "做一下星间交叉",
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
    "mode": "local"
}

# 第一步：运行到 user_confirm 暂停
result = graph.invoke(initial_state, config)
# suggest = result["__interrupt__"][0].value["messages"]
suggest_command = input("sugges : ")

result = graph.invoke(Command(resume=suggest_command), config=config)

# 用户确认后，再次 invoke：应该走到 execute_operator
print(result["param_body"])
user_confirmed = input("任务参数如下 请确认？(y/n): ")
graph.update_state(config, {"user_confirmed": user_confirmed})
result2 = graph.invoke(None, config)
print("status after second invoke:", result2.get("status"))
print("operator_result:", json.dumps(result2.get("operator_result", {}), indent=2, ensure_ascii=False) if result2.get("operator_result") else "operator_result is None")
  
# 向用户展示 param_body
print(f"match result {result2}")