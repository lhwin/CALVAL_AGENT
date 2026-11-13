import sys
import os
import numpy as np
import time
import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties
import matplotlib.font_manager as fm
import matplotlib as mpl
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta
# from docx import Document
# from docx.shared import Cm
import shutil
from operators.IPFUtils import Logger, write_product_xml, CacuConfig


# ===================== 辅助函数 =====================

def read_satellite_data(file_list, sat_id, start_date, end_date,
                        select_area=None, distance_to_coast_threshold=50,
                        ocean_depth_threshold=1000, wind_speed_range=None):
    """
    读取卫星数据 - 不做任何筛选，只返回原始数据
    返回: data_dict (包含所有原始数据)
    """
    all_lon, all_lat, all_ssh, all_time = [], [], [], []
    all_distance_to_coast = []
    all_depth = []
    all_wind_speed = []

    files_processed = 0

    for filepath in file_list:
        try:
            if sat_id.startswith('S6') or sat_id.startswith('S6A'):  # Sentinel-6
                data = read_sentinel6_nc(filepath)
            elif sat_id.startswith('JA3') or sat_id.startswith('J3'):  # Jason-3
                data = read_jason3_nc(filepath)
            elif sat_id.startswith('SA3') or sat_id.startswith('S3'):  # Sentinel-3
                data = read_sentinel3_nc(filepath)
            elif sat_id.startswith('SARAL') or sat_id.startswith('SRL'):  # SARAL
                data = read_SARAL_nc(filepath)
            else:
                Logger.warn(f"不支持的卫星类型: {sat_id}")
                continue

            if data is None or len(data['ssh']) == 0:
                continue

            files_processed += 1
            original_count = len(data['ssh'])

            # 不做任何筛选，直接保存所有数据
            all_lon.extend(data['lon'])
            all_lat.extend(data['lat'])
            all_ssh.extend(data['ssh'])
            all_time.extend(data['time'])

            if data['distance_to_coast'] is not None and len(data['distance_to_coast']) > 0:
                all_distance_to_coast.extend(data['distance_to_coast'])

            if data['depth'] is not None and len(data['depth']) > 0:
                all_depth.extend(data['depth'])

            if data.get('wind_speed') is not None and len(data['wind_speed']) > 0:
                all_wind_speed.extend(data['wind_speed'])

            Logger.info(f"文件 {os.path.basename(filepath)}: 读取 {original_count} 点")

        except Exception as e:
            Logger.warn(f"读取文件 {filepath} 失败: {str(e)}")
            continue

    Logger.info(f"共处理文件数: {files_processed}")
    Logger.info(f"读取总点数: {len(all_ssh)}")

    return {
        'lon': np.array(all_lon),
        'lat': np.array(all_lat),
        'ssh': np.array(all_ssh),
        'time': np.array(all_time),
        'distance_to_coast': np.array(all_distance_to_coast) if all_distance_to_coast else np.array([]),
        'depth': np.array(all_depth) if all_depth else np.array([]),
        'wind_speed': np.array(all_wind_speed) if all_wind_speed else np.array([])
    }


def read_jason3_nc(filepath):
    """读取Jason-3 NC文件"""
    try:
        import h5py
        with h5py.File(filepath, 'r') as f:
            data_01 = f['data_01']

            lon = data_01['longitude'][:].astype(float) / 1e6
            lat = data_01['latitude'][:].astype(float) / 1e6
            ssh_raw = data_01['ku/ssha'][:].astype(float)
            time = data_01['time'][:].astype(float)

            # 读取距离海岸距离（Jason-3单位是mm，需要除以1000转换为km）
            distance_to_coast = data_01['distance_to_coast'][:].astype(float) / 1000.0  # mm -> km

            # 读取水深（单位米，负值为海洋深度）
            depth = data_01['depth_or_elevation'][:].astype(float)

            wind_speed_raw = data_01['wind_speed_alt'][:].astype(float)
            wind_speed = wind_speed_raw * 0.01

            # Jason-3: 去除32767填充值
            fill_value_jason = 32767
            valid_mask = (ssh_raw != fill_value_jason) & (~np.isnan(ssh_raw))

            # Jason-3的SSH单位是mm，除以1000得到米
            ssh = ssh_raw[valid_mask] / 1000.0
            lon = normalize_longitude(lon[valid_mask])
            lat = lat[valid_mask]
            time = time[valid_mask]
            distance_to_coast = distance_to_coast[valid_mask]
            depth = depth[valid_mask]
            wind_speed = wind_speed[valid_mask]

            # 过滤明显异常值（超过±5米）
            valid_ssh_mask = np.abs(ssh) < 1.5
            ssh = ssh[valid_ssh_mask]
            lon = lon[valid_ssh_mask]
            lat = lat[valid_ssh_mask]
            time = time[valid_ssh_mask]
            distance_to_coast = distance_to_coast[valid_ssh_mask]
            depth = depth[valid_ssh_mask]
            wind_speed = wind_speed[valid_ssh_mask]

            # 过滤无效的离岸距离（例如大于20000km的值）
            valid_coast_mask = (distance_to_coast >= 50) & (distance_to_coast < 20000)
            ssh = ssh[valid_coast_mask]
            lon = lon[valid_coast_mask]
            lat = lat[valid_coast_mask]
            time = time[valid_coast_mask]
            distance_to_coast = distance_to_coast[valid_coast_mask]
            depth = depth[valid_coast_mask]
            wind_speed = wind_speed[valid_coast_mask]

            return {
                'lon': lon,
                'lat': lat,
                'ssh': ssh,
                'time': time,
                'distance_to_coast': distance_to_coast,
                'depth': depth,
                'wind_speed': wind_speed,
            }
    except Exception as e:
        Logger.warn(f"读取Jason-3文件失败: {str(e)}")
        return None


