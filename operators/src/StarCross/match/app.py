from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Union
from func_GLSY_ALT_GDR_AUX_SAT_MATCH import func_cross_matching_pro
app = FastAPI()

class Item(BaseModel):
    Sat_ID: str
    Data_version: str
    AUX_Sat: str
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

@app.post("/starcross/match")
def get_item(item: Item):
    res = func_cross_matching_pro(item)
    return res
