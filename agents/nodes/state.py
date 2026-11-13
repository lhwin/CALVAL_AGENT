"""
LangGraph State Management for Cal/Val Agent.
"""

from typing import Annotated, Dict, Any, Optional
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    """LangGraph state for calibration workflow."""
    
    # Input/Planning
    task_text: Annotated[str, "Natural language task description"]
    parsed_task: Annotated[Optional[Dict[str, Any]], "Structured task"]
    param_body: Annotated[Optional[Dict[str, Any]], "参数体，供用户确认后执行"]
    user_confirmed: Annotated[bool, "用户是否已确认参数体"] = False,
    
    # Data Discovery
    available_datasets: Annotated[list, "Discovered datasets on server/local"]
    selected_data: Annotated[Optional[Dict[str, Any]], "Selected data for processing"]
    metadata: Annotated[Optional[Dict[str, Any]], "Discovery metadata (e.g., next_step)"]
    
    # Recommendation
    recommendation: Annotated[Optional[Dict[str, Any]], "Method recommendation"]
    
    # Operator Execution
    current_operator: Annotated[Optional[str], "Active operator type"]
    operator_config: Annotated[Optional[Dict[str, Any]], "Operator configuration"]
    operator_result: Annotated[Optional[Dict[str, Any]], "Latest operator output"]
    
    # Branching Logic
    branch_path: Annotated[Optional[str], "Selected execution branch"]
    fallback_needed: Annotated[bool, "Whether fallback is required"]
    retry_count: Annotated[int, "Number of retry attempts"]
    
    # Outputs
    results: Annotated[list, "Final calibration results"]
    logs: Annotated[list, "Execution log entries"]
    
    # System
    messages: Annotated[list[AnyMessage], "Conversation messages"]
    status: Annotated[str, "pending|running|success|failed|blocked"]