def read_sentinel6_nc(filepath):
    """读取Sentinel-6 NC文件"""
    try:
        import h5py
        with h5py.File(filepath, 'r') as f:
            data_01 = f['data_01']

            lon = data_01['longitude'][:].astype(float) / 1e6
            lat = data_01['latitude'][:].astype(float) / 1e6
            ssh_raw = data_01['ku/ssha'][:].astype(float)
            time = data_01['time'][:].astype(float)

            # 读取距离海岸距离（Sentinel-6单位是km）
            distance_to_coast = data_01['distance_to_coast'][:].astype(float)/10

            # 读取水深（单位米，负值为海洋深度）
            depth = data_01['depth_or_elevation'][:].astype(float)

            wind_speed_raw = data_01['wind_speed_alt'][:].astype(float)
            wind_speed = wind_speed_raw * 0.01  # 转换为 m/s

            # Sentinel-6: 去除2147483647填充值
            fill_value = 2147483647
            valid_mask = (ssh_raw != fill_value) & (~np.isnan(ssh_raw))

            # Sentinel-6的SSH单位是0.1mm，除以10000得到米
            ssh = ssh_raw[valid_mask] / 10000.0
            lon = normalize_longitude(lon[valid_mask])
            lat = lat[valid_mask]
            time = time[valid_mask]
            distance_to_coast = distance_to_coast[valid_mask]
            depth = depth[valid_mask]
            wind_speed = wind_speed[valid_mask]

            # 过滤明显异常值（超过±5米）
            valid_ssh_mask = np.abs(ssh) < 10
            ssh = ssh[valid_ssh_mask]
            lon = lon[valid_ssh_mask]
            lat = lat[valid_ssh_mask]
            time = time[valid_ssh_mask]
            distance_to_coast = distance_to_coast[valid_ssh_mask]
            depth = depth[valid_ssh_mask]
            wind_speed = wind_speed[valid_ssh_mask]

            # 过滤无效的离岸距离（负值表示陆地，大于20000km的明显无效）
            valid_coast_mask = (distance_to_coast >= 50) & (distance_to_coast < 20000)
            ssh = ssh[valid_coast_mask]
            lon = lon[valid_coast_mask]
            lat = lat[valid_coast_mask]
            time = time[valid_coast_mask]
            distance_to_coast = distance_to_coast[valid_coast_mask]
            depth = depth[valid_coast_mask]
            wind_speed = wind_speed[valid_coast_mask]

            return {
                'lon': lon,
                'lat': lat,
                'ssh': ssh,
                'time': time,
                'distance_to_coast': distance_to_coast,
                'depth': depth,
                'wind_speed': wind_speed,
            }
    except Exception as e:
        Logger.warn(f"读取Sentinel-6文件失败: {str(e)}")
        return None

