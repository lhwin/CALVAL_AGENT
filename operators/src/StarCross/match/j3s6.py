import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
from scipy import stats
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist
from sklearn.linear_model import Ridge
import os
import warnings
import h5py
from datetime import datetime, timedelta
import cartopy.crs as ccrs
import cartopy.feature as cfeature

warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 数据目录
data_dir_335 = r'E:\星星交叉定标\335'  # Jason-3
data_dir_088 = r'E:\星星交叉定标\088'  # Sentinel-6

# 目标区域
target_lon_min = -180
target_lon_max = 180
target_lat_min = -60
target_lat_max = 60

print('============================================================')
print('卫星数据交叉定标分析 - 修正Sentinel-6缩放因子(10000)')
print('============================================================')


def normalize_longitude_jason(lon):
    """将Jason-3经度统一到[-180, 180]范围"""
    lon = np.array(lon)
    lon[lon > 180] = lon[lon > 180] - 360
    return lon


def normalize_longitude_sentinel(lon):
    """将Sentinel-6经度统一到[-180, 180]范围"""
    lon = np.array(lon)
    lon[lon > 180] = lon[lon > 180] - 360
    return lon


def read_jason3_nc(filepath):
    """读取Jason-3 NC文件"""
    try:
        with h5py.File(filepath, 'r') as f:
            lon = f['data_01/longitude'][:].astype(float) / 1e6
            lat = f['data_01/latitude'][:].astype(float) / 1e6
            ssh_raw = f['data_01/ku/ssha'][:].astype(float)
            time = f['data_01/time'][:].astype(float)

            # Jason-3: 去除32767填充值
            fill_value_jason = 32767
            valid_mask = (ssh_raw != fill_value_jason) & (~np.isnan(ssh_raw))

            # Jason-3的SSH单位是mm，除以1000得到米
            ssh = ssh_raw[valid_mask] / 1000.0
            lon = normalize_longitude_jason(lon[valid_mask])
            lat = lat[valid_mask]
            time = time[valid_mask]

            # 过滤明显异常值（超过±5米）
            valid_ssh_mask = np.abs(ssh) < 5
            ssh = ssh[valid_ssh_mask]
            lon = lon[valid_ssh_mask]
            lat = lat[valid_ssh_mask]
            time = time[valid_ssh_mask]

            return {
                'lon': lon,
                'lat': lat,
                'ssh': ssh,
                'time': time
            }
    except Exception as e:
        return None


def read_sentinel6_nc(filepath):
    """读取Sentinel-6 NC文件 - 修正缩放因子为10000"""
    try:
        with h5py.File(filepath, 'r') as f:
            lon = f['data_01/longitude'][:].astype(float) / 1e6
            lat = f['data_01/latitude'][:].astype(float) / 1e6
            ssh_raw = f['data_01/ku/ssha'][:].astype(float)
            time = f['data_01/time'][:].astype(float)

            # Sentinel-6: 去除2147483647填充值
            fill_value = 2147483647
            valid_mask = (ssh_raw != fill_value) & (~np.isnan(ssh_raw))

            # Sentinel-6的SSH单位应该是0.1mm，除以10000得到米
            ssh = ssh_raw[valid_mask] / 10000.0  # 从1000改为10000
            lon = normalize_longitude_sentinel(lon[valid_mask])
            lat = lat[valid_mask]
            time = time[valid_mask]

            # 过滤明显异常值（超过±5米）
            valid_ssh_mask = np.abs(ssh) < 5
            ssh = ssh[valid_ssh_mask]
            lon = lon[valid_ssh_mask]
            lat = lat[valid_ssh_mask]
            time = time[valid_ssh_mask]

            return {
                'lon': lon,
                'lat': lat,
                'ssh': ssh,
                'time': time
            }
    except Exception as e:
        return None


def seconds_to_date(time_seconds):
    """将秒数转换为日期整数 (YYYYMMDD)"""
    ref_date = datetime(2000, 1, 1)
    date = ref_date + timedelta(seconds=float(time_seconds))
    return int(date.strftime('%Y%m%d'))


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


