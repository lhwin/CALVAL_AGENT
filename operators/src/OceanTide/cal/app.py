from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from func_GLSY_ALT_AUX_YCZ_GDR_CAL import func_ycz_cal_pro

app = FastAPI()

class Item(BaseModel):
    Sat_ID: str
    Data_version: str
    Match_Data_Type: str
    Product_Type: str
    Start_date: str
    End_date: str
    Template_docx: str
    order_id: str
    input: str
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None

@app.post("/ycz/cal")
def get_item(item: Item):
    res = func_ycz_cal_pro(item)
    return res
