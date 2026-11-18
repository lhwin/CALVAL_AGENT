import requests
import json

def request_data(url, item_data):
    """
    向指定地址发送数据发现请求，并返回响应结果。
    
    :param address: API 地址
    :param item_data: 请求数据
    """
    try:
        response = requests.post(url, json=item_data)
        response.raise_for_status()  # 检查请求是否成功
        return response.json()  # 返回 JSON 响应
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None
   
if __name__ == "__main__":
    base_url = "http://192.168.240.132:8000"

    item_data = {
        "satelite_dir":"/home/leehir/data/satelite",
        "oceantide_dir":"/home/leehir/data/oceantide"
    }

    response = requests.post(f"{base_url}/data/discover", json=item_data)
    print(f"Status Code: {response.status_code}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))