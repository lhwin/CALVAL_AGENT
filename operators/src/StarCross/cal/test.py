import requests
import json

# 定义API的基本URL
base_url = "http://127.0.0.1:8000"  # 假设API在本地运行

# 路径参数
item_id = 123

# 查询参数
query_params = {"q": "optional_query"}

# 请求体数据
item_data = {
    'Sat_ID': 'S6A', 
    'Data_version': '001', 
    'Match_Data_Type': 'JA3', 
    'Product_Type': 'SSH', 
    'Start_date': '20230501', 
    'End_date': '20230504', 
    'order_id': '20251205162848625',
    'Select_Area': '[-60,60,-180,180]', 
    'distance_to_coast': '50', 
    'ocean_depth': '1000', 
    'wind_speed': '[0,40]', 
    'Match_time': '24', 
    'Template_docx': './doc/MCS_GL_ALT_CCS.docx',
    'input': '/home/leehir/GPF/01-星星交叉法v2.0/csv_glsy_alt_gdr_aux_sat_cal/input/MDS_S6A_JA3_SSH_20230501_20230501_V001',
    'output': './data/output',
    'outputFileType':'S6_JA3_SSH_CROSS_CAL_RESULT',
    'proc_name':'gl_ssh_cross_cal_pro',
    'version':'1.0'
    }
# 发送PUT请求
response = requests.post(
    f"{base_url}/sig0cross/cal",  # 包含路径参数         # 查询参数
    json=item_data                  # 请求体
)

# 打印响应
print(f"Status Code: {response.status_code}")
print(f"Response JSON: {json.dumps(response.json(), indent=2)}")