import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import os
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 多文件卫星数据批量处理
data_dir = 'E:\星星交叉定标\星星交叉法\CVS_GLSY_ALT_GDR_AUX_SAT_MATCH'

sentinel6_filenames = [
#    'cmems_obs-sl_glo_phy-ssh_nrt_s6a-hr-l3-duacs_PT1S_1761810623584.csv',
#    'cmems_obs-sl_glo_phy-ssh_nrt_s6a-hr-l3-duacs_PT1S_1761810673816.csv',
#    'cmems_obs-sl_glo_phy-ssh_nrt_s6a-hr-l3-duacs_PT1S_1761810731642.csv',
   'cmems_obs-sl_glo_phy-ssh_nrt_s6a-hr-l3-duacs_PT1S_1761810776964.csv'
]

jason3_filenames = [
#    'cmems_obs-sl_glo_phy-ssh_nrt_j3n-l3-duacs_PT1S_1761540422964.csv',
#    'cmems_obs-sl_glo_phy-ssh_nrt_j3n-l3-duacs_PT1S_1761569636861.csv',  
#    'cmems_obs-sl_glo_phy-ssh_nrt_j3n-l3-duacs_PT1S_1761569701379.csv',
   'cmems_obs-sl_glo_phy-ssh_nrt_j3n-l3-duacs_PT1S_1761569758425.csv'
]

# target_lon_min = -180
# target_lon_max = -120
# target_lat_min = 0
# target_lat_max = 50
target_lon_min = -180
target_lon_max = 180
target_lat_min = -60
target_lat_max = 60

print('============================================================')
print('多文件卫星数据批量交叉定标分析')
print('============================================================')
print(f'Sentinel-6文件数量: {len(sentinel6_filenames)}')
print(f'Jason-3文件数量: {len(jason3_filenames)}')
print(f'目标区域: 经度[{target_lon_min:.1f}, {target_lon_max:.1f}], 纬度[{target_lat_min:.1f}, {target_lat_max:.1f}]')

# 读取所有Sentinel-6数据
print('\n============================================================')
print('读取所有Sentinel-6数据文件')
print('============================================================')

all_sentinel6_data = []
sentinel6_file_count = 0

