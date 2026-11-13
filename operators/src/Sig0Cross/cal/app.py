from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from func_GLSY_ALT_AUX_Sat_GDR_SIG0_CAL import func_cross_cal_pro

app = FastAPI()

class Item(BaseModel):
    Sat_ID: str
    Data_version: str
    AUX_Sat: str
    Product_Type: str
    Match_Data_Type: str
    Start_date: str
    End_date: str
    template_doc: str
    order_id: str
    input: str
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None

@app.post("/sig0cross/cal")
def get_item(item: Item):
    res = func_cross_cal_pro(item)
    return res
