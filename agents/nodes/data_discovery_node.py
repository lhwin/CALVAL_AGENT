from agents.nodes.state import AgentState
from agents.data_adapter.explorer import LocalDataExplorer
import yaml
def data_discovery_node(state: AgentState) -> AgentState:
    """扫描卫星数据和潮汐站数据，生成统计信息。"""
    try:
        with open("config/settings.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)["data"]

        explorer = LocalDataExplorer(data["satelite"], data["ocean_tide"])
        report = explorer.discover_data()
    except Exception as e:
        return {
            "available_datasets": [],
            "selected_data": None,
            "metadata": {"next_step": None, "data_summary": {}},
            "logs": state["logs"] + [{"event": "discovery_error", "error": str(e)[:200]}],
        }

    # 组装数据统计信息
    data_summary = {
        "satellite_stats": report["satellite_stats"],
        "tide_summary": report["tide_summary"],
        "total_nc_files": report["total_nc_files"],
        "total_txt_files": report["total_txt_files"],
        "matched_sats": report["matched_sats"],
    }

    return {
        "available_datasets": report["satellite"],
        "selected_data": report["satellite"][0] if report["satellite"] else None,
        "metadata": {
            "next_step": "match" if report["satellite"] else None,
            "data_summary": data_summary,
        },
        "logs": state["logs"] + [
            {"event": "datasets_found", "sat_count": len(report["satellite"]), "tide_nc": report["tide_summary"]["nc_count"]}
        ],
    }