for i, filename in enumerate(sentinel6_filenames):
    filepath = os.path.join(data_dir, filename)
    
    print(f'\n读取Sentinel-6文件 {i+1}/{len(sentinel6_filenames)}: {filename}')
    
    if not os.path.exists(filepath):
        print('  文件不存在，跳过')
        continue
    
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        data_start_line = 0#有什么用？
        for j, line in enumerate(lines):
            if not line.startswith('#'):
                data_start_line = j
                break
        
        sentinel6_table = pd.read_csv(filepath, comment='#', skip_blank_lines=True)
        
        if sentinel6_table.empty:
            print('  数据为空，跳过')
            continue
        
        lon_col = None
        lat_col = None
        ssh_col = None
        time_col = None
        
        for col in sentinel6_table.columns:
            col_lower = col.lower()
            if 'lon' in col_lower or 'longitude' in col_lower:
                lon_col = col
            elif 'lat' in col_lower or 'latitude' in col_lower:
                lat_col = col
            elif ('ssh' in col_lower or 'value' in col_lower or 'sla' in col_lower or 'adt' in col_lower) and 'qc' not in col_lower:
                ssh_col = col
            elif 'time' in col_lower or 'date' in col_lower:
                time_col = col
        
        if not all([lon_col, lat_col, ssh_col, time_col]):
            if len(sentinel6_table.columns) >= 4:
                lon_col = sentinel6_table.columns[0]
                lat_col = sentinel6_table.columns[1]
                ssh_col = sentinel6_table.columns[2]
                time_col = sentinel6_table.columns[3]
            else:
                continue
        
        lon_data = sentinel6_table[lon_col].values
        lat_data = sentinel6_table[lat_col].values
        ssh_data = sentinel6_table[ssh_col].values
        time_data = sentinel6_table[time_col].values
        
        region_mask = (lon_data >= target_lon_min) & (lon_data <= target_lon_max) & \
                     (lat_data >= target_lat_min) & (lat_data <= target_lat_max)
        
        print(f'  原始数据点数: {len(lon_data)}')
        print(f'  区域筛选后点数: {np.sum(region_mask)}')
        
        if np.any(region_mask):
            lon_region = lon_data[region_mask]
            lat_region = lat_data[region_mask]
            ssh_region = ssh_data[region_mask]
            time_region = time_data[region_mask]
            
            valid_mask = ~np.isnan(ssh_region)
            lon_region = lon_region[valid_mask]
            lat_region = lat_region[valid_mask]
            ssh_region = ssh_region[valid_mask]
            time_region = time_region[valid_mask]
           
            if len(ssh_region) > 0:
                date_nums = np.zeros(len(time_region))
                for j in range(len(time_region)):
                    time_str = str(time_region[j])
                    if len(time_str) >= 10:
                        date_str = time_str[:10]
                        date_parts = date_str.split('-')
                        if len(date_parts) == 3:
                            date_nums[j] = int(date_parts[0] + date_parts[1] + date_parts[2])
                        else:
                            date_nums[j] = j + 1
                    else:
                        date_nums[j] = j + 1
                
                sentinel6_file_count += 1
                file_data = {
                    'filename': filename,
                    'lon': lon_region,
                    'lat': lat_region,
                    'ssh': ssh_region,
                    'dates': date_nums,
                    'unique_dates': np.unique(date_nums)
                }
                all_sentinel6_data.append(file_data)
                
                unique_dates_all = np.unique(date_nums)
                print(f'  成功读取，包含 {len(unique_dates_all)} 个日期')
                print(f'  SLA范围: [{np.min(ssh_region):.4f}, {np.max(ssh_region):.4f}] m')
        
    except Exception as e:
        print(f'  读取失败: {str(e)}')

print(f'\n成功读取 {sentinel6_file_count}/{len(sentinel6_filenames)} 个Sentinel-6文件')

# 读取所有Jason-3数据
print('\n============================================================')
print('读取所有Jason-3数据文件')
print('============================================================')

all_jason3_data = []
jason3_file_count = 0

