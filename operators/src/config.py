from pydantic import BaseModel
from typing import Optional, Literal

class SelfCrossItem(BaseModel):
    """自交叉比对项目（合并Match和Cal）"""
    Sat_ID: str
    Data_version: str
    Product_Type: str
    Start_date: str
    End_date: str
    Match_time: str
    Template_docx: str
    order_id: str
    input: str
    # operation_type: Literal["match", "cal"]
    # 可选字段
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None
    Select_Area: Optional[str] = None
    distance_to_coast: Optional[int] = None
    ocean_depth: Optional[int] = None
    wind_speed: Optional[str] = None
    # CAL特有字段
    input_AUX: Optional[str] = None

class StarCrossItem(BaseModel):
    """星间交叉比对项目"""
    Sat_ID: str
    Data_version: str
    AUX_Sat: str
    Match_Data_Type: str 
    Product_Type: str
    Start_date: str
    End_date: str
    Match_time: str
    Template_docx: str
    order_id: str
    # 必填目录
    input: str        # 主卫星输入目录
    input_AUX: str    # 辅助卫星输入目录
    # 添加可选字段
    Select_Area: Optional[str] = None
    distance_to_coast: Optional[int] = None
    ocean_depth: Optional[int] = None
    wind_speed: Optional[str] = None
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None

class Sig0CrossItem(BaseModel):
    """Sigma0交叉比对项目（合并Match和Cal）"""
    Sat_ID: str
    Data_version: str
    AUX_Sat: str
    Product_Type: str
    Start_date: str
    End_date: str
    order_id: str
    operation_type: Literal["match", "cal"]
    # Match特有字段
    Match_time: Optional[str] = None
    Template_docx: Optional[str] = None
    input: str
    input_AUX: str
    # Cal特有字段
    Match_Data_Type: Optional[str] = None
    template_doc: Optional[str] = None
    # 可选字段
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None

class OceanTideItem(BaseModel):
    """海洋潮汐项目（合并Match和Cal）"""
    Sat_ID: str
    Data_version: str
    Product_Type: str
    Start_date: str
    End_date: str
    order_id: str
    # operation_type: Literal["match", "cal"]
    # Match特有字段
    AUX_YCZ: Optional[str] = None
    MSS_PATH: Optional[str] = None
    FES2014_PATH: Optional[str] = None
    input: str
    input_AUX: str
    # Cal特有字段
    Match_Data_Type: Optional[str] = None
    Template_docx: Optional[str] = None
    # 可选字段
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None