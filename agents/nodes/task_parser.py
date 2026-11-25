"""
Task Parser - 用大模型解析用户自然语言，提取结构化任务信息。
优先 LLM, 失败则 regex 兜底。
"""
from typing import Dict, Any, Optional
import re
import json
from agents.nodes.llm_client import LLMClient

def parse_task(text: str, data_summary: Dict[str, Any] = None) -> Dict[str, Any]:
    result = {
        "method": None,
        "primary_sat": None,
        "aux_data_type": None,
        "start_date": None,
        "end_date": None,
        "select_area": None,
        "distance_to_coast": None,
        "ocean_depth": None,
        "wind_speed": None,
        "match_time": None,
        "task_text": text,
    }

    # 优先 LLM
    try:
        llm_result = _parse_with_llm(text, data_summary)
        if llm_result:
            for key in ["method", "primary_sat", "aux_data_type", "start_date", "end_date"]:
                if llm_result.get(key):
                    result[key] = llm_result[key]
    except Exception as e:
        print(f"[LLM parse failed, using regex fallback: {e}]")

    # regex 兜底
    result = _merge_regex(result, text)

    # 日期合理性校验：LLM 没看到数据范围时会瞎填，这里用真实数据范围纠正
    warn = _validate_date_range(result, data_summary)
    if warn:
        result["_warning"] = warn
    return result


def _validate_date_range(result: Dict[str, Any], data_summary: Optional[Dict[str, Any]] = None) -> str:
    """用 data_summary 里的真实卫星数据范围校验 start/end_date，越界则纠正并返回提示。"""
    if not data_summary:
        return ""
    stats = data_summary.get("satellite_stats") or {}
    if not stats:
        return ""

    sat = result.get("primary_sat")
    st = stats.get(sat) if sat else None
    if not st:
        # 退而求其次：取所有卫星里覆盖最广的范围
        ranges = [(v.get("start_date"), v.get("end_date")) for v in stats.values()
                  if v.get("start_date") and v.get("end_date")]
        if not ranges:
            return ""
        ranges.sort()
        real_start, real_end = ranges[0][0], ranges[-1][1]
    else:
        real_start, real_end = st.get("start_date"), st.get("end_date")
    if not real_start or not real_end:
        return ""

    sd, ed = result.get("start_date"), result.get("end_date")
    if not sd or not ed:
        return f"数据可用范围 {real_start}~{real_end}，但任务未给出日期，请补充。"

    notes = []
    if sd < real_start or sd > real_end:
        result["start_date"] = real_start
        notes.append(f"start_date {sd} 超出数据范围，已改为 {real_start}")
    if ed < real_start or ed > real_end:
        result["end_date"] = real_end
        notes.append(f"end_date {ed} 超出数据范围，已改为 {real_end}")
    if result["start_date"] > result["end_date"]:
        result["start_date"], result["end_date"] = real_start, real_end
        notes.append("起止日期颠倒，已重置为数据范围")
    return "；".join(notes)



def _parse_with_llm(text: str, data_summary: Dict[str, Any] = None) -> Dict[str, Any]:
    """调用 LLM 解析，返回结构化 dict，并结合数据分析结果推荐日期。"""
    llm = LLMClient()

    
    # 构建数据分析结果的上下文信息
    data_context = data_summary.get("data_describe", "无数据统计信息") if data_summary else "无数据统计信息"
   

    system_prompt = """你是一个卫星高度计定标任务解析器。请从用户自然语言中提取结构化信息，并结合可用数据范围推荐合理的时间段。
请严格返回 JSON：
- method: star_cross / self_cross / sig0_cross / tide_ext
- primary_sat: 主卫星ID（如 S6A）
- aux_data_type: 辅助卫星ID（星间交叉需要）
- start_date: YYYYMMDD（根据数据范围推荐）
- end_date: YYYYMMDD（根据数据范围推荐）
- select_area: [min_lat, max_lat, min_lon, max_lon]（可选）
- distance_to_coast: km（可选）
- ocean_depth: m（可选）
- wind_speed: [min, max]（可选）
- match_time: 小时（可选）
"""

    prompt = f"""用户任务：{text}

{data_context}

请根据用户任务和可用数据范围，返回 JSON："""

    response = llm.chat([{"role": "user", "content": prompt}], system_prompt=system_prompt)
    
    json_str = re.sub(r'^[^{]*', '', response)
    json_str = re.sub(r'[^}]*$', '', json_str)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {"method": None, "start_date": None, "end_date": None}


def _merge_regex(result: Dict[str, Any], text: str) -> Dict[str, Any]:
    """regex 兜底补全缺失字段。"""
    text_lower = text.lower()

    # 方法
    if not result.get("method"):
        if any(kw in text for kw in ["自交叉", "self"]):
            result["method"] = "self_cross"
        elif any(kw in text for kw in ["交叉", "cross"]):
            result["method"] = "star_cross"
        elif any(kw in text for kw in ["验潮", "tide"]):
            result["method"] = "tide_ext"
        elif any(kw in text for kw in ["sig0"]):
            result["method"] = "sig0_cross"

    # 卫星ID
    sat_patterns = [r"(S6[A-Z])", r"(JA[0-9])", r"(HY-\d+[A-Z]?)", r"(Sentinel[-]?[36])", r"(Cryosat[-]?\d?)"]
    satellites = []
    for pat in sat_patterns:
        for m in re.findall(pat, text, re.I):
            if m not in satellites:
                satellites.append(m)
    if satellites:
        if not result.get("primary_sat"):
            result["primary_sat"] = satellites[0]
        if not result.get("aux_data_type") and len(satellites) > 1:
            result["aux_data_type"] = satellites[1]

    # 日期
    cn_date = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(?:(\d{1,2})日)?", text)
    if cn_date:
        y, m, d = cn_date.groups()
        result["start_date"] = f"{y}{m.zfill(2)}{(d or '01').zfill(2)}"
        result["end_date"] = result["start_date"]

    return result
