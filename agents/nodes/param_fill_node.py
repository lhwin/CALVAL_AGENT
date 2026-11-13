from agents.nodes.state import AgentState

def param_fill_node(state: AgentState) -> AgentState:
    """参数体填充节点：根据方法自动读取 pipeline 参数模板并填充"""
    parsed = state.get("parsed_task", {})
    metadata = state.get("metadata") or {}
    data_summary = metadata.get("data_summary", {})
    selected_data = state.get("selected_data") or {}
    available_datasets = state.get("available_datasets", [])

    method = parsed.get("method")
    sat_id = parsed.get("primary_sat", "UNKNOWN")
    aux_type = parsed.get("aux_data_type", "UNKNOWN")
    start_date = parsed.get("start_date", "20230101")
    end_date = parsed.get("end_date", "20231231")

    # 确定 input / input_AUX 目录
    primary_input_dir = ""
    aux_input_dir = ""

    # 从 available_datasets 查找对应卫星目录
    for ds in available_datasets:
        if ds.get("sat_id", "").upper() == sat_id.upper():
            primary_input_dir = ds.get("path", "") or ds.get("input_dir", "")
        elif ds.get("sat_id", "").upper() == aux_type.upper():
            aux_input_dir = ds.get("path", "") or ds.get("input_dir", "")

    if not primary_input_dir and selected_data:
        primary_input_dir = selected_data.get("path", "") or selected_data.get("input_dir", "")
    if not aux_input_dir:
        aux_input_dir = primary_input_dir

    # 根据方法构建参数体
    param_body = {}

    if method == "star_cross":
        param_body = {
            "Sat_ID": sat_id,
            "AUX_Sat": aux_type,
            "Data_version": "V001",
            "Match_Data_Type": aux_type,
            "Product_Type": "SSH",
            "Start_date": start_date,
            "End_date": end_date,
            "Match_time": "2.0",
            "Template_docx": "",
            "order_id": "0",
            "input": primary_input_dir,
            "input_AUX": aux_input_dir,
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_STAR_CROSS_MATCH_RESULT",
            "proc_name": "gl_ssh_cross_match_pro",
            "version": "1.0",
            "Select_Area": "[-60,60,-180,180]",
            "distance_to_coast": 50,
            "ocean_depth": 1000,
            "wind_speed": "[0,40]",
        }
    elif method == "self_cross":
        param_body = {
            "Sat_ID": sat_id,
            "Data_version": "V001",
            "Product_Type": "SSH",
            "Start_date": start_date,
            "End_date": end_date,
            "Match_time": "2.0",
            "Template_docx": "",
            "order_id": "0",
            "input": primary_input_dir,
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_SELF_CROSS_MATCH_RESULT",
            "proc_name": "gl_ssh_self_cross_match_pro",
            "version": "1.0",
            "Select_Area": "[-60,60,-180,180]",
            "distance_to_coast": 50,
            "ocean_depth": 1000,
            "wind_speed": "[0,40]",
        }
    elif method == "sig0_cross":
        param_body = {
            "Sat_ID": sat_id,
            "AUX_Sat": aux_type,
            "Data_version": "V001",
            "Product_Type": "SIG0",
            "Start_date": start_date,
            "End_date": end_date,
            "Match_time": "2.0",
            "Template_docx": "",
            "order_id": "0",
            "input": primary_input_dir,
            "input_AUX": aux_input_dir,
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_SIG0_CROSS_MATCH_RESULT",
            "proc_name": "gl_ssh_sig0_cross_match_pro",
            "version": "1.0",
        }
    elif method in ("ycz_match", "tide_ext"):
        tide_summary = data_summary.get("tide_summary", {})
        param_body = {
            "Sat_ID": sat_id,
            "Data_version": "V001",
            "Product_Type": "SSH",
            "Start_date": start_date,
            "End_date": end_date,
            "order_id": "0",
            "operation_type": "match",
            "input": primary_input_dir,
            "input_AUX": selected_data.get("wstg_dir", "") if selected_data else "",
            "AUX_YCZ": selected_data.get("wstg_dir", "zhiwan") if selected_data else "zhiwan",
            "MSS_PATH": tide_summary.get("mss_path", "") or selected_data.get("mss_path", "") if selected_data else "",
            "FES2014_PATH": tide_summary.get("fes2014_path", "") or selected_data.get("fes2014_path", "") if selected_data else "",
            "output": f"output_local_test/{method}_0",
            "outputFileType": "GL_SSH_YCZ_MATCH_RESULT",
            "proc_name": "gl_ssh_ycz_match_pro",
            "version": "1.0",
        }
    else:
        param_body = {
            "Sat_ID": sat_id,
            "AUX_Sat": aux_type,
            "Start_date": start_date,
            "End_date": end_date,
            "input": primary_input_dir,
            "input_AUX": aux_input_dir,
            "output": f"output_local_test/{method}_0",
        }

    return {
        "param_body": param_body,
        "status": "awaiting_user_confirm",
        "logs": state["logs"] + [{"event": "param_filled", "method": method, "param_keys": list(param_body.keys())}],
    }