def read_sentinel3_nc(filepath):
    """读取Sentinel-3 NC文件"""
    try:
        import h5py
        with h5py.File(filepath, 'r') as data_01:

            lon = data_01['lon_01'][:].astype(float) / 1e6
            lat = data_01['lat_01'][:].astype(float) / 1e6
            ssh_raw = data_01['ssha_01_ku'][:].astype(float)
            time = data_01['time_01'][:].astype(float)

            # 读取距离海岸距离（Sentinel-3单位是km）
            distance_to_coast = data_01['dist_coast_01'][:].astype(float) / 1e3  # m -> km

            # 读取水深（单位米，负值为海洋深度）
            depth = data_01['odle_01'][:].astype(float) / 1e4

            wind_speed_raw = data_01['wind_speed_alt_01_ku'][:].astype(float)
            wind_speed = wind_speed_raw * 0.01  # 转换为 m/s

            # Sentinel-3: 去除2147483647填充值
            fill_value = 32767
            valid_mask = (ssh_raw != fill_value) & (~np.isnan(ssh_raw))

            # Sentinel-3的SSH单位是0.1mm，除以10000得到米
            ssh = ssh_raw[valid_mask] / 1000.0
            lon = normalize_longitude(lon[valid_mask])
            lat = lat[valid_mask]
            time = time[valid_mask]
            distance_to_coast = distance_to_coast[valid_mask]
            depth = depth[valid_mask]
            wind_speed = wind_speed[valid_mask]

            # 过滤明显异常值（超过±5米）
            valid_ssh_mask = np.abs(ssh) < 10
            ssh = ssh[valid_ssh_mask]
            lon = lon[valid_ssh_mask]
            lat = lat[valid_ssh_mask]
            time = time[valid_ssh_mask]
            distance_to_coast = distance_to_coast[valid_ssh_mask]
            depth = depth[valid_ssh_mask]
            wind_speed = wind_speed[valid_ssh_mask]

            # 过滤无效的离岸距离（负值表示陆地，大于20000km的明显无效）
            valid_coast_mask = (distance_to_coast >= 50) & (distance_to_coast < 20000)
            ssh = ssh[valid_coast_mask]
            lon = lon[valid_coast_mask]
            lat = lat[valid_coast_mask]
            time = time[valid_coast_mask]
            distance_to_coast = distance_to_coast[valid_coast_mask]
            depth = depth[valid_coast_mask]
            wind_speed = wind_speed[valid_coast_mask]

            return {
                'lon': lon,
                'lat': lat,
                'ssh': ssh,
                'time': time,
                'distance_to_coast': distance_to_coast,
                'depth': depth,
                'wind_speed': wind_speed,
            }
    except Exception as e:
        Logger.warn(f"读取Sentinel-3文件失败: {str(e)}")
        return None

def read_SARAL_nc(filepath):
    """读取SARAL NC文件"""
    try:
        import h5py
        with h5py.File(filepath, 'r') as data_01:

            lon = data_01['lon'][:].astype(float) / 1e6
            lat = data_01['lat'][:].astype(float) / 1e6
            ssh_raw = data_01['ssha'][:].astype(float)
            time = data_01['time'][:].astype(float)

            # 读取距离海岸距离（SARAL单位是km）
            distance_to_coast = data_01['dist_coast'][:].astype(float)/1000

            # 读取水深（单位米，负值为海洋深度）
            depth = data_01['bathymetry'][:].astype(float)

            wind_speed_raw = data_01['wind_speed_alt'][:].astype(float)
            wind_speed = wind_speed_raw * 0.01  # 转换为 m/s

            # SARAL: 去除32767填充值
            fill_value = 32767
            valid_mask = (ssh_raw != fill_value) & (~np.isnan(ssh_raw))

            # SARAL的SSH单位是0.1mm，除以10000得到米
            ssh = ssh_raw[valid_mask] / 1000.0
            lon = normalize_longitude(lon[valid_mask])
            lat = lat[valid_mask]
            time = time[valid_mask]
            distance_to_coast = distance_to_coast[valid_mask]
            depth = depth[valid_mask]
            wind_speed = wind_speed[valid_mask]

            # 过滤明显异常值（超过±5米）
            valid_ssh_mask = np.abs(ssh) < 10
            ssh = ssh[valid_ssh_mask]
            lon = lon[valid_ssh_mask]
            lat = lat[valid_ssh_mask]
            time = time[valid_ssh_mask]
            distance_to_coast = distance_to_coast[valid_ssh_mask]
            depth = depth[valid_ssh_mask]
            wind_speed = wind_speed[valid_ssh_mask]

            # 过滤无效的离岸距离（负值表示陆地，大于20000km的明显无效）
            valid_coast_mask = (distance_to_coast >= 50) & (distance_to_coast < 20000)
            ssh = ssh[valid_coast_mask]
            lon = lon[valid_coast_mask]
            lat = lat[valid_coast_mask]
            time = time[valid_coast_mask]
            distance_to_coast = distance_to_coast[valid_coast_mask]
            depth = depth[valid_coast_mask]
            wind_speed = wind_speed[valid_coast_mask]

            return {
                'lon': lon,
                'lat': lat,
                'ssh': ssh,
                'time': time,
                'distance_to_coast': distance_to_coast,
                'depth': depth,
                'wind_speed': wind_speed,
            }
    except Exception as e:
        Logger.warn(f"读取SARAL文件失败: {str(e)}")
        return None



