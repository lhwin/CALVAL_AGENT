"""算子配置基类。"""
from pydantic import BaseModel
from typing import Optional

class LocalConfig(BaseModel):
    """本地算子配置基类。"""
    sat_id: str
    aux_data_type: Optional[str] = None
    start_date: str
    end_date: str
    output_dir: str
    input_dir: str
    aux_input_dir: Optional[str] = None
    yz_data_dir: Optional[str] = None
    mss_path: Optional[str] = None
    fes2014_path: Optional[str] = None