def enhanced_spatial_matching(lon_A, lat_A, ssh_A, lon_B, lat_B, ssh_B,
                              max_distance_km=15, method='hybrid'):
    """
    增强的空间匹配方法
    """

    # 构建KDTree
    points_B = np.column_stack((lon_B, lat_B))
    tree_B = cKDTree(points_B)

    ssh_B_interp = np.zeros(len(lon_A)) * np.nan
    match_distances = []
    match_indices = []

    for i in range(len(lon_A)):
        if np.isnan(ssh_A[i]):
            continue

        # 找到半径内的所有点
        indices = tree_B.query_ball_point([lon_A[i], lat_A[i]],
                                          r=max_distance_km / 111.32)

        if len(indices) < 3:
            continue

        # 获取这些点的经纬度和SSH
        lon_B_local = lon_B[indices]
        lat_B_local = lat_B[indices]
        ssh_B_local = ssh_B[indices]

        # 计算精确的大圆距离
        distances = np.array([haversine_distance(lon_A[i], lat_A[i],
                                                 lon_B_local[j], lat_B_local[j])
                              for j in range(len(lon_B_local))])

        # 筛选在阈值内的点
        valid_mask = distances <= max_distance_km
        valid_distances = distances[valid_mask]
        valid_ssh = ssh_B_local[valid_mask]

        if len(valid_ssh) < 3:
            continue

        if method == 'hybrid':
            # 混合方法：结合IDW和高斯加权
            # 1. 反距离权重 (power=2)
            idw_weights = 1.0 / (valid_distances ** 2 + 1e-10)
            idw_weights = idw_weights / np.sum(idw_weights)
            idw_value = np.average(valid_ssh, weights=idw_weights)

            # 2. 高斯加权 (sigma = max_distance/3)
            sigma = max_distance_km / 3
            gaussian_weights = np.exp(-(valid_distances ** 2) / (2 * sigma ** 2))
            gaussian_weights = gaussian_weights / np.sum(gaussian_weights)
            gaussian_value = np.average(valid_ssh, weights=gaussian_weights)

            # 3. 取平均
            ssh_B_interp[i] = (idw_value + gaussian_value) / 2

        elif method == 'idw':
            weights = 1.0 / (valid_distances ** 2 + 1e-10)
            weights = weights / np.sum(weights)
            ssh_B_interp[i] = np.average(valid_ssh, weights=weights)

        elif method == 'gaussian':
            sigma = max_distance_km / 3
            weights = np.exp(-(valid_distances ** 2) / (2 * sigma ** 2))
            weights = weights / np.sum(weights)
            ssh_B_interp[i] = np.average(valid_ssh, weights=weights)

        match_distances.append(np.mean(valid_distances))
        match_indices.append(i)

    return ssh_B_interp, np.array(match_distances), np.array(match_indices)


# 获取所有NC文件
print("\n获取文件列表...")
jason3_files = [f for f in os.listdir(data_dir_335) if f.endswith('.nc')]
sentinel6_files = [f for f in os.listdir(data_dir_088) if f.endswith('.nc')]

print(f"Jason-3文件数量: {len(jason3_files)}")
print(f"Sentinel-6文件数量: {len(sentinel6_files)}")

# 读取所有Jason-3数据
print('\n============================================================')
print('读取Jason-3数据')
print('============================================================')

all_jason3_data = []

for i, filename in enumerate(jason3_files):
    print(f"\r处理文件 {i + 1}/{len(jason3_files)}: {filename[:30]}...", end="")

    data = read_jason3_nc(os.path.join(data_dir_335, filename))
    if data is None or len(data['ssh']) == 0:
        continue

    mask = (data['lon'] >= target_lon_min) & (data['lon'] <= target_lon_max) & \
           (data['lat'] >= target_lat_min) & (data['lat'] <= target_lat_max)

    if np.sum(mask) > 0:
        dates = [seconds_to_date(t) for t in data['time'][mask]]

        file_data = {
            'lon': data['lon'][mask],
            'lat': data['lat'][mask],
            'ssh': data['ssh'][mask],
            'dates': dates
        }
        all_jason3_data.append(file_data)

print(f"\n成功读取 {len(all_jason3_data)} 个Jason-3文件")

# 读取所有Sentinel-6数据
print('\n============================================================')
print('读取Sentinel-6数据 (修正缩放因子: 除以10000)')
print('============================================================')

all_sentinel6_data = []

