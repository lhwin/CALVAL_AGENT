import requests
import json

base_url = "http://127.0.0.1:8000"

item_data = {
    "Sat_ID": "H2B",
    "Data_version": "001",
    "Match_Data_Type": "GL_SSH_YCZ_MATCH_RESULT",
    "Product_Type": "SSH",
    "Start_date": "20190610",
    "End_date": "20241007",
    "Template_docx": "./MCS_GL_ALT_YCZ.docx",
    "order_id": "20251205162848625",
    "input": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_CAL/data/input/MDS_H2B_AUX_WS_YCZ_SSH_20190610_20241017_V001",
    "output": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_CAL/data/output",
    "outputFileType": "GL_SSH_YCZ_CAL_RESULT",
    "proc_name": "gl_ssh_ycz_cal_pro",
    "version": "1.0",
}

response = requests.post(f"{base_url}/ycz/cal", json=item_data)
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
