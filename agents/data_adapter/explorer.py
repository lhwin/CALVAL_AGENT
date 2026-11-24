"""数据探索器，扫描卫星数据和潮汐站数据。"""
import os
import re
from typing import Dict, List, Optional, Tuple


# 验潮站文件名前缀 -> 站名 key（与 OceanTide 算子 stations_config 的 key 一致）
_STATION_ALIAS = {
    "zhiwanwharf": "zhiwan",
    "danganwharf": "dangan",
    "wailingdingwharf": "wailingding",
}


# OceanTide MATCH 算子必需的分潮文件（缺任一个都无法跑通）
_FES_REQUIRED = ["m2", "s2", "n2", "k2", "k1", "o1", "p1", "q1", "m4", "m6"]


class LocalDataExplorer:
    def __init__(self, satelite_dir: str, ocean_tide: str):
        self.satelite_dir = satelite_dir
        self.ocean_tide = ocean_tide

        # 验潮站相关标准路径（由 ocean_tide 根目录推导）
        self.wstg_root = os.path.join(ocean_tide, "WSTG")
        self.fes_dir = os.path.join(ocean_tide, "FES2014", "ocean_tide")
        self.mss_path = os.path.join(ocean_tide, "DTU18MSS_1min.nc")
        self.hy2b_root = os.path.join(ocean_tide, "HY-2BGDR")

    # ─────────────────────── 卫星 ───────────────────────

    def discover_satellite_folders(self) -> List[Dict]:
        """扫描卫星数据文件夹。"""
        sat_folders = []
        for folder in os.listdir(self.satelite_dir):
            folder_path = os.path.join(self.satelite_dir, folder)
            if os.path.isdir(folder_path):
                nc_files = []
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        if file.endswith(".nc"):
                            nc_files.append(os.path.join(root, file))

                if nc_files:
                    sat_id = folder
                    nc_count = len(nc_files)
                    start_date, end_date = self._get_date_range(nc_files)
                    sat_folders.append({
                        "sat_id": sat_id,
                        "path": folder_path,
                        "nc_count": nc_count,
                        "start_date": start_date,
                        "end_date": end_date,
                        "total_size_bytes": sum(os.path.getsize(f) for f in nc_files),
                    })
        return sat_folders

    def _get_date_range(self, files: List[str]) -> Tuple[str, str]:
        """从文件名中提取日期范围。"""
        dates = []
        for file in files:
            match = re.search(r"(\d{8})", os.path.basename(file))
            if match:
                dates.append(match.group(1))

        if dates:
            return min(dates), max(dates)
        return "00000000", "99999999"

    # ─────────────────────── 验潮站 ───────────────────────

    @staticmethod
    def _station_key_from_filename(filename: str) -> Optional[str]:
        """ATG_ZhiwanWharf_20230101.txt -> 'zhiwan'"""
        m = re.match(r"ATG_([A-Za-z]+?)(?:Wharf)?_\d{8}\.txt$", filename, re.IGNORECASE)
        if not m:
            return None
        raw = m.group(1).lower()
        return _STATION_ALIAS.get(raw + "wharf", _STATION_ALIAS.get(raw, raw))

    @staticmethod
    def _date_from_filename(filename: str) -> Optional[str]:
        """ATG_ZhiwanWharf_20230101.txt -> '20230101'"""
        m = re.search(r"_(\d{8})\.txt$", filename)
        return m.group(1) if m else None

    @staticmethod
    def _parse_wstg_header(filepath: str) -> Dict:
        """解析 SONEL 风格头（/begin_header ... /end_header），取站点元信息。"""
        meta = {}
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i > 60:
                        break
                    line = line.strip()
                    if line.startswith("/end_header"):
                        break
                    if line.startswith("/") and "=" in line:
                        k, v = line[1:].split("=", 1)
                        meta[k.strip()] = v.strip()
        except Exception:
            return {}

        def _f(key):
            try:
                return float(meta.get(key))
            except (TypeError, ValueError):
                return None

        return {
            "station": meta.get("station"),
            "latitude": _f("north_latitude"),
            "longitude": _f("east_longitude"),
            "water_depth": meta.get("water_depth"),
            "fields": meta.get("fields"),
            "units": meta.get("units"),
            "start_date": meta.get("start_date"),
            "end_date": meta.get("end_date"),
        }

    def discover_tide_stations(self) -> Dict[str, Dict]:
        """
        扫描 WSTG 下所有验潮站（兼容两种布局）：
          WSTG/<year>/<station>/*.txt
          WSTG/wstg/*.txt
        返回 {station_key: {...统计...}}
        """
        stations: Dict[str, Dict] = {}

        if not os.path.isdir(self.wstg_root):
            return stations

        for root, _dirs, files in os.walk(self.wstg_root):
            txts = [f for f in files if f.lower().endswith(".txt")]
            if not txts:
                continue

            for name in txts:
                key = self._station_key_from_filename(name)
                date = self._date_from_filename(name)
                if not key or not date:
                    continue

                st = stations.setdefault(key, {
                    "files": [],
                    "dirs": set(),
                    "dates": [],
                })
                st["files"].append(os.path.join(root, name))
                st["dirs"].add(root)
                st["dates"].append(date)

        result: Dict[str, Dict] = {}
        for key, st in stations.items():
            dates = sorted(st["dates"])
            dirs = sorted(st["dirs"])

            # 选定主目录：文件数最多的那个目录
            dir_counts = {}
            for fp in st["files"]:
                d = os.path.dirname(fp)
                dir_counts[d] = dir_counts.get(d, 0) + 1
            best_dir = max(dir_counts, key=dir_counts.get)

            # 解析前 3 个文件的头，取到有效经纬度即止（同站元信息一致）
            header = {}
            for fp in st["files"][:3]:
                header = self._parse_wstg_header(fp)
                if header.get("latitude") is not None:
                    break

            result[key] = {
                "station": key,
                "header_station": header.get("station"),
                "lat": header.get("latitude"),
                "lon": header.get("longitude"),
                "water_depth": header.get("water_depth"),
                "fields": header.get("fields"),
                "units": header.get("units"),
                "file_count": len(st["files"]),
                "date_start": dates[0],
                "date_end": dates[-1],
                "year_dirs": dirs,
                "wstg_dir": best_dir,
                "total_size_mb": round(
                    sum(os.path.getsize(f) for f in st["files"]) / 1024 / 1024, 2
                ),
            }
        return result

    def discover_fes2014(self) -> Dict:
        """扫描 FES2014 分潮文件，检查算子必需分潮是否齐全。"""
        if not os.path.isdir(self.fes_dir):
            return {
                "path": self.fes_dir,
                "exists": False,
                "constituents": [],
                "count": 0,
                "required": list(_FES_REQUIRED),
                "required_missing": list(_FES_REQUIRED),
            }

        cons = sorted(
            os.path.splitext(f)[0].lower()
            for f in os.listdir(self.fes_dir)
            if f.lower().endswith(".nc")
        )
        missing = [c for c in _FES_REQUIRED if c not in cons]
        return {
            "path": self.fes_dir,
            "exists": True,
            "constituents": cons,
            "count": len(cons),
            "required": list(_FES_REQUIRED),
            "required_missing": missing,
        }

    def discover_mss(self) -> Dict:
        """检查 DTU18 MSS 平均海面高模型文件。"""
        if not os.path.isfile(self.mss_path):
            return {"path": self.mss_path, "exists": False, "size_mb": 0}
        return {
            "path": self.mss_path,
            "exists": True,
            "size_mb": round(os.path.getsize(self.mss_path) / 1024 / 1024, 1),
        }

    def discover_hy2bgdr(self) -> Dict:
        """按年份统计 HY-2B GDR 文件数与日期范围。"""
        out: Dict[str, Dict] = {}
        if not os.path.isdir(self.hy2b_root):
            return out

        for entry in sorted(os.listdir(self.hy2b_root)):
            year_dir = os.path.join(self.hy2b_root, entry)
            if not os.path.isdir(year_dir) or not entry.isdigit():
                continue
            files = [f for f in os.listdir(year_dir) if f.lower().endswith(".nc")]
            if not files:
                continue
            dates = []
            for f in files:
                dates.extend(re.findall(r"(20\d{6})", f))
            out[entry] = {
                "count": len(files),
                "date_start": min(dates) if dates else None,
                "date_end": max(dates) if dates else None,
                "path": year_dir,
            }
        return out

    def recommend_station(self, start_date: str = None, end_date: str = None,
                          stations: Dict[str, Dict] = None) -> Optional[str]:
        """
        按任务日期范围推荐验潮站：
        统计各站在 [start_date, end_date] 内的可用日文件数，取最多者；
        并列时优先 zhiwan（常用主站）。
        """
        if stations is None:
            stations = self.discover_tide_stations()
        if not stations:
            return None

        def overlap_count(st: Dict) -> int:
            if not start_date or not end_date:
                return st["file_count"]
            cnt = 0
            for d in st["year_dirs"]:
                if not os.path.isdir(d):
                    continue
                for name in os.listdir(d):
                    fd = self._date_from_filename(name)
                    if fd and start_date <= fd <= end_date:
                        cnt += 1
            return cnt

        scored = [(overlap_count(st), key == "zhiwan", key) for key, st in stations.items()]
        scored.sort(reverse=True)
        best_cnt, _pref, best_key = scored[0]

        if best_cnt == 0:
            # 日期范围内无数据，退回总文件数最多的站
            return max(stations.items(), key=lambda kv: kv[1]["file_count"])[0]
        return best_key

    def find_tide_data(self) -> List[Dict]:
        """扫描潮汐站数据，返回每个站的详细统计（含可直接作为 input_AUX 的目录）。"""
        stations = self.discover_tide_stations()
        return [
            {
                "station": key,
                "path": st["wstg_dir"],
                "wstg_dir": st["wstg_dir"],
                "nc_count": 0,
                "txt_count": st["file_count"],
                "date_start": st["date_start"],
                "date_end": st["date_end"],
                "lat": st["lat"],
                "lon": st["lon"],
                "water_depth": st["water_depth"],
                "total_size_mb": st["total_size_mb"],
            }
            for key, st in stations.items()
        ]

    # ─────────────────────── 汇总 ───────────────────────

    def discover_data(self) -> Dict:
        """综合扫描卫星和潮汐数据。"""
        sat_folders = self.discover_satellite_folders()
        stations = self.discover_tide_stations()
        fes = self.discover_fes2014()
        mss = self.discover_mss()
        hy2b = self.discover_hy2bgdr()

        report = {
            "satellite": [],
            "tide": [],
            "satellite_stats": {},
            "matched_sats": [],
            "total_nc_files": 0,
            "total_txt_files": 0,
            "tide_summary": {},
        }

        for folder in sat_folders:
            report["satellite"].append(folder)
            report["satellite_stats"][folder["sat_id"]] = {
                "nc_count": folder["nc_count"],
                "start_date": folder["start_date"],
                "end_date": folder["end_date"],
            }
        report["matched_sats"] = [f["sat_id"] for f in report["satellite"]]
        report["total_nc_files"] = sum(f["nc_count"] for f in report["satellite"])

        for item in self.find_tide_data():
            report["tide"].append(item)
            report["total_txt_files"] += item["txt_count"]

        total_txt = sum(st["file_count"] for st in stations.values())

        report["tide_summary"] = {
            # —— 兼容旧字段（其它节点/前端仍在用）——
            "nc_count": 0,
            "txt_count": total_txt,
            "has_wstg": bool(stations),
            "has_fes2014": fes["exists"],
            "has_mss": mss["exists"],

            # —— 验潮站详情 ——
            "wstg_root": self.wstg_root,
            "stations": stations,
            "station_count": len(stations),
            "station_names": sorted(stations.keys()),
            "recommended_station": self.recommend_station(stations=stations),

            # —— 辅助模型数据 ——
            "mss_path": mss["path"] if mss["exists"] else "",
            "mss_info": mss,
            "fes2014_path": fes["path"] if fes["exists"] else "",
            "fes2014_info": fes,

            # —— HY-2B GDR ——
            "hy2bgdr_root": self.hy2b_root,
            "hy2bgdr": hy2b,
        }

        report["tide_summary"]["data_describe"] = self._describe_tide(report["tide_summary"])
        return report

    @staticmethod
    def _describe_tide(ts: Dict) -> str:
        """把验潮站统计整理成给 LLM 阅读的文字摘要。"""
        lines = []
        if ts.get("stations"):
            lines.append(f"验潮站共 {ts.get('station_count', 0)} 个：")
            for key, st in ts["stations"].items():
                lines.append(
                    f"  - {key}（{st.get('header_station') or '-'}）"
                    f"纬度 {st.get('lat')} 经度 {st.get('lon')}，"
                    f"{st.get('file_count')} 个日文件，"
                    f"{st.get('date_start')}~{st.get('date_end')}，"
                    f"{st.get('total_size_mb')} MB"
                )
        else:
            lines.append("无验潮站数据。")

        if ts.get("hy2bgdr"):
            parts = [f"{y}年{v.get('count')}个" for y, v in sorted(ts["hy2bgdr"].items())]
            lines.append("HY-2B GDR：" + "，".join(parts))
        else:
            lines.append("无 HY-2B GDR 数据。")

        fes = ts.get("fes2014_info") or {}
        if fes.get("exists"):
            missing = fes.get("required_missing") or []
            lines.append(
                f"FES2014 分潮 {fes.get('count')} 个"
                + (f"，缺少必需分潮：{','.join(missing)}" if missing else "，必需分潮齐全")
            )
        else:
            lines.append("FES2014 缺失。")

        mss = ts.get("mss_info") or {}
        lines.append(
            f"DTU18 MSS {'已就绪' if mss.get('exists') else '缺失'}"
            + (f"（{mss.get('size_mb')} MB）" if mss.get('exists') else "")
        )

        if ts.get("recommended_station"):
            lines.append(f"推荐验潮站：{ts['recommended_station']}")
        return "\n".join(lines)