for i, filename in enumerate(jason3_filenames):
    filepath = os.path.join(data_dir, filename)
    
    print(f'\n读取Jason-3文件 {i+1}/{len(jason3_filenames)}: {filename}')
    
    if not os.path.exists(filepath):
        print('  文件不存在，跳过')
        continue
    
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
        
        data_start_line = 0
        for j, line in enumerate(lines):
            if not line.startswith('#'):
                data_start_line = j
                break
        
        jason3_table = pd.read_csv(filepath, comment='#', skip_blank_lines=True)
        
        if jason3_table.empty:
            continue
        
        lon_col = None
        lat_col = None
        ssh_col = None
        time_col = None
        
        for col in jason3_table.columns:
            col_lower = col.lower()
            if 'lon' in col_lower or 'longitude' in col_lower:
                lon_col = col
            elif 'lat' in col_lower or 'latitude' in col_lower:
                lat_col = col
            elif ('ssh' in col_lower or 'value' in col_lower or 'sla' in col_lower or 'adt' in col_lower) and 'qc' not in col_lower:
                ssh_col = col
            elif 'time' in col_lower or 'date' in col_lower:
                time_col = col
        
        if not all([lon_col, lat_col, ssh_col, time_col]):
            if len(jason3_table.columns) >= 4:
                lon_col = jason3_table.columns[0]
                lat_col = jason3_table.columns[1]
                ssh_col = jason3_table.columns[2]
                time_col = jason3_table.columns[3]
            else:
                continue
        
        lon_data = jason3_table[lon_col].values
        lat_data = jason3_table[lat_col].values
        ssh_data = jason3_table[ssh_col].values
        time_data = jason3_table[time_col].values
        
        region_mask = (lon_data >= target_lon_min) & (lon_data <= target_lon_max) & \
                     (lat_data >= target_lat_min) & (lat_data <= target_lat_max)
        
        print(f'  原始数据点数: {len(lon_data)}')
        print(f'  区域筛选后点数: {np.sum(region_mask)}')
        
        if np.any(region_mask):
            lon_region = lon_data[region_mask]
            lat_region = lat_data[region_mask]
            ssh_region = ssh_data[region_mask]
            time_region = time_data[region_mask]
            
            valid_mask = ~np.isnan(ssh_region)
            lon_region = lon_region[valid_mask]
            lat_region = lat_region[valid_mask]
            ssh_region = ssh_region[valid_mask]
            time_region = time_region[valid_mask]
            
            if len(ssh_region) > 0:
                date_nums = np.zeros(len(time_region))
                for j in range(len(time_region)):
                    time_str = str(time_region[j])
                    if len(time_str) >= 10:
                        date_str = time_str[:10]
                        date_parts = date_str.split('-')
                        if len(date_parts) == 3:
                            date_nums[j] = int(date_parts[0] + date_parts[1] + date_parts[2])
                        else:
                            date_nums[j] = j + 1
                    else:
                        date_nums[j] = j + 1
                
                jason3_file_count += 1
                file_data = {
                    'filename': filename,
                    'lon': lon_region,
                    'lat': lat_region,
                    'ssh': ssh_region,
                    'dates': date_nums,
                    'unique_dates': np.unique(date_nums)
                }
                all_jason3_data.append(file_data)
                
                unique_dates_all = np.unique(date_nums)
                print(f'  成功读取，包含 {len(unique_dates_all)} 个日期')
                print(f'  SLA范围: [{np.min(ssh_region):.4f}, {np.max(ssh_region):.4f}] m')
        
    except Exception as e:
        print(f'  读取失败: {str(e)}')

print(f'\n成功读取 {jason3_file_count}/{len(jason3_filenames)} 个Jason-3文件')

# 合并所有数据并按日期组织
print('\n============================================================')
print('合并所有数据并按日期组织')
print('============================================================')

if sentinel6_file_count > 0:
    all_sentinel6_combined = {
        'lon': np.array([]),
        'lat': np.array([]),
        'ssh': np.array([]),
        'dates': np.array([])
    }
    
    for i in range(sentinel6_file_count):
        all_sentinel6_combined['lon'] = np.concatenate([all_sentinel6_combined['lon'], all_sentinel6_data[i]['lon']])
        all_sentinel6_combined['lat'] = np.concatenate([all_sentinel6_combined['lat'], all_sentinel6_data[i]['lat']])
        all_sentinel6_combined['ssh'] = np.concatenate([all_sentinel6_combined['ssh'], all_sentinel6_data[i]['ssh']])
        all_sentinel6_combined['dates'] = np.concatenate([all_sentinel6_combined['dates'], all_sentinel6_data[i]['dates']])
    
    all_sentinel6_combined['unique_dates'] = np.unique(all_sentinel6_combined['dates'])
    
    print('Sentinel-6合并数据统计:')
    print(f'  总点数: {len(all_sentinel6_combined["ssh"])}')
    print(f'  SLA范围: [{np.min(all_sentinel6_combined["ssh"]):.4f}, {np.max(all_sentinel6_combined["ssh"]):.4f}] m')
else:
    print('无有效的Sentinel-6数据')
    all_sentinel6_combined = {}

