import requests
import json

base_url = "http://127.0.0.1:8000"

item_data = {
    "Sat_ID": "JA3",
    "Data_version": "001",
    "AUX_Sat": "S6A",
    "Product_Type": "SIG0",
    "Start_date": "20230501",
    "End_date": "20230503",
    "Match_time": "24",
    "order_id": "20251205162848625",
    "input": "/home/leehir/data/JA3_20230501_20230503",
    "input_AUX": "/home/leehir/data/S6A_20230501_20230503",
    "output": "/home/leehir/GPF/03-星星交叉_烟台/XOver_2026_parallel_v4_match/output",
    "outputFileType": "GL_S6_SIG0_CROSS_MATCH_RESULT",
    "proc_name": "gl_sig0_cross_match_pro",
    "version": "1.0",
    "Template_docx": "./MCS_GL_ALT_CCS.docx",
}

response = requests.post(f"{base_url}/sig0cross/match", json=item_data)
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