for i, filename in enumerate(sentinel6_files):
    print(f"\r处理文件 {i + 1}/{len(sentinel6_files)}: {filename[:30]}...", end="")

    data = read_sentinel6_nc(os.path.join(data_dir_088, filename))
    if data is None or len(data['ssh']) == 0:
        continue

    mask = (data['lon'] >= target_lon_min) & (data['lon'] <= target_lon_max) & \
           (data['lat'] >= target_lat_min) & (data['lat'] <= target_lat_max)

    if np.sum(mask) > 0:
        dates = [seconds_to_date(t) for t in data['time'][mask]]

        file_data = {
            'lon': data['lon'][mask],
            'lat': data['lat'][mask],
            'ssh': data['ssh'][mask],
            'dates': dates
        }
        all_sentinel6_data.append(file_data)

print(f"\n成功读取 {len(all_sentinel6_data)} 个Sentinel-6文件")

# 合并所有数据
print('\n============================================================')
print('合并数据')
print('============================================================')


def combine_data(data_list):
    if not data_list:
        return None

    combined = {
        'lon': np.concatenate([d['lon'] for d in data_list]),
        'lat': np.concatenate([d['lat'] for d in data_list]),
        'ssh': np.concatenate([d['ssh'] for d in data_list]),
        'dates': np.concatenate([d['dates'] for d in data_list])
    }
    return combined


jason3_combined = combine_data(all_jason3_data)
sentinel6_combined = combine_data(all_sentinel6_data)

if jason3_combined is None or sentinel6_combined is None:
    print("错误: 没有成功读取任何数据！")
    exit()

if jason3_combined:
    print(f"Jason-3总点数: {len(jason3_combined['ssh'])}")
    print(f"SSH范围: [{np.nanmin(jason3_combined['ssh']):.3f}, {np.nanmax(jason3_combined['ssh']):.3f}] m")
    print(f"经度范围: [{np.nanmin(jason3_combined['lon']):.2f}, {np.nanmax(jason3_combined['lon']):.2f}]")
    print(f"纬度范围: [{np.nanmin(jason3_combined['lat']):.2f}, {np.nanmax(jason3_combined['lat']):.2f}]")
    print(f"日期范围: {int(np.min(jason3_combined['dates']))} - {int(np.max(jason3_combined['dates']))}")

if sentinel6_combined:
    print(f"Sentinel-6总点数: {len(sentinel6_combined['ssh'])}")
    print(f"SSH范围: [{np.nanmin(sentinel6_combined['ssh']):.3f}, {np.nanmax(sentinel6_combined['ssh']):.3f}] m")
    print(f"经度范围: [{np.nanmin(sentinel6_combined['lon']):.2f}, {np.nanmax(sentinel6_combined['lon']):.2f}]")
    print(f"纬度范围: [{np.nanmin(sentinel6_combined['lat']):.2f}, {np.nanmax(sentinel6_combined['lat']):.2f}]")
    print(f"日期范围: {int(np.min(sentinel6_combined['dates']))} - {int(np.max(sentinel6_combined['dates']))}")

# 按日期匹配
print('\n============================================================')
print('日期匹配')
print('============================================================')

common_dates = np.intersect1d(np.unique(jason3_combined['dates']),
                              np.unique(sentinel6_combined['dates']))
print(f"共同日期数量: {len(common_dates)}")
print(f"共同日期前10个: {common_dates[:10]}")

if len(common_dates) == 0:
    print("没有共同日期！")
    exit()

# 按日期筛选数据
jason3_by_date = {}
sentinel6_by_date = {}

for date in common_dates:
    jason_mask = jason3_combined['dates'] == date
    sentinel_mask = sentinel6_combined['dates'] == date

    if np.sum(jason_mask) > 10 and np.sum(sentinel_mask) > 10:
        jason3_by_date[date] = {
            'lon': jason3_combined['lon'][jason_mask],
            'lat': jason3_combined['lat'][jason_mask],
            'ssh': jason3_combined['ssh'][jason_mask]
        }

        sentinel6_by_date[date] = {
            'lon': sentinel6_combined['lon'][sentinel_mask],
            'lat': sentinel6_combined['lat'][sentinel_mask],
            'ssh': sentinel6_combined['ssh'][sentinel_mask]
        }

print(f"有数据的共同日期数量: {len(jason3_by_date)}")

# 空间匹配
print('\n============================================================')
print('空间匹配')
print('============================================================')

max_distance_km = 15
matching_method = 'hybrid'

ssh_diff = []
ssh_satA = []  # Sentinel-6
ssh_satB = []  # Jason-3
match_lons = []
match_lats = []
match_diffs = []
match_distances = []

