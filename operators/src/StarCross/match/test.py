import requests
import json

base_url = "http://s5.s100.vip:11422"

item_data = {
    "Sat_ID": "S6A",
    "Data_version": "001",
    "AUX_Sat": "JA3",
    "Product_Type": "SSH",
    "Start_date": "20230501",
    "End_date": "20230503",
    "order_id": "20251205162848625",
    "Select_Area": "[-60,60,-180,180]",
    "distance_to_coast": "50",
    "ocean_depth": "1000",
    "wind_speed": "[0,40]",
    "Match_time": "24",
    "Template_docx": "./doc/MCS_GL_ALT_CCS.docx",
    "input": "/home/leehir/GPF/01-星星交叉法v2.0/cvs_glsy_alt_gdr_aux_sat_match/input/MDS_S6A_JA3_SSH_20230501_20230503_V001",
    "output": "./data/output",
    "outputFileType": "S6_JA3_SSH_CROSS_MATCH_RESULT",
    "proc_name": "gl_ssh_cross_match_pro",
    "version": "1.0"
}

response = requests.post(
    f"{base_url}/selfcross/match",
    json=item_data
)

print("Status Code: {}".format(response.status_code))
print("Response JSON: {}".format(json.dumps(response.json(), indent=2)))
