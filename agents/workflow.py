from langgraph.graph import StateGraph, START, END

"""
LangGraph 工作流 - 完整校准/验证 Agent 编排。
用法:
    from workflow import create_workflow
    graph = create_workflow()
    result = graph.invoke({"task_text": "用 S6A 和 JA3 做星间交叉"})
"""
from typing import Dict, Any, Optional, Literal
from pathlib import Path
from langgraph.graph import StateGraph, END
from agents.nodes.state import AgentState
# from agents.nodes.task_parser import parse_task
from agents.data_adapter.explorer import LocalDataExplorer
import yaml
from agents.nodes.task_parser_node import task_parser_node
from agents.nodes.data_discovery_node import data_discovery_node
from agents.nodes.execute_operator_node import execute_operator_node
from agents.nodes.method_recommendation_node import method_recommendation_node
from agents.nodes.param_fill_node import param_fill_node
from agents.nodes.user_confirm_node import user_confirm_node

def create_workflow(debug: bool = False):
    """创建工作流图。"""
    graph_builder = StateGraph(AgentState)
    nodes = {
        "task_parser": task_parser_node,
        "data_discovery": data_discovery_node,
        "method_recommendation": method_recommendation_node,
        "param_fill": param_fill_node,
        "user_confirm": user_confirm_node,
        "execute_operator": execute_operator_node,
    }
    for name, func in nodes.items():
        graph_builder.add_node(name, func)

    graph_builder.set_entry_point("data_discovery")
    graph_builder.add_edge("data_discovery", "task_parser")

    def route_after_task_parser(state: AgentState) -> Literal["method_recommendation", "param_fill"]:
        branch = state.get("branch_path", "need_method_recommendation")
        if branch == "need_method_recommendation":
            return "method_recommendation"
        # task_parser 已有 method 且字段齐全，跳过推荐节点；保留 task_parser 写入的 recommendation，避免 param_fill 拿不到
        return "param_fill"

    graph_builder.add_conditional_edges(
        "task_parser",
        route_after_task_parser,
        {
            "method_recommendation": "method_recommendation",
            "param_fill": "param_fill",
        },
    )

    graph_builder.add_edge("method_recommendation", "param_fill")
    graph_builder.add_edge("param_fill", "user_confirm")

    def route_after_confirm(state: AgentState) -> Literal["execute_operator"]:
        if state.get("user_confirmed", False):
            return "execute_operator"
        return "execute_operator"  
# blocked 状态由外部控制，此处不跳


    graph_builder.add_conditional_edges(
        "user_confirm",
        route_after_confirm,
        {"execute_operator": "execute_operator"},
    )

    graph_builder.add_conditional_edges(
        "execute_operator",
        lambda s: END,
        {END: END},
    )

    return graph_builder.compile()

workflow_graph = create_workflow()