for date_idx, date in enumerate(common_dates):
    print(f"\n处理日期 {date} ({date_idx + 1}/{len(common_dates)})")

    jason_data = jason3_by_date[date]
    sentinel_data = sentinel6_by_date[date]

    lon_B = jason_data['lon']
    lat_B = jason_data['lat']
    ssh_B = jason_data['ssh']

    lon_A = sentinel_data['lon']
    lat_A = sentinel_data['lat']
    ssh_A = sentinel_data['ssh']

    print(f"  Jason-3点数: {len(lon_B)}")
    print(f"  Sentinel-6点数: {len(lon_A)}")

    if len(lon_B) < 10 or len(lon_A) < 10:
        continue

    # 使用增强空间匹配方法
    ssh_B_interp, distances, valid_indices = enhanced_spatial_matching(
        lon_A, lat_A, ssh_A, lon_B, lat_B, ssh_B,
        max_distance_km=max_distance_km, method=matching_method
    )

    date_matches = 0

    for idx in range(len(valid_indices)):
        i = valid_indices[idx]
        if not np.isnan(ssh_B_interp[i]):
            ssh_diff_val = ssh_A[i] - ssh_B_interp[i]

            ssh_diff.append(ssh_diff_val)
            ssh_satA.append(ssh_A[i])
            ssh_satB.append(ssh_B_interp[i])
            match_lons.append(lon_A[i])
            match_lats.append(lat_A[i])
            match_diffs.append(ssh_diff_val)
            match_distances.append(distances[idx])
            date_matches += 1

    if date_matches > 0:
        avg_dist = np.mean(match_distances[-date_matches:])
        print(f"  匹配点数: {date_matches} (平均距离: {avg_dist:.2f}km)")

# 转换为numpy数组
if len(ssh_diff) > 0:
    ssh_diff = np.array(ssh_diff)
    ssh_satA = np.array(ssh_satA)
    ssh_satB = np.array(ssh_satB)
    match_lons = np.array(match_lons)
    match_lats = np.array(match_lats)
    match_diffs = np.array(match_diffs)
    match_distances = np.array(match_distances)

print(f"\n总匹配点数: {len(ssh_diff)}")
if len(ssh_diff) > 0:
    print(f"平均匹配距离: {np.mean(match_distances):.2f} km")
    print(f"距离标准差: {np.std(match_distances):.2f} km")
    print(f"最小距离: {np.min(match_distances):.2f} km")
    print(f"最大距离: {np.max(match_distances):.2f} km")

# 检查经度范围
if len(match_lons) > 0:
    print(f"\n匹配点经度范围: [{np.min(match_lons):.1f}, {np.max(match_lons):.1f}]")
    print(f"匹配点纬度范围: [{np.min(match_lats):.1f}, {np.max(match_lats):.1f}]")
    neg_lon_count = np.sum(match_lons < 0)
    print(f"负经度点数: {neg_lon_count} ({neg_lon_count / len(match_lons) * 100:.1f}%)")

# 结果显示
print('\n============================================================')
print('交叉定标结果')
print('============================================================')
print(f'匹配数据点数量: {len(ssh_diff)}')

