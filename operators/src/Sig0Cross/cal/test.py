import requests
import json

base_url = "http://127.0.0.1:8000"

item_data = {
    "Sat_ID": "JA3",
    "Data_version": "001",
    "AUX_Sat": "S6A",
    "Match_Data_Type": "GL_S6_SIG0_CROSS_MATCH_RESULT",
    "Product_Type": "SIG0",
    "Start_date": "20230401",
    "End_date": "20230430",
    "template_doc": "./doc",
    "order_id": "20251205162848625",
    "input": "/home/leehir/GPF/03-星星交叉_烟台/XOver_2026_parallel_v5_cal/input",
    "output": "/home/leehir/GPF/03-星星交叉_烟台/XOver_2026_parallel_v5_cal/output",
    "outputFileType": "GL_S6_SIG0_CROSS_CAL_RESULT",
    "proc_name": "gl_sig0_cross_cal_pro",
    "version": "1.0",
}

response = requests.post(f"{base_url}/sig0cross/cal", json=item_data)
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
