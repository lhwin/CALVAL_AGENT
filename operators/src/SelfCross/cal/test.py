import requests, json

base_url = "http://127.0.0.1:8000"

item_data = {
    "Sat_ID": "JA3",
    "Data_version": "001",
    "Product_Type": "SSH",
    "Start_date": "20230501",
    "End_date": "20230502",
    "Match_time": "24",
    "order_id": "20251205162848625",
    "input": "/home/leehir/GPF/02-星星自交叉法v2.0/CVS_SELF_GLSY_ALT_GDR_AUX_SAT_MATCH/output/MDS_JA3_SSH_SELF_CROSS_20230501_20230502_V001",
    "output": "/home/leehir/GPF/02-星星自交叉法v2.0/CVS_SELF_GLSY_ALT_GDR_AUX_SAT_CAL/output",
    "outputFileType": "S6_S6A_SSH_SELF_CAL_RESULT",
    "proc_name": "gl_ssh_self_cross_cal_pro",
    "version": "1.0",
    "Select_Area": "[-60,60,-180,180]",
    "distance_to_coast": 50,
    "ocean_depth": 1000,
    "wind_speed": "[0,40]",
    "Template_docx": "./MCS_GL_ALT_CCS.docx"
}

response = requests.post(f"{base_url}/selfcross/cal", json=item_data)
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
