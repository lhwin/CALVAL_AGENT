import requests
import json

base_url = "http://127.0.0.1:8000"

item_data = {
    "Sat_ID": "JA3",
    "Data_version": "001",
    "AUX_YCZ": "AUX_WS_YCZ",
    "Product_Type": "SSH",
    "Start_date": "20190610",
    "End_date": "20241017",
    "MSS_PATH": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_MATCH/data/input/DTU18MSS_1min.nc",
    "FES2014_PATH": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_MATCH/data/input/FES2014/ocean_tide",
    "order_id": "20251205162848625",
    "input": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_MATCH/data/output",
    "input_AUX": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_MATCH/data/input/WSTG",
    "output": "/home/leehir/GPF/04-验潮站外推v1.0/CVS_GLSY_ALT_GDR_AUX_YCZ_MATCH/data/output",
    "outputFileType": "GL_SSH_YCZ_MATCH_RESULT",
    "proc_name": "gl_ssh_ycz_match_pro",
    "version": "1.0",
}

response = requests.post(f"{base_url}/ycz/match", json=item_data)
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