if jason3_file_count > 0:
    all_jason3_combined = {
        'lon': np.array([]),
        'lat': np.array([]),
        'ssh': np.array([]),
        'dates': np.array([])
    }
    
    for i in range(jason3_file_count):
        all_jason3_combined['lon'] = np.concatenate([all_jason3_combined['lon'], all_jason3_data[i]['lon']])
        all_jason3_combined['lat'] = np.concatenate([all_jason3_combined['lat'], all_jason3_data[i]['lat']])
        all_jason3_combined['ssh'] = np.concatenate([all_jason3_combined['ssh'], all_jason3_data[i]['ssh']])
        all_jason3_combined['dates'] = np.concatenate([all_jason3_combined['dates'], all_jason3_data[i]['dates']])
    
    all_jason3_combined['unique_dates'] = np.unique(all_jason3_combined['dates'])
    
    print('Jason-3合并数据统计:')
    print(f'  总点数: {len(all_jason3_combined["ssh"])}')
    print(f'  SLA范围: [{np.min(all_jason3_combined["ssh"]):.4f}, {np.max(all_jason3_combined["ssh"]):.4f}] m')
else:
    print('无有效的Jason-3数据')
    all_jason3_combined = {}

# 按日期组织数据
print('\n============================================================')
print('按日期组织数据 - 只匹配相同日期的数据')
print('============================================================')

if all_sentinel6_combined and all_jason3_combined and \
   'unique_dates' in all_sentinel6_combined and 'unique_dates' in all_jason3_combined and \
   len(all_sentinel6_combined['unique_dates']) > 0 and len(all_jason3_combined['unique_dates']) > 0:
    
    common_dates = np.intersect1d(all_sentinel6_combined['unique_dates'], all_jason3_combined['unique_dates'])
    print(f'两个数据集有 {len(common_dates)} 个共同日期')
    
    if len(common_dates) == 0:
        print('警告：没有找到共同日期！无法进行时间匹配的交叉定标。')
    else:
        sentinel6_by_date = []
        for date_num in common_dates:
            date_mask = (all_sentinel6_combined['dates'] == date_num)
            if np.any(date_mask):
                date_data = {
                    'date_num': date_num,
                    'lon': all_sentinel6_combined['lon'][date_mask],
                    'lat': all_sentinel6_combined['lat'][date_mask],
                    'ssh': all_sentinel6_combined['ssh'][date_mask],
                     'count': np.sum(date_mask)
                }
                sentinel6_by_date.append(date_data)
        
        jason3_by_date = []
        for date_num in common_dates:
            date_mask = (all_jason3_combined['dates'] == date_num)
            if np.any(date_mask):
                date_data = {
                    'date_num': date_num,
                    'lon': all_jason3_combined['lon'][date_mask],
                    'lat': all_jason3_combined['lat'][date_mask],
                    'ssh': all_jason3_combined['ssh'][date_mask],
                    'count': np.sum(date_mask)
                }
                jason3_by_date.append(date_data)
    
else:
    print('至少有一个数据集为空或缺少日期信息，无法进行日期匹配')
    common_dates = np.array([])
    sentinel6_by_date = []
    jason3_by_date = []

# 空间匹配
print('\n============================================================')
print('空间匹配')
print('============================================================')

max_total_points = 5000000
min_data_points = 20
spatial_threshold_km = 25
min_neighbors = 4

point_count = 0
ssh_diff = np.full(max_total_points, np.nan)
ssh_satA = np.full(max_total_points, np.nan)
ssh_satB = np.full(max_total_points, np.nan)

