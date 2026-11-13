from agents.workflow import create_workflow

graph = create_workflow()

initial_state = {
    "task_text": "用 S6A 和 JA3 做 2023 年 5 月的星间交叉",
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
}

# 第一步：运行到 user_confirm 暂停

state = graph.invoke(initial_state)

# 向用户展示 param_body

print("建议参数：")
print(state["param_body"])
print("请回复：yes（默认执行） 或 修改后的参数 / 自然语言修改")

# 用户回复后，外部处理：

# 用户说 "yes"：

state["user_confirmed"] = True
state["status"] = "running"
state = graph.invoke(state)  
# 继续执行


# 用户说 "把 start_date 改成 20230601"：

state["param_body"]["Start_date"] = "20230601"
state["user_confirmed"] = True
state["status"] = "running"
state = graph.invoke(state)