def normalize_longitude(lon):
    """将经度统一到[-180, 180]范围"""
    lon = np.array(lon)
    lon[lon > 180] = lon[lon > 180] - 360
    return lon


def haversine_distance(lon1, lat1, lon2, lat2):
    """计算两点间的大圆距离（km）- 精确版本"""
    R = 6371.0  # 地球半径（km）

    lon1_rad = np.radians(lon1)
    lat1_rad = np.radians(lat1)
    lon2_rad = np.radians(lon2)
    lat2_rad = np.radians(lat2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    distance = R * c

    return distance


def func_cross_matching_pro(ipf_config):
   
    if getattr(sys, 'frozen', False):
    # PyInstaller 打包模式：资源解压到 sys._MEIPASS 临时目录
        current_dir = sys._MEIPASS
    else:
        # 源码运行模式：使用脚本所在目录定位资源
        current_dir = os.path.dirname(os.path.abspath(__file__))
    current_dir = os.path.abspath(current_dir)

    fontTTF = os.path.join(current_dir, "conf", "SimHei.ttf")
    font_prop = FontProperties(fname=fontTTF)
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams.update({'font.size': 14})

    # stpe1 配置文件加载及解析
    # 在输出目录下创建文件同名的文件夹，以存放产品
    new_dir_path = os.path.join(ipf_config.output, "MDS_" + ipf_config.Sat_ID + "_" +
                                ipf_config.AUX_Sat + "_" + ipf_config.Product_Type + "_" +
                                ipf_config.Start_date + "_" + ipf_config.End_date + "_V" +
                                ipf_config.Data_version)
    os.makedirs(new_dir_path, exist_ok=True)
    outputPath = new_dir_path
    # 将生产的nc等文件放到outputPath目录下。
    # +-------------此处添加核心处理代码-----------------------#
    Logger.info("Start data processing")
    Logger.info("Get file list in input directory within specified time range")
    # 根据关键字ipf_config.Sat_ID和起止时间ipf_config.Start_date和ipf_config.End_date获取输入目录下在这个时间范围的文件列表
    input_file_list = get_file_list(ipf_config.input, ipf_config.Sat_ID, ipf_config.Start_date, ipf_config.End_date)
    aux_file_list = get_file_list(ipf_config.input_AUX, ipf_config.AUX_Sat, ipf_config.Start_date, ipf_config.End_date)

    Logger.info("Start data reading")
    # 解析卫星ID
    primary_sat = ipf_config.Sat_ID  # 主卫星, 如 "S6A"
    aux_sat = ipf_config.AUX_Sat  # 辅助卫星, 如 "JA3"

    Logger.info(f"主卫星: {primary_sat}, 辅助卫星: {aux_sat}")
    Logger.info(f"主卫星文件数量: {len(input_file_list)}")
    Logger.info(f"辅助卫星文件数量: {len(aux_file_list)}")

    wind_speed_range = None
    if hasattr(ipf_config, 'wind_speed') and ipf_config.wind_speed:
        wind_speed_range = ipf_config.wind_speed
    else:
        Logger.info("未配置风速筛选")

    # 读取主卫星数据
    Logger.info("读取主卫星数据...")
    primary_data = read_satellite_data(
        input_file_list, primary_sat,
        ipf_config.Start_date, ipf_config.End_date,
        select_area=ipf_config.Select_Area,
        distance_to_coast_threshold=ipf_config.distance_to_coast,
        ocean_depth_threshold=ipf_config.ocean_depth,
        wind_speed_range=wind_speed_range
    )

    # 读取辅助卫星数据
    Logger.info("读取辅助卫星数据...")
    aux_data = read_satellite_data(
        aux_file_list, aux_sat,
        ipf_config.Start_date, ipf_config.End_date,
        select_area=ipf_config.Select_Area,
        distance_to_coast_threshold=ipf_config.distance_to_coast,
        ocean_depth_threshold=ipf_config.ocean_depth,
        wind_speed_range=wind_speed_range
    )

    Logger.info(f"主卫星有效数据点数: {len(primary_data['lon'])}")
    Logger.info(f"辅助卫星有效数据点数: {len(aux_data['lon'])}")

    if len(primary_data['lon']) == 0 or len(aux_data['lon']) == 0:
        Logger.error("读取的有效数据为空")
        return

    Logger.info("Start data matching")
    Logger.info("开始时空匹配...")

    def haversine_distance(lon1, lat1, lon2, lat2):
        """计算两点间的大圆距离（km）- 精确版本"""
        R = 6371.0  # 地球半径（km）

        lon1_rad = np.radians(lon1)
        lat1_rad = np.radians(lat1)
        lon2_rad = np.radians(lon2)
        lat2_rad = np.radians(lat2)

        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad

        a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
        c = 2 * np.arcsin(np.sqrt(a))
        distance = R * c

        return distance

    def match_satellite_data(primary_data, aux_data, spatial_threshold_km=15,
                             min_neighbors=3, max_time_diff_hours=6):
        """匹配两颗卫星的数据"""
        from scipy.spatial import cKDTree

        lon_p = primary_data['lon']
        lat_p = primary_data['lat']
        ssh_p = primary_data['ssh']
        time_p = primary_data['time']

        lon_a = aux_data['lon']
        lat_a = aux_data['lat']
        ssh_a = aux_data['ssh']
        time_a = aux_data['time']

        # 构建KDTree
        points_a = np.column_stack((lon_a, lat_a))
        tree_a = cKDTree(points_a)

        match_lon, match_lat = [], []
        match_time_p, match_time_a = [], []
        match_ssh_p, match_ssh_a = [], []
        match_ssh_diff, match_distance = [], []

        max_time_diff_seconds = max_time_diff_hours * 3600

        Logger.info(f"开始匹配，主卫星点数: {len(lon_p)}")

        for i in range(len(lon_p)):
            if i % 10000 == 0 and i > 0:
                Logger.info(f"处理进度: {i}/{len(lon_p)}")

            if np.isnan(ssh_p[i]):
                continue

            # 空间匹配：找到半径内的所有点
            indices = tree_a.query_ball_point([lon_p[i], lat_p[i]],
                                              r=spatial_threshold_km / 111.32)

            if len(indices) < min_neighbors:
                continue

            # 获取这些点的经纬度和SSH
            lon_a_local = lon_a[indices]
            lat_a_local = lat_a[indices]
            ssh_a_local = ssh_a[indices]
            time_a_local = time_a[indices]

            # 计算精确的大圆距离
            distances = np.array([haversine_distance(lon_p[i], lat_p[i],
                                                     lon_a_local[j], lat_a_local[j])
                                  for j in range(len(lon_a_local))])

            # 筛选在阈值内的点
            valid_mask = distances <= spatial_threshold_km
            valid_distances = distances[valid_mask]
            valid_ssh = ssh_a_local[valid_mask]
            valid_time = time_a_local[valid_mask]

            if len(valid_ssh) < min_neighbors:
                continue

            # 混合方法：结合IDW和高斯加权
            # 1. 反距离权重
            idw_weights = 1.0 / (valid_distances ** 2 + 1e-10)
            idw_weights = idw_weights / np.sum(idw_weights)
            idw_value = np.average(valid_ssh, weights=idw_weights)

            # 2. 高斯加权
            sigma = spatial_threshold_km / 3
            gaussian_weights = np.exp(-(valid_distances ** 2) / (2 * sigma ** 2))
            gaussian_weights = gaussian_weights / np.sum(gaussian_weights)
            gaussian_value = np.average(valid_ssh, weights=gaussian_weights)

            # 3. 取平均
            ssh_a_interp = (idw_value + gaussian_value) / 2

            # 记录匹配结果
            match_lon.append(lon_p[i])
            match_lat.append(lat_p[i])
            match_time_p.append(time_p[i])
            match_time_a.append(np.average(valid_time, weights=gaussian_weights))
            match_ssh_p.append(ssh_p[i])
            match_ssh_a.append(ssh_a_interp)
            match_ssh_diff.append(ssh_p[i] - ssh_a_interp)
            match_distance.append(np.mean(valid_distances))

        if len(match_ssh_diff) == 0:
            return None

        Logger.info(f"匹配完成，共 {len(match_ssh_diff)} 个匹配点")

        return {
            'lon': np.array(match_lon),
            'lat': np.array(match_lat),
            'time_primary': np.array(match_time_p),
            'time_aux': np.array(match_time_a),
            'ssh_primary': np.array(match_ssh_p),
            'ssh_aux': np.array(match_ssh_a),
            'ssh_diff': np.array(match_ssh_diff),
            'distance': np.array(match_distance)
        }

    def seconds_to_date(time_seconds):
        ref_date = datetime(2000, 1, 1)
        date = ref_date + timedelta(seconds=float(time_seconds))
        return int(date.strftime('%Y%m%d'))

    # 匹配参数设置
    spatial_threshold_km = 15
    min_neighbors = 3
    max_time_diff_hours = 6

    # 获取共同日期
    primary_dates = [seconds_to_date(t) for t in primary_data['time']]
    aux_dates = [seconds_to_date(t) for t in aux_data['time']]
    common_dates = sorted(set(primary_dates) & set(aux_dates))

    Logger.info(f"共同日期: {common_dates}")

    # 存储所有匹配结果
    all_results = []

    # 按日期分别匹配
    for date in common_dates:
        Logger.info(f"处理日期 {date}")

        # 按日期筛选数据
        p_mask = np.array([seconds_to_date(t) for t in primary_data['time']]) == date
        a_mask = np.array([seconds_to_date(t) for t in aux_data['time']]) == date

        if np.sum(p_mask) < 10 or np.sum(a_mask) < 10:
            Logger.info(f"  数据点不足，跳过")
            continue

        p_data_date = {
            'lon': primary_data['lon'][p_mask],
            'lat': primary_data['lat'][p_mask],
            'ssh': primary_data['ssh'][p_mask],
            'time': primary_data['time'][p_mask]
        }
        a_data_date = {
            'lon': aux_data['lon'][a_mask],
            'lat': aux_data['lat'][a_mask],
            'ssh': aux_data['ssh'][a_mask],
            'time': aux_data['time'][a_mask]
        }

        # 执行匹配
        match_result = match_satellite_data(
            p_data_date, a_data_date,
            spatial_threshold_km=spatial_threshold_km,
            min_neighbors=min_neighbors,
            max_time_diff_hours=max_time_diff_hours
        )

        if match_result and len(match_result['ssh_diff']) > 0:
            all_results.append(match_result)
            Logger.info(f"  匹配点数: {len(match_result['ssh_diff'])}")
        else:
            Logger.info(f"  未找到匹配点")

    # 合并所有结果
    if all_results:
        match_result = {
            'lon': np.concatenate([r['lon'] for r in all_results]),
            'lat': np.concatenate([r['lat'] for r in all_results]),
            'time_primary': np.concatenate([r['time_primary'] for r in all_results]),
            'time_aux': np.concatenate([r['time_aux'] for r in all_results]),
            'ssh_primary': np.concatenate([r['ssh_primary'] for r in all_results]),
            'ssh_aux': np.concatenate([r['ssh_aux'] for r in all_results]),
            'ssh_diff': np.concatenate([r['ssh_diff'] for r in all_results]),
            'distance': np.concatenate([r['distance'] for r in all_results])
        }
        Logger.info(f"总计匹配点数: {len(match_result['ssh_diff'])}")

        # ==================== 新增：对匹配点进行筛选统计 ====================
        # 从配置中获取筛选阈值
        min_lat, max_lat, min_lon, max_lon = -60, 60, -180, 180
        if hasattr(ipf_config, 'Select_Area') and ipf_config.Select_Area:
            area_parts = ipf_config.Select_Area.strip('[]').split(',')
            min_lat, max_lat, min_lon, max_lon = [float(p) for p in area_parts]

        distance_threshold = getattr(ipf_config, 'distance_to_coast', 50)
        depth_threshold = getattr(ipf_config, 'ocean_depth', 1000)

        wind_min, wind_max = 0, 40
        if hasattr(ipf_config, 'wind_speed') and ipf_config.wind_speed:
            wind_parts = ipf_config.wind_speed.strip('[]').split(',')
            wind_min = float(wind_parts[0])
            wind_max = float(wind_parts[1])

        total_match = len(match_result['ssh_diff'])

        # 获取匹配点的属性（需要从aux_data中插值获取）
        from scipy.spatial import cKDTree

        # 构建辅助卫星数据的KDTree
        aux_points = np.column_stack((aux_data['lon'], aux_data['lat']))
        aux_tree = cKDTree(aux_points)

        match_coast = []
        match_depth = []
        match_wind = []

        for i in range(total_match):
            dist, idx = aux_tree.query([match_result['lon'][i], match_result['lat'][i]])
            if len(aux_data['distance_to_coast']) > idx:
                match_coast.append(aux_data['distance_to_coast'][idx])
            else:
                match_coast.append(np.nan)
            if len(aux_data['depth']) > idx:
                match_depth.append(aux_data['depth'][idx])
            else:
                match_depth.append(np.nan)
            if len(aux_data['wind_speed']) > idx:
                match_wind.append(aux_data['wind_speed'][idx])
            else:
                match_wind.append(np.nan)

        match_coast = np.array(match_coast)
        match_depth = np.array(match_depth)
        match_wind = np.array(match_wind)

        # 统计各筛选条件通过的点数
        # 1. 经纬度筛选
        lon_mask = (match_result['lon'] >= min_lon) & (match_result['lon'] <= max_lon)
        lat_mask = (match_result['lat'] >= min_lat) & (match_result['lat'] <= max_lat)
        area_mask = lon_mask & lat_mask
        pass_area = np.sum(area_mask)

        # 2. 离岸距离筛选
        coast_valid = ~np.isnan(match_coast)
        coast_mask = match_coast >= distance_threshold
        pass_coast = np.sum(coast_valid & coast_mask)

        # 3. 水深筛选（负值，小于 -threshold 表示深海）
        depth_valid = ~np.isnan(match_depth)
        depth_mask = match_depth < -depth_threshold
        pass_depth = np.sum(depth_valid & depth_mask)

        # 4. 风速筛选
        wind_valid = ~np.isnan(match_wind)
        wind_mask = (match_wind >= wind_min) & (match_wind <= wind_max)
        pass_wind = np.sum(wind_valid & wind_mask)

        # 5. 组合筛选（满足所有条件的点）
        combined_mask = area_mask
        if np.any(coast_valid):
            combined_mask = combined_mask & coast_mask
        if np.any(depth_valid):
            combined_mask = combined_mask & depth_mask
        if np.any(wind_valid):
            combined_mask = combined_mask & wind_mask

        pass_all = np.sum(combined_mask)

        Logger.info("=" * 50)
        Logger.info("匹配点筛选统计:")
        Logger.info(f"  总匹配点数: {total_match}")
        Logger.info(f"  经纬度筛选通过: {pass_area} ({pass_area / total_match * 100:.1f}%)")
        Logger.info(f"  离岸距离筛选通过: {pass_coast} ({pass_coast / total_match * 100:.1f}%)")
        Logger.info(f"  水深筛选通过: {pass_depth} ({pass_depth / total_match * 100:.1f}%)")
        Logger.info(f"  风速筛选通过: {pass_wind} ({pass_wind / total_match * 100:.1f}%)")
        Logger.info(f"  所有条件通过: {pass_all} ({pass_all / total_match * 100:.1f}%)")
        Logger.info("=" * 50)

        # 保存筛选统计信息
        match_stats = {
            'total_match': total_match,
            'pass_area': pass_area,
            'pass_coast': pass_coast,
            'pass_depth': pass_depth,
            'pass_wind': pass_wind,
            'pass_all': pass_all,
            'thresholds': {
                'lat_range': [min_lat, max_lat],
                'lon_range': [min_lon, max_lon],
                'distance_to_coast': distance_threshold,
                'ocean_depth': depth_threshold,
                'wind_speed': [wind_min, wind_max]
            }
        }

        # 保存为numpy压缩格式（包含匹配点的属性信息）
        match_file = os.path.join(outputPath,
                                  f"match_result_{ipf_config.Sat_ID}_vs_{ipf_config.AUX_Sat}_{ipf_config.Start_date}_{ipf_config.End_date}.npz")

        np.savez_compressed(match_file,
                            lon=match_result['lon'],
                            lat=match_result['lat'],
                            time_primary=match_result['time_primary'],
                            time_aux=match_result['time_aux'],
                            ssh_primary=match_result['ssh_primary'],
                            ssh_aux=match_result['ssh_aux'],
                            ssh_diff=match_result['ssh_diff'],
                            distance=match_result.get('distance', np.array([])),
                            distance_to_coast=match_coast,
                            depth=match_depth,
                            wind_speed=match_wind,
                            match_stats=match_stats)  # 添加筛选统计

        Logger.info(f"匹配结果已保存至: {match_file}")

        # 同时保存为CSV格式便于查看
        try:
            import pandas as pd
            csv_file = os.path.join(outputPath,
                                    f"match_result_{ipf_config.Sat_ID}_vs_{ipf_config.AUX_Sat}_{ipf_config.Start_date}_{ipf_config.End_date}.csv")
            df = pd.DataFrame({
                'lon': match_result['lon'],
                'lat': match_result['lat'],
                'time_primary': match_result['time_primary'],
                'time_aux': match_result['time_aux'],
                'ssh_primary': match_result['ssh_primary'],
                'ssh_aux': match_result['ssh_aux'],
                'ssh_diff': match_result['ssh_diff']
            })
            df.to_csv(csv_file, index=False)
            Logger.info(f"匹配结果CSV已保存至: {csv_file}")
        except ImportError:
            Logger.warn("pandas未安装，跳过CSV保存")

    else:
        match_result = None
        Logger.warn("未找到匹配点")

    # 根据处理进度情况，进行进度配置，如：70%
    Logger.progress(10)
    # 添加日志，如：
    msg = "Initialize function, program starts running"
    Logger.info(msg)
    # --------------此处添加核心处理代码-----------------------#

    Logger.info("Finish data processing")
    # 最后生成结果文件列表："product.xml"
    str_order_id = "%010d" % int(ipf_config.order_id)
    product_xml_name = str_order_id + ".product.xml"
    product_xml_path = os.path.join(ipf_config.output, product_xml_name)
    write_product_xml(product_xml_path, outputPath, ipf_config.outputFileType)
    # 函数write_product_xml传参：
    Logger.progress(100)

    result = {
    "statistics": {
        "total_match": int(total_match),
        "pass_area": int(pass_area),
        "pass_coast": int(pass_coast),
        "pass_depth": int(pass_depth),
        "pass_wind": int(pass_wind),
        "pass_all": int(pass_all),
        "thresholds": {
            "lat_range": [min_lat, max_lat],
            "lon_range": [min_lon, max_lon],
            "distance_to_coast": distance_threshold,
            "ocean_depth": depth_threshold,
            "wind_speed": [wind_min, wind_max]
            }
        },
        "output_files": {
        "match_npz": match_file if 'match_file' in dir() else "",
        "match_csv": csv_file if 'csv_file' in dir() else ""
        },
        "output_dir":os.path.abspath(new_dir_path),
        "success": True
    }
    return result


def get_file_list(directory, sat_id, start_date, end_date):
    """
    根据卫星ID和起止时间获取目录下符合条件的文件列表

    参数:
        directory: 要搜索的目录路径
        sat_id: 卫星ID关键字 (如 "S6A")
        start_date: 起始日期，格式为"YYYYMMDD"
        end_date: 结束日期，格式为"YYYYMMDD"

    返回:
        符合条件的文件列表
    """
    file_list = []

    # 将日期字符串转换为datetime对象
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    # end_dt = datetime.strptime(end_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d") + timedelta(days=1) - timedelta(seconds=1)

    # 确保目录存在
    if not os.path.isdir(directory):
        print(f"警告: 目录 {directory} 不存在")
        return file_list

    # 使用os.walk递归遍历目录及其子目录
    for root, dirs, files in os.walk(directory):
        for filename in files:
            # 检查文件后缀是否为.nc或.h5
            if not (filename.endswith('.nc') or filename.endswith('.h5')):
                continue

            # 检查文件名中是否包含卫星ID
            if sat_id not in filename:
                continue
                # 使用正则表达式提取文件名中的时间范围
            # 支持两种文件格式:
            # 1. S6A_P4_2__LR_STD__NT_088_044_20230401T002018_20230401T011630_F08.nc
            # 2. JA3_GPN_2PfP335_138_20230406_160600_20230406_170213.nc
            time_pattern = r'(\d{8})(?:T|_)(\d{6})_(\d{8})(?:T|_)(\d{6})'
            match = re.search(time_pattern, filename)

            if not match:
                continue

            # 提取时间范围
            groups = match.groups()

            try:
                # 构造时间字符串，统一使用T作为分隔符
                start_time_str = f"{groups[0]}T{groups[1]}"
                end_time_str = f"{groups[2]}T{groups[3]}"

                # 将时间字符串转换为datetime对象
                file_start_dt = datetime.strptime(start_time_str, "%Y%m%dT%H%M%S")
                file_end_dt = datetime.strptime(end_time_str, "%Y%m%dT%H%M%S")

                # 检查文件时间范围是否与查询时间范围有交集
                if file_end_dt < start_dt or file_start_dt > end_dt:
                    continue

                # 如果有交集，则添加到文件列表
                filepath = os.path.join(root, filename)
                file_list.append(filepath)

            except ValueError as e:
                print(f"警告: 无法解析文件 {filename} 中的日期: {e}")
                continue

    return file_list