if len(common_dates) > 0 and len(sentinel6_by_date) > 0 and len(jason3_by_date) > 0:
    print(f'开始处理 {len(common_dates)} 个共同日期')
    
    for date_idx in range(len(common_dates)):
        if point_count >= max_total_points:
            break
        
        if date_idx >= len(sentinel6_by_date) or date_idx >= len(jason3_by_date):
            continue
        
        current_date = common_dates[date_idx]
        
        sentinel6_data = sentinel6_by_date[date_idx]
        lon_A_all = sentinel6_data['lon']
        lat_A_all = sentinel6_data['lat']
        ssh_A_all = sentinel6_data['ssh']
        
        jason3_data = jason3_by_date[date_idx]
        lon_B_all = jason3_data['lon']
        lat_B_all = jason3_data['lat']
        ssh_B_all = jason3_data['ssh']
        
        print(f'处理日期 {int(current_date)} ({date_idx+1}/{len(common_dates)}): Sentinel-6点: {len(lon_A_all)}, Jason-3点: {len(lon_B_all)}')
        
        if len(lon_A_all) == 0 or len(lon_B_all) == 0 or len(lon_B_all) < min_data_points:
            continue
        
        try:
            lon_B_all = lon_B_all.astype(float)
            lat_B_all = lat_B_all.astype(float)
            ssh_B_all = ssh_B_all.astype(float)
            lon_A_all = lon_A_all.astype(float)
            lat_A_all = lat_A_all.astype(float)
            
            points_B = np.column_stack((lon_B_all, lat_B_all))
            ssh_B_interp = griddata(points_B, ssh_B_all, (lon_A_all, lat_A_all), method='linear', fill_value=np.nan)
            #绘制lon_A_all和lat_A_all在全球地图上的位置，用不同颜色表示ssh_B_interp的值，看看插值结果是否合理,边缘无颜色
            # plt.figure(figsize=(8, 6))
            # sc = plt.scatter(lon_A_all, lat_A_all, c=ssh_B_interp, cmap='viridis', s=5, edgecolor='none')
            # plt.colorbar(sc, label='Interpolated SSH (m)')
            # plt.xlabel('Longitude')
            # plt.ylabel('Latitude')
            # plt.title(f'Interpolated SSH for Date {current_date}')
            # plt.show()
            # #在上图基础上，绘制lon_B_all和lat_B_all在全球地图上的位置，用不同颜色表示ssh_B_all的值，看看原始数据点的位置和插值结果的关系
            # plt.figure(figsize=(8, 6))
            # sc = plt.scatter(lon_B_all, lat_B_all, c=ssh_B_all, cmap='viridis', s=5, edgecolor='none')
            # plt.colorbar(sc, label='Original SSH (m)')
            # plt.xlabel('Longitude')
            # plt.ylabel('Latitude')
            # plt.title(f'Original SSH for Date {current_date}')
            # plt.show()
           
            distances = np.zeros(len(lon_A_all))
            for i in range(len(lon_A_all)):
                dists = np.sqrt((lon_B_all - lon_A_all[i])**2 + (lat_B_all - lat_A_all[i])**2)
                distances[i] = np.min(dists) * 111.32
            
            valid_mask = ~np.isnan(ssh_B_interp) & \
                        (distances <= spatial_threshold_km) & \
                        ~np.isnan(ssh_A_all)
            
            for i in range(len(lon_A_all)):
                if valid_mask[i]:
                    neighbor_mask = np.sqrt((lon_B_all - lon_A_all[i])**2 + \
                                           (lat_B_all - lat_A_all[i])**2) <= (spatial_threshold_km/111.32)
                    if np.sum(neighbor_mask) < min_neighbors:
                        valid_mask[i] = False
            
            num_valid = np.sum(valid_mask)
            
            if num_valid > 0:
                end_idx = point_count + num_valid
                indices = slice(point_count, end_idx)
                
                ssh_satA[indices] = ssh_A_all[valid_mask]
                ssh_satB[indices] = ssh_B_interp[valid_mask]
                ssh_diff[indices] = ssh_A_all[valid_mask] - ssh_B_interp[valid_mask]
                
                point_count = end_idx
                
                avg_distance = np.mean(distances[valid_mask])
                interp_quality = num_valid / len(lon_A_all) * 100
                
                print(f'  优化插值: {num_valid} 点 (成功率: {interp_quality:.1f}%, 平均距离: {avg_distance:.1f}km)')
            
        except Exception as e:
            print(f'  插值失败: {str(e)}')
else:
    print('无共同日期数据，无法进行时间匹配的交叉定标')

if point_count > 0:
    ssh_diff = ssh_diff[:point_count]
    ssh_satA = ssh_satA[:point_count]
    ssh_satB = ssh_satB[:point_count]