if len(ssh_diff) > 10:
    mean_diff = np.nanmean(ssh_diff)
    std_diff = np.nanstd(ssh_diff)
    rmse = np.sqrt(np.nanmean(ssh_diff ** 2))

    print('\n统计结果:')
    print(f'平均差值 (Sentinel-6 - Jason-3): {mean_diff:.4f} m')
    print(f'标准差: {std_diff:.4f} m')
    print(f'RMSE: {rmse:.4f} m')

    print('\n转换为厘米:')
    print(f'平均差值: {mean_diff * 100:.2f} cm')
    print(f'标准差: {std_diff * 100:.2f} cm')
    print(f'RMSE: {rmse * 100:.2f} cm')

    # 线性回归
    slope, intercept, r_value, p_value, std_err = stats.linregress(ssh_satB, ssh_satA)
    print(f'\n线性回归:')
    print(f'  y = {slope:.4f}x + {intercept:.4f}')
    print(f'  R² = {r_value ** 2:.4f}')

    # 创建三个子图
    fig = plt.figure(figsize=(18, 5))

    # 1. 散点图
    ax1 = plt.subplot(1, 3, 1)

    # 使用hexbin
    hb = ax1.hexbin(ssh_satB * 100, ssh_satA * 100, gridsize=50, cmap='YlOrRd', mincnt=1)
    plt.colorbar(hb, ax=ax1, label='点数')

    # 拟合线
    x_range = np.array([np.min(ssh_satB), np.max(ssh_satB)]) * 100
    ax1.plot(x_range, (slope * x_range / 100 + intercept) * 100, 'b-', linewidth=2, label='拟合线')

    # 1:1线
    ax1.plot(x_range, x_range, 'k--', linewidth=1, alpha=0.5, label='1:1线')

    ax1.set_xlabel('Jason-3 SSH (cm)')
    ax1.set_ylabel('Sentinel-6 SSH (cm)')
    ax1.set_title(f'Sentinel-6 vs Jason-3 交叉定标')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax1.text(0.05, 0.95, f'y = {slope:.4f}x + {intercept * 100:.2f} cm',
             transform=ax1.transAxes, fontsize=9,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax1.text(0.05, 0.88, f'R² = {r_value ** 2:.4f}',
             transform=ax1.transAxes, fontsize=9,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax1.text(0.05, 0.81, f'n = {len(ssh_diff)}',
             transform=ax1.transAxes, fontsize=9,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    # 2. 差值直方图
    ax2 = plt.subplot(1, 3, 2)
    n, bins, patches = ax2.hist(ssh_diff * 100, bins=30, color='steelblue', edgecolor='black', alpha=0.7)
    ax2.axvline(x=mean_diff * 100, color='red', linestyle='--', linewidth=2, label=f'均值: {mean_diff * 100:.2f} cm')
    ax2.axvline(x=0, color='black', linestyle='-', linewidth=1, alpha=0.5)

    ax2.set_xlabel('差值 (Sentinel-6 - Jason-3) (cm)')
    ax2.set_ylabel('频数')
    ax2.set_title('SSH差值分布')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    ax2.text(0.7, 0.9, f'平均: {mean_diff * 100:.2f} cm', transform=ax2.transAxes, fontsize=9)
    ax2.text(0.7, 0.85, f'标准差: {std_diff * 100:.2f} cm', transform=ax2.transAxes, fontsize=9)
    ax2.text(0.7, 0.8, f'RMSE: {rmse * 100:.2f} cm', transform=ax2.transAxes, fontsize=9)

    # 3. 差值空间分布图
    ax3 = plt.subplot(1, 3, 3, projection=ccrs.PlateCarree())

    # 添加地图要素
    ax3.add_feature(cfeature.LAND, facecolor='lightgray')
    ax3.add_feature(cfeature.OCEAN, facecolor='lightblue', alpha=0.3)
    ax3.add_feature(cfeature.COASTLINE, linewidth=0.5)

    # 绘制网格线
    gl = ax3.gridlines(draw_labels=True, linewidth=0.5, color='gray', alpha=0.3, crs=ccrs.PlateCarree())
    gl.top_labels = False
    gl.right_labels = False
    gl.xlabel_style = {'size': 8}
    gl.ylabel_style = {'size': 8}

    # 绘制差值散点
    sc = ax3.scatter(match_lons, match_lats, c=match_diffs * 100,
                     cmap='RdBu_r', s=10, alpha=0.7,
                     vmin=-15, vmax=15, transform=ccrs.PlateCarree(),
                     edgecolors='none')

    plt.colorbar(sc, ax=ax3, label='SSH差值 (cm)', extend='both', shrink=0.8)

    ax3.set_title(f'SSH差值空间分布\n(平均距离: {np.mean(match_distances):.2f}km)')

    # 设置地图范围
    ax3.set_global()
    ax3.set_extent([-180, 180, -60, 60], crs=ccrs.PlateCarree())

    plt.tight_layout()
    plt.show()

    # 打印详细统计
    print('\n详细统计:')
    print(f'  最小值: {np.min(ssh_diff) * 100:.2f} cm')
    print(f'  最大值: {np.max(ssh_diff) * 100:.2f} cm')
    print(f'  中位数: {np.median(ssh_diff) * 100:.2f} cm')
    print(f'  25%分位数: {np.percentile(ssh_diff, 25) * 100:.2f} cm')
    print(f'  75%分位数: {np.percentile(ssh_diff, 75) * 100:.2f} cm')

else:
    print('匹配点数太少，无法进行有效分析')

print('\n============================================================')
print('处理完成')
print('============================================================')