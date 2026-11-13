"""数据探索器，扫描卫星数据和潮汐站数据。"""
import os
import re
from typing import Dict, List
from datetime import datetime

class LocalDataExplorer:
    def __init__(self, satelite_dir: str, ocean_tide: str):
        self.satelite_dir = satelite_dir
        self.ocean_tide = ocean_tide

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
                        "nc_files": nc_files,
                        "nc_count": nc_count,
                        "start_date": start_date,
                        "end_date": end_date,
                        "total_size_bytes": sum(os.path.getsize(f) for f in nc_files),
                    })
        return sat_folders

    def find_tide_data(self) -> List[Dict]:
        """扫描潮汐站数据。"""
        tide_datasets = []
        for folder in os.listdir(self.ocean_tide):
            folder_path = os.path.join(self.ocean_tide, folder)
            if os.path.isdir(folder_path):
                nc_files = []
                txt_files = []
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        if file.endswith(".nc"):
                            nc_files.append(os.path.join(root, file))
                        elif file.endswith(".txt"):
                            txt_files.append(os.path.join(root, file))

                if nc_files or txt_files:
                    tide_datasets.append({
                        "path": folder_path,
                        "nc_count": len(nc_files),
                        "txt_count": len(txt_files),
                        "wstg_dir": folder_path,
                    })
        return tide_datasets

    def _get_date_range(self, files: List[str]) -> (str, str):
        """从文件名中提取日期范围。"""
        dates = []
        for file in files:
            match = re.search(r"(\d{8})", file)
            if match:
                dates.append(match.group(1))

        if dates:
            start_date = min(dates)
            end_date = max(dates)
            return start_date, end_date
        return "00000000", "99999999"

    def discover_data(self) -> Dict:
        """综合扫描卫星和潮汐数据。"""
        sat_folders = self.discover_satellite_folders()
        tide_datasets = self.find_tide_data()

        report = {
            "satellite": [],
            "tide": [],
            "satellite_stats": {},
            "matched_sats": [],
            "total_nc_files": 0,
            "total_txt_files": 0,
            "tide_summary": {
                "nc_count": 0,
                "txt_count": 0,
                "has_wstg": False,
                "has_fes2014": False,
                "has_mss": False,
            },
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

        for dataset in tide_datasets:
            report["tide"].append(dataset)
            report["total_txt_files"] += dataset["txt_count"]
            report["tide_summary"]["nc_count"] += dataset["nc_count"]
            report["tide_summary"]["txt_count"] += dataset["txt_count"]
            report["tide_summary"]["has_wstg"] = report["tide_summary"]["txt_count"] > 0

        return report