else:
    ssh_diff = np.array([])
    ssh_satA = np.array([])
    ssh_satB = np.array([])

# 异常值处理
print('\n============================================================')
print('异常值处理')
print('============================================================')

if point_count > 0:
    original_count = point_count
    original_mean = np.nanmean(ssh_diff)
    original_std = np.nanstd(ssh_diff)
    
    threshold_cm = 15
    threshold_m = threshold_cm / 100
    
    outlier_mask = np.abs(ssh_diff) > threshold_m
    num_outliers = np.sum(outlier_mask)
    
    print(f'检测到超出±{threshold_cm} cm阈值的异常点数量: {num_outliers} ({num_outliers/original_count*100:.2f}%)')
    
    if num_outliers > 0:
        valid_mask = ~outlier_mask
        ssh_diff_clean = ssh_diff[valid_mask]
        ssh_satA_clean = ssh_satA[valid_mask]
        ssh_satB_clean = ssh_satB[valid_mask]
        
        ssh_diff = ssh_diff_clean
        ssh_satA = ssh_satA_clean
        ssh_satB = ssh_satB_clean
        point_count = len(ssh_diff)
        
        cleaned_mean = np.nanmean(ssh_diff)
        cleaned_std = np.nanstd(ssh_diff)
        
        print('异常值处理后:')
        print(f'  数据点数: {point_count}')
        print(f'  平均差值: {cleaned_mean:.6f} m ({cleaned_mean*100:.3f} cm)')
        print(f'  标准差: {cleaned_std:.6f} m ({cleaned_std*100:.3f} cm)')
    else:
        print(f'未检测到超出±{threshold_cm} cm阈值的异常点')
    
else:
    print('无有效数据进行异常值处理')

# 结果显示
print('\n============================================================')
print('交叉定标结果')
print('============================================================')
print(f'匹配数据点数量: {point_count}')
print(f'处理的文件数量: Sentinel-6({sentinel6_file_count}/{len(sentinel6_filenames)}), Jason-3({jason3_file_count}/{len(jason3_filenames)})')
print(f'处理的共同日期数量: {len(common_dates)}')

