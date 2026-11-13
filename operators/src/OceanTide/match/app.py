from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from func_GLSY_ALT_GDR_AUX_YCZ_MATCH import func_ycz_matching_pro

app = FastAPI()

class Item(BaseModel):
    Sat_ID: str
    Data_version: str
    AUX_YCZ: str
    Product_Type: str
    Start_date: str
    End_date: str
    MSS_PATH: str
    FES2014_PATH: str
    order_id: str
    input: str          # 主卫星输入目录
    input_AUX: str      # 辅助验潮站输入目录
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None

@app.post("/ycz/match")
def get_item(item: Item):
    res = func_ycz_matching_pro(item)
    return res
