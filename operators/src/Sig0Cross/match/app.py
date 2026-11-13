from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from func_GLSY_ALT_GDR_AUX_SAT_SIG0_MATCH import func_cross_matching_pro

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
    input: str
    input_AUX: str
    output: Optional[str] = None
    outputFileType: Optional[str] = None
    proc_name: Optional[str] = None
    version: Optional[str] = None

@app.post("/sig0cross/match")
def get_item(item: Item):
    res = func_cross_matching_pro(item)
    return res