if point_count > 0:
    mean_diff = np.nanmean(ssh_diff)
    std_diff = np.nanstd(ssh_diff)
    rmse = np.sqrt(np.nanmean(ssh_diff**2))
    
    print('\n统计结果:')
    print(f'平均差值 (Sentinel-6 SLA - Jason-3 SLA): {mean_diff:.6f} m')
    print(f'标准差: {std_diff:.6f} m')
    print(f'RMSE: {rmse:.6f} m')
    
    print('\n转换为厘米:')
    print(f'平均差值: {mean_diff * 100:.3f} cm')
    print(f'标准差: {std_diff * 100:.3f} cm')
    print(f'RMSE: {rmse * 100:.3f} cm')
    
    max_plot_points = 100000
    if point_count > max_plot_points:
        plot_indices = np.random.choice(point_count, max_plot_points, replace=False)
    else:
        plot_indices = np.arange(point_count)
    
    ssh_satA_plot = ssh_satA[plot_indices] * 100
    ssh_satB_plot = ssh_satB[plot_indices] * 100
    ssh_diff_plot = ssh_diff[plot_indices] * 100
    
    min_val = min(np.nanmin(ssh_satA_plot), np.nanmin(ssh_satB_plot))
    max_val = max(np.nanmax(ssh_satA_plot), np.nanmax(ssh_satB_plot))
    
    valid_fit = ~np.isnan(ssh_satB_plot) & ~np.isnan(ssh_satA_plot)
    x_fit = ssh_satB_plot[valid_fit]
    y_fit = ssh_satA_plot[valid_fit]
    
    print('\n=== 普通最小二乘线性回归 (Ordinary Least Squares) ===')
    
    try:
        p = np.polyfit(x_fit, y_fit, 1)
        slope = p[0]
        intercept = p[1]
        
        y_fit_pred = np.polyval(p, x_fit)
        residuals = y_fit - y_fit_pred
        rmse_fit = np.sqrt(np.mean(residuals**2))
        
        y_mean = np.mean(y_fit)
        ss_tot = np.sum((y_fit - y_mean)**2)
        ss_res = np.sum(residuals**2)
        r_squared = 1 - (ss_res / ss_tot)
        
        print(f'截距: {intercept:.4f} cm')
        print(f'斜率: {slope:.4f}')
        print(f'R²: {r_squared:.4f}')
        print(f'RMSE: {rmse_fit:.4f} cm')
        
        x_range = np.linspace(np.min(x_fit), np.max(x_fit), 100)
        y_range = np.polyval(p, x_range)
        
    except Exception as e:
        print(f'线性回归失败: {str(e)}')
    
    plt.figure(figsize=(12, 5))
    
    plt.subplot(1, 2, 1)
    
    hist2d, x_edges, y_edges = np.histogram2d(ssh_satB_plot, ssh_satA_plot, bins=50)
    
    x_bin = np.digitize(ssh_satB_plot, x_edges) - 1
    y_bin = np.digitize(ssh_satA_plot, y_edges) - 1
    
    color_data = np.zeros(len(ssh_satB_plot))
    for i in range(len(ssh_satB_plot)):
        if 0 <= x_bin[i] < hist2d.shape[0] and 0 <= y_bin[i] < hist2d.shape[1]:
            color_data[i] = hist2d[x_bin[i], y_bin[i]]
    
    mask = color_data > 0
    
    scatter = plt.scatter(ssh_satB_plot[mask], ssh_satA_plot[mask], c=color_data[mask], 
                         s=10, alpha=0.6, cmap='viridis')
    
    plt.plot(x_range, y_range, 'r-', linewidth=3, color=(0.9, 0.1, 0.1))
    
    cbar = plt.colorbar(scatter)
    cbar.set_label('频数', fontsize=10)
    
    plt.xlabel('Jason-3 SSH (cm)')
    plt.ylabel('Sentinel-6 SSH (cm)')
    plt.title('Sentinel-6 vs Jason-3交叉定标')
    plt.grid(True)
    
    plt.xlim(min_val, max_val)
    plt.ylim(min_val, max_val)
    
    plt.text(0.05, 0.95, f'y = {slope:.4f}x + {intercept:.4f}', 
             transform=plt.gca().transAxes, fontsize=12, fontweight='bold',
             backgroundcolor='white')
    plt.text(0.05, 0.88, f'R$^2$ = {r_squared:.4f}', 
             transform=plt.gca().transAxes, fontsize=12, fontweight='bold',
             backgroundcolor='white')
    
    plt.subplot(1, 2, 2)
    
    hist_data = ssh_diff_plot
    max_abs_diff = max(np.abs(hist_data))
    bin_edges = np.linspace(-max_abs_diff, max_abs_diff, 51)
    
    plt.hist(hist_data, bins=bin_edges, color='blue', edgecolor='black', alpha=0.7)
    
    plt.xlabel('差值 (Sentinel-6 - Jason-3) (cm)')
    plt.ylabel('频数')
    plt.title('SSH差值分布 (cm)')
    plt.grid(True)
    
    plt.xlim(-max_abs_diff, max_abs_diff)
    
    plt.text(0.7, 0.9, f'平均差值: {mean_diff*100:.3f} cm', transform=plt.gca().transAxes, fontsize=10)
    plt.text(0.7, 0.85, f'标准差: {std_diff*100:.3f} cm', transform=plt.gca().transAxes, fontsize=10)
    plt.text(0.7, 0.8, f'RMSE: {rmse*100:.3f} cm', transform=plt.gca().transAxes, fontsize=10)
    
    plt.tight_layout()
    plt.show()
    
else:
    print('未找到匹配的数据点')

print('\n============================================================')
print('处理完成')
print('============================================================')