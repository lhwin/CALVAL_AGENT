from agents.nodes.state import AgentState
from agents.data_adapter.explorer import LocalDataExplorer
import yaml
from core.utils.utils import request_data

from agents.nodes.llm_client import LLMClient

def describe_data_summary(data_summary: dict) -> str:
    """生成数据统计信息的描述文本。"""
    satellite_stats = data_summary.get("satellite_stats", {})
    tide_summary = data_summary.get("tide_summary", {})

    description = "数据统计信息:\n"

    # --- 卫星部分（保持不变） ---
    if satellite_stats:
        description += "卫星数据:\n"
        for sat_id, stats in satellite_stats.items():
            file_count = stats.get("nc_count", "未知")
            start_date = stats.get('start_date', '未知')
            end_date = stats.get('end_date', '未知')
            description += f"  - 卫星 {sat_id}: {file_count} 个文件，时间范围 {start_date} - {end_date}\n"
    else:
        description += "无卫星数据。\n"

    # --- 验潮站部分（重写） ---
    if tide_summary:
        description += "验潮站数据:\n"

        # 优先用 explorer 生成的整段文字
        if tide_summary.get("data_describe"):
            description += tide_summary["data_describe"]
        else:
            # 旧版/远程 tide_summary 的降级处理
            stations = tide_summary.get("stations") or {}
            if stations:
                description += f"  共 {len(stations)} 个验潮站：\n"
                for key, st in stations.items():
                    description += (
                        f"    - {key}（{st.get('header_station') or '-'}）"
                        f"纬度 {st.get('lat')} 经度 {st.get('lon')}，"
                        f"{st.get('file_count', 0)} 个日文件，"
                        f"{st.get('date_start')}~{st.get('date_end')}，"
                        f"{st.get('total_size_mb')} MB\n"
                    )
                if tide_summary.get("recommended_station"):
                    description += f"    推荐验潮站：{tide_summary['recommended_station']}\n"
            else:
                description += f"  NC 文件 {tide_summary.get('nc_count', 0)} 个，TXT 文件 {tide_summary.get('txt_count', 0)} 个（未解析出站点信息）\n"

            hy2b = tide_summary.get("hy2bgdr") or {}
            if hy2b:
                parts = [f"{y} 年 {v.get('count')} 个" for y, v in sorted(hy2b.items())]
                description += "  HY-2B GDR：" + "，".join(parts) + "\n"

            fes = tide_summary.get("fes2014_info") or {}
            if fes.get("exists"):
                missing = fes.get("required_missing") or []
                description += (
                    f"  FES2014 分潮 {fes.get('count')} 个"
                    + (f"，缺少必需分潮 {','.join(missing)}" if missing else "，必需分潮齐全") + "\n"
                )
            else:
                description += "  FES2014：缺失\n"

            mss = tide_summary.get("mss_info") or {}
            description += (
                "  DTU18 MSS："
                + (f"就绪（{mss.get('size_mb')} MB）" if mss.get("exists") else "缺失") + "\n"
            )
    else:
        description += "无验潮站数据。\n"

    return description

def data_discovery_node(state: AgentState) -> AgentState:
    """扫描卫星数据和潮汐站数据，生成统计信息。"""
    llm = LLMClient()
    try:
        with open("config/settings.yaml", "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        if state["mode"] == "local":
            
            data = data["localdata"]
            explorer = LocalDataExplorer(data["satelite"], data["ocean_tide"])
            report = explorer.discover_data()
        elif state["mode"] == "remote":
            config = data["serverdata"]
            satelite_dir = config["satelite"]
            oceantide_dir = config["oceantide"]
            item_data = {
                    "satelite_dir": satelite_dir,
                    "oceantide_dir": oceantide_dir
                }
            api_address = config["api_address"]+"/data/discover"
            report = request_data(api_address, item_data)

        data_describe = describe_data_summary(report)
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
        "data_describe": data_describe
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