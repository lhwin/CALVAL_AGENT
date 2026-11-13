from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from func_GLSY_ALT_GDR_AUX_SAT_MATCH import func_self_cross_matching_pro

app = FastAPI()

class Item(BaseModel):
    Sat_ID: str
    Data_version: str
    Product_Type: str
    Start_date: str
    End_date: str
    Match_time: str
    Template_docx: str
    order_id: str
    input: str                          # 输入目录（NC/H5），单输入
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None
    Select_Area: Optional[str] = None
    distance_to_coast: Optional[int] = None
    ocean_depth: Optional[int] = None
    wind_speed: Optional[str] = None

@app.post("/selfcross/selfmatch")
def get_item(item: Item):
    res = func_self_cross_matching_pro(item)
    return res
