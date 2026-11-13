import requests
import json

base_url = "http://127.0.0.1:8000"

item_data = {
    "Sat_ID": "S6A",
    "Data_version": "001",
    "Product_Type": "SSH",
    "Start_date": "20230501",
    "End_date": "20230503",
    "Match_time": "24",
    "order_id": "20251205162848625",
    "input": "/home/leehir/data/S6A_20230501_20230503",   # 绝对路径，必须存在
    "output": "/home/leehir/GPF/02-星星自交叉法v2.0/CVS_SELF_GLSY_ALT_GDR_AUX_SAT_MATCH/output",
    "outputFileType": "GL_SSH_SELF_CROSS_MATCH_RESULT",
    "proc_name": "gl_ssh_self_cross_match_pro",
    "version": "1.0",
    "Select_Area": "[-60,60,-180,180]",
    "distance_to_coast": 50,
    "ocean_depth": 1000,
    "wind_speed": "[0,40]",
    "Template_docx": "./template.xml"
}

response = requests.post(f"{base_url}/selfcross/selfmatch", json=item_data)
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
