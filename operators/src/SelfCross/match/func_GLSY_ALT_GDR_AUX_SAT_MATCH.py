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
from IPFUtils import Logger, write_product_xml, CacuConfig


def func_self_cross_matching_pro(ipf_config):
    # 兼容 Python 源码运行和 PyInstaller 打包运行
    current_dir = getattr(
        sys,
        '_MEIPASS',
        os.path.dirname(os.path.abspath(__file__))
    )

    current_dir = os.path.abspath(current_dir)

    fontTTF = os.path.join(current_dir, "conf", "SimHei.ttf")
    font_prop = FontProperties(fname=fontTTF)
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams.update({'font.size': 14})

    # stpe1 配置文件加载及解析
    # 在输出目录下创建文件同名的文件夹，以存放产品
    new_dir_path = os.path.join(ipf_config.output, "MDS_" + ipf_config.Sat_ID + "_" +
                                ipf_config.Product_Type + "_SELF_CROSS_" +
                                ipf_config.Start_date + "_" + ipf_config.End_date + "_V" +
                                ipf_config.Data_version)
    os.makedirs(new_dir_path, exist_ok=True)
    outputPath = new_dir_path
    # 将生产的nc等文件放到outputPath目录下。
    # +-------------此处添加核心处理代码-----------------------#
    Logger.info("Start data processing")
    Logger.info("Get file list in input directory within specified time range")
    # 根据关键字ipf_config.Sat_ID和起止时间ipf_config.Start_date和ipf_config.End_date获取输入目录下在这个时间范围的文件列表
    input_file_list = sorted(get_file_list(
        ipf_config.input, ipf_config.Sat_ID,
        ipf_config.Start_date, ipf_config.End_date
    ))

    Logger.info("Start data reading")

    # 定义数据读取函数
    def normalize_longitude(lon):
        """将经度统一到[-180, 180]范围"""
        lon = np.array(lon)
        lon[lon > 180] = lon[lon > 180] - 360
        return lon

    def seconds_to_date(time_seconds):
        """将秒数转换为日期整数 (YYYYMMDD)"""
        ref_date = datetime(2000, 1, 1)
        date = ref_date + timedelta(seconds=float(time_seconds))
        return int(date.strftime('%Y%m%d'))

    def read_satellite_nc(filepath, sat_id):
        """根据卫星ID读取对应的NC文件，包含属性信息"""
        try:
            import h5py
            with h5py.File(filepath, 'r') as f:
                lon = f['data_01/longitude'][:].astype(float) / 1e6
                lat = f['data_01/latitude'][:].astype(float) / 1e6
                ssh_raw = f['data_01/ku/ssha'][:].astype(float)
                time = f['data_01/time'][:].astype(float)

                # 读取属性数据
                distance_to_coast = f['data_01/distance_to_coast'][:].astype(float)
                # Jason-3单位是mm，转换为km
                if 'JA3' in sat_id.upper() or 'JASON3' in sat_id.upper():
                    distance_to_coast = distance_to_coast / 1000.0

                depth = f['data_01/depth_or_elevation'][:].astype(float)
                wind_speed_raw = f['data_01/wind_speed_alt'][:].astype(float)
                wind_speed = wind_speed_raw * 0.01  # 转换为 m/s

                # 根据卫星ID设置不同的参数
                sat_id_upper = sat_id.upper()
                if sat_id_upper == 'S6A':
                    # Sentinel-6: 填充值2147483647，单位0.1mm，除以10000得到米
                    fill_value = 2147483647
                    valid_mask = (ssh_raw != fill_value) & (~np.isnan(ssh_raw))
                    ssh = ssh_raw[valid_mask] / 10000.0
                elif sat_id_upper == 'JASON3' or sat_id_upper == 'JA3':
                    # Jason-3: 填充值32767，单位mm，除以1000得到米
                    fill_value = 32767
                    valid_mask = (ssh_raw != fill_value) & (~np.isnan(ssh_raw))
                    ssh = ssh_raw[valid_mask] / 1000.0
                else:
                    Logger.error(f"不支持的卫星ID: {sat_id}")
                    return None

                lon = normalize_longitude(lon[valid_mask])
                lat = lat[valid_mask]
                time = time[valid_mask]
                distance_to_coast = distance_to_coast[valid_mask]
                depth = depth[valid_mask]
                wind_speed = wind_speed[valid_mask]

                # 过滤明显异常值（超过±3米）
                valid_ssh_mask = np.abs(ssh) < 3
                ssh = ssh[valid_ssh_mask]
                lon = lon[valid_ssh_mask]
                lat = lat[valid_ssh_mask]
                time = time[valid_ssh_mask]
                distance_to_coast = distance_to_coast[valid_ssh_mask]
                depth = depth[valid_ssh_mask]
                wind_speed = wind_speed[valid_ssh_mask]

                # 过滤无效的离岸距离
                valid_coast_mask = (distance_to_coast >= 0) & (distance_to_coast < 20000)
                ssh = ssh[valid_coast_mask]
                lon = lon[valid_coast_mask]
                lat = lat[valid_coast_mask]
                time = time[valid_coast_mask]
                distance_to_coast = distance_to_coast[valid_coast_mask]
                depth = depth[valid_coast_mask]
                wind_speed = wind_speed[valid_coast_mask]

                return {
                    'lon': lon, 'lat': lat, 'ssh': ssh, 'time': time,
                    'distance_to_coast': distance_to_coast,
                    'depth': depth,
                    'wind_speed': wind_speed
                }
        except Exception as e:
            Logger.error(f"读取文件 {filepath} 失败: {e}")
            return None

    # 获取卫星ID
    sat_id = ipf_config.Sat_ID
    Logger.info(f"开始读取 {len(input_file_list)} 个{sat_id}数据文件")

    all_data = []
    for idx, filepath in enumerate(input_file_list):
        Logger.info(f"读取文件 {idx + 1}/{len(input_file_list)}: {os.path.basename(filepath)}")
        data = read_satellite_nc(filepath, sat_id)
        if data is not None and len(data['ssh']) > 0:
            all_data.append(data)

    Logger.info(f"成功读取 {len(all_data)} 个文件的数据")

    Logger.info("Start data matching")
    # 目标区域
    target_lon_min = -180
    target_lon_max = 180
    target_lat_min = -60
    target_lat_max = 60

    # 匹配参数
    max_distance_km = 15
    min_points = 4

    def haversine_distance(lon1, lat1, lon2, lat2):
        """计算两点间的大圆距离（km）"""
        R = 6371.0
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

    def determine_track_direction(lat, time):
        """根据每个 GDR 文件内的时间顺序和纬度变化判断升降轨。

        返回：升轨 +1、降轨 -1、无法判定 0。
        只利用相邻时间差在 (0, 120] 秒内的观测，避免跨数据缺口误判。
        """
        lat = np.asarray(lat, dtype=float)
        time = np.asarray(time, dtype=float)

        if len(lat) != len(time):
            raise ValueError("纬度与时间数组长度不一致")

        direction = np.zeros(len(time), dtype=np.int8)
        if len(time) < 2:
            return direction

        order = np.argsort(time, kind='stable')
        phi = lat[order]
        t = time[order]

        dt = np.diff(t)
        dlat = np.diff(phi)
        valid = (
            (dt > 0) & (dt <= 120)
            & np.isfinite(phi[:-1]) & np.isfinite(phi[1:])
            & np.isfinite(t[:-1]) & np.isfinite(t[1:])
        )

        rate = np.full(len(dt), np.nan, dtype=float)
        rate[valid] = dlat[valid] / dt[valid]

        before = np.r_[np.nan, rate]
        after = np.r_[rate, np.nan]
        counts = np.isfinite(before).astype(int) + np.isfinite(after).astype(int)
        velocity = np.zeros(len(t), dtype=float)
        np.divide(
            np.nan_to_num(before, nan=0.0) + np.nan_to_num(after, nan=0.0),
            counts,
            out=velocity,
            where=counts > 0,
        )

        # 纬度随时间增加为升轨，纬度随时间减少为降轨
        direction_sorted = np.zeros(len(t), dtype=np.int8)
        direction_sorted[velocity > 0.0001] = 1
        direction_sorted[velocity < -0.0001] = -1
        direction[order] = direction_sorted
        return direction

    def split_by_track_direction(lon, lat, ssh, time, dates, distance_to_coast, depth, wind_speed, direction):
        """使用各 GDR 文件预先计算好的升降轨方向分割数据"""

        ascending_mask = direction == 1
        descending_mask = direction == -1

        ascending_data = {
            'lon': lon[ascending_mask],
            'lat': lat[ascending_mask],
            'ssh': ssh[ascending_mask],
            'time': time[ascending_mask],
            'dates': dates[ascending_mask],
            'distance_to_coast': distance_to_coast[ascending_mask],
            'depth': depth[ascending_mask],
            'wind_speed': wind_speed[ascending_mask]
        }

        descending_data = {
            'lon': lon[descending_mask],
            'lat': lat[descending_mask],
            'ssh': ssh[descending_mask],
            'time': time[descending_mask],
            'dates': dates[descending_mask],
            'distance_to_coast': distance_to_coast[descending_mask],
            'depth': depth[descending_mask],
            'wind_speed': wind_speed[descending_mask]
        }

        return ascending_data, descending_data

    def cross_track_matching(lon_A, lat_A, ssh_A, lon_B, lat_B, ssh_B,
                             max_distance_km=10, min_points=5):
        """轨道交叉点匹配方法"""
        from scipy.spatial import cKDTree

        points_B = np.column_stack((lon_B, lat_B))
        tree_B = cKDTree(points_B)

        ssh_B_interp = np.zeros(len(lon_A)) * np.nan
        match_distances = []
        match_indices = []
        match_std = []

        for i in range(len(lon_A)):
            if np.isnan(ssh_A[i]):
                continue

            indices = tree_B.query_ball_point([lon_A[i], lat_A[i]],
                                              r=max_distance_km / 111.32)

            if len(indices) < min_points:
                continue

            lon_B_local = lon_B[indices]
            lat_B_local = lat_B[indices]
            ssh_B_local = ssh_B[indices]

            distances = np.array([haversine_distance(lon_A[i], lat_A[i],
                                                     lon_B_local[j], lat_B_local[j])
                                  for j in range(len(lon_B_local))])

            valid_mask = distances <= max_distance_km
            valid_distances = distances[valid_mask]
            valid_ssh = ssh_B_local[valid_mask]

            if len(valid_ssh) < min_points:
                continue

            ssh_std = np.std(valid_ssh)
            if ssh_std > 0.2:
                continue

            idw_weights = 1.0 / (valid_distances ** 2 + 1e-10)
            idw_weights = idw_weights / np.sum(idw_weights)
            idw_value = np.average(valid_ssh, weights=idw_weights)

            sigma = max_distance_km / 3
            gaussian_weights = np.exp(-(valid_distances ** 2) / (2 * sigma ** 2))
            gaussian_weights = gaussian_weights / np.sum(gaussian_weights)
            gaussian_value = np.average(valid_ssh, weights=gaussian_weights)

            ssh_B_interp[i] = (idw_value + gaussian_value) / 2

            match_distances.append(np.mean(valid_distances))
            match_indices.append(i)
            match_std.append(ssh_std)

        return ssh_B_interp, np.array(match_distances), np.array(match_indices), np.array(match_std)

    # 合并所有数据并进行区域筛选
    Logger.info("合并数据并进行区域筛选")

    if not all_data:
        raise FileNotFoundError("没有成功读取到可用的卫星观测数据，请检查输入路径和文件内容")

    # 每个原始 GDR 文件独立判断升降轨；避免合并天数改变同一文件的判断结果
    combined = {
        'direction': np.concatenate([
            determine_track_direction(d['lat'], d['time'])
            for d in all_data
        ]),
        'lon': np.concatenate([d['lon'] for d in all_data]),
        'lat': np.concatenate([d['lat'] for d in all_data]),
        'ssh': np.concatenate([d['ssh'] for d in all_data]),
        'time': np.concatenate([d['time'] for d in all_data]),
        'distance_to_coast': np.concatenate([d['distance_to_coast'] for d in all_data]),
        'depth': np.concatenate([d['depth'] for d in all_data]),
        'wind_speed': np.concatenate([d['wind_speed'] for d in all_data])
    }

    # 区域筛选
    mask = (combined['lon'] >= target_lon_min) & (combined['lon'] <= target_lon_max) & \
           (combined['lat'] >= target_lat_min) & (combined['lat'] <= target_lat_max)

    combined['lon'] = combined['lon'][mask]
    combined['lat'] = combined['lat'][mask]
    combined['ssh'] = combined['ssh'][mask]
    combined['time'] = combined['time'][mask]
    combined['distance_to_coast'] = combined['distance_to_coast'][mask]
    combined['depth'] = combined['depth'][mask]
    combined['wind_speed'] = combined['wind_speed'][mask]
    combined['direction'] = combined['direction'][mask]
    combined['dates'] = np.array([seconds_to_date(t) for t in combined['time']])

    Logger.info(f"区域筛选后总点数: {len(combined['ssh'])}")
    Logger.info(f"SSH范围: [{np.nanmin(combined['ssh']):.3f}, {np.nanmax(combined['ssh']):.3f}] m")

    # 分割上升轨和下降轨
    Logger.info("分割上升轨和下降轨数据...")
    ascending_data, descending_data = split_by_track_direction(
        combined['lon'], combined['lat'], combined['ssh'],
        combined['time'], combined['dates'],
        combined['distance_to_coast'], combined['depth'],
        combined['wind_speed'], combined['direction']
    )

    Logger.info(f"上升轨点数: {len(ascending_data['ssh'])}")
    Logger.info(f"下降轨点数: {len(descending_data['ssh'])}")

    if len(ascending_data['ssh']) < 100 or len(descending_data['ssh']) < 100:
        Logger.error("上升轨或下降轨数据点太少，无法进行有效分析")
        raise Exception("Insufficient data points")

    # 按日期分组
    Logger.info("按日期分组...")
    ascending_dates = np.unique(ascending_data['dates'])
    descending_dates = np.unique(descending_data['dates'])
    common_dates = np.intersect1d(ascending_dates, descending_dates)

    Logger.info(f"共同日期数量: {len(common_dates)}")

    if len(common_dates) == 0:
        Logger.error("没有共同日期！")
        raise Exception("No common dates found")

    # 按日期组织数据
    ascending_by_date = {}
    descending_by_date = {}

    for date in common_dates:
        asc_mask = ascending_data['dates'] == date
        desc_mask = descending_data['dates'] == date

        if np.sum(asc_mask) > 100 and np.sum(desc_mask) > 100:
            ascending_by_date[date] = {
                'lon': ascending_data['lon'][asc_mask],
                'lat': ascending_data['lat'][asc_mask],
                'ssh': ascending_data['ssh'][asc_mask],
                'time': ascending_data['time'][asc_mask],
                'distance_to_coast': ascending_data['distance_to_coast'][asc_mask],
                'depth': ascending_data['depth'][asc_mask],
                'wind_speed': ascending_data['wind_speed'][asc_mask]
            }

            descending_by_date[date] = {
                'lon': descending_data['lon'][desc_mask],
                'lat': descending_data['lat'][desc_mask],
                'ssh': descending_data['ssh'][desc_mask],
                'distance_to_coast': descending_data['distance_to_coast'][desc_mask],
                'depth': descending_data['depth'][desc_mask],
                'wind_speed': descending_data['wind_speed'][desc_mask]
            }

    Logger.info(f"有足够数据的共同日期数量: {len(ascending_by_date)}")

    if len(ascending_by_date) == 0:
        Logger.error("没有找到有足够数据的共同日期！")
        raise Exception("No dates with sufficient data")

    # 空间匹配
    Logger.info("开始空间匹配...")

    all_matches = []

    for date_idx, date in enumerate(list(ascending_by_date.keys())):
        if date not in descending_by_date:
            continue

        Logger.info(f"处理日期 {date} ({date_idx + 1}/{len(ascending_by_date)})")

        asc_data = ascending_by_date[date]
        desc_data = descending_by_date[date]

        desc_interp, distances, valid_indices, stds = cross_track_matching(
            asc_data['lon'], asc_data['lat'], asc_data['ssh'],
            desc_data['lon'], desc_data['lat'], desc_data['ssh'],
            max_distance_km=max_distance_km, min_points=min_points
        )

        date_matches = 0
        for idx in range(len(valid_indices)):
            i = valid_indices[idx]
            if not np.isnan(desc_interp[i]):
                match_record = {
                    'date': int(date),
                    'time_asc': float(asc_data['time'][i]),
                    'lon': float(asc_data['lon'][i]),
                    'lat': float(asc_data['lat'][i]),
                    'ssh_asc': float(asc_data['ssh'][i]),
                    'ssh_desc': float(desc_interp[i]),
                    'diff': float(asc_data['ssh'][i] - desc_interp[i]),
                    'distance': float(distances[idx]),
                    'std': float(stds[idx]),
                    'distance_to_coast': float(asc_data['distance_to_coast'][i]),
                    'depth': float(asc_data['depth'][i]),
                    'wind_speed': float(asc_data['wind_speed'][i])
                }
                all_matches.append(match_record)
                date_matches += 1

        if date_matches > 0:
            avg_dist = np.mean(distances)
            avg_std = np.mean(stds)
            Logger.info(f"  匹配点数: {date_matches} (平均距离: {avg_dist:.2f}km, 平均STD: {avg_std:.3f}m)")

    Logger.info(f"总匹配点数: {len(all_matches)}")

    if len(all_matches) == 0:
        Logger.error("没有找到匹配点！")
        raise Exception("No matching points found")

    # ==================== 对匹配点进行筛选统计 ====================
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

    total_match = len(all_matches)

    # 提取匹配点的属性数组
    match_lons = np.array([m['lon'] for m in all_matches])
    match_lats = np.array([m['lat'] for m in all_matches])
    match_coast = np.array([m.get('distance_to_coast', np.nan) for m in all_matches])
    match_depth = np.array([m.get('depth', np.nan) for m in all_matches])
    match_wind = np.array([m.get('wind_speed', np.nan) for m in all_matches])

    # 统计各筛选条件通过的点数
    # 1. 经纬度筛选
    lon_mask = (match_lons >= min_lon) & (match_lons <= max_lon)
    lat_mask = (match_lats >= min_lat) & (match_lats <= max_lat)
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
        'pass_area': int(pass_area),
        'pass_coast': int(pass_coast),
        'pass_depth': int(pass_depth),
        'pass_wind': int(pass_wind),
        'pass_all': int(pass_all),
        'thresholds': {
            'lat_range': [min_lat, max_lat],
            'lon_range': [min_lon, max_lon],
            'distance_to_coast': distance_threshold,
            'ocean_depth': depth_threshold,
            'wind_speed': [wind_min, wind_max]
        }
    }

    # 保存匹配结果
    import pandas as pd
    df_matches = pd.DataFrame(all_matches)

    # 使用Sat_ID作为文件名前缀
    sat_id = ipf_config.Sat_ID
    match_result_file = os.path.join(outputPath,
                                     f"{sat_id}_self_cross_matches_{ipf_config.Start_date}_{ipf_config.End_date}.csv")
    df_matches.to_csv(match_result_file, index=False)
    Logger.info(f"匹配结果已保存到: {match_result_file}")

    # 保存为Parquet格式（包含属性和统计信息）
    try:
        match_result_parquet = os.path.join(outputPath,
                                            f"{sat_id}_self_cross_matches_{ipf_config.Start_date}_{ipf_config.End_date}.parquet")
        # 将统计信息保存为单独的文件
        import json
        stats_file = os.path.join(outputPath,
                                  f"{sat_id}_self_cross_match_stats_{ipf_config.Start_date}_{ipf_config.End_date}.json")
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(match_stats, f, ensure_ascii=False, indent=2)

        df_matches.to_parquet(match_result_parquet, index=False)
        Logger.info(f"匹配结果(Parquet)已保存到: {match_result_parquet}")
        Logger.info(f"筛选统计已保存到: {stats_file}")
    except Exception as e:
        Logger.warn(f"Parquet格式保存失败: {e}")

    Logger.info("数据匹配处理完成")

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
        "statistics": match_stats,  
            # total_match/pass_area/pass_coast/pass_depth/pass_wind/pass_all/thresholds
        "output_files": {
            "csv": match_result_file.replace('\\', '/'),
            "parquet": match_result_parquet.replace('\\', '/') if 'match_result_parquet' in dir() else None,
            "stats_json": stats_file.replace('\\', '/') if 'stats_file' in dir() else None,
        },
        "output_dir": os.path.abspath(outputPath.replace('\\', '/')),
        "success": True,
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

    # 修复返回问题 
    return file_list