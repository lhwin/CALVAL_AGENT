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


def func_cross_cal_pro(ipf_config):
    # if getattr(sys, 'frozen', False):
    # # PyInstaller 打包模式：资源解压到 sys._MEIPASS 临时目录
    #     current_dir = sys._MEIPASS
    # else:
    #     # 源码运行模式：使用脚本所在目录定位资源
    current_dir = os.getcwd()
    current_dir = os.path.abspath(current_dir)
   
    fontTTF = os.path.join(current_dir, "config", "SimHei.ttf")
    font_prop = FontProperties(fname=fontTTF)
    fm.fontManager.addfont(fontTTF) 
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams.update({'font.size': 14})

    # stpe1 配置文件加载及解析
    # 在输出目录下创建文件同名的文件夹，以存放产品
    new_dir_path = os.path.join(ipf_config.output, "CAL_" + ipf_config.outputFileType + "_" +
                                ipf_config.Start_date + "_" + ipf_config.End_date + "_V" +
                                ipf_config.Data_version)
    os.makedirs(new_dir_path, exist_ok=True)
    outputPath = new_dir_path
    # 将生产的nc等文件放到outputPath目录下。
    # +-------------此处添加核心处理代码-----------------------#
    Logger.info("Start data processing")

    Logger.info("Start data reading")
    # 读取匹配结果文件
    Logger.info("读取匹配结果文件")



    # ==================== 多日期文件读取、合并、去重 ====================

    start_date = datetime.strptime(ipf_config.Start_date, "%Y%m%d")
    end_date = datetime.strptime(ipf_config.End_date, "%Y%m%d")

    if end_date < start_date:
        raise ValueError("End_date 不能早于 Start_date")

    # 1. 获取输入目录
    input_dir = ipf_config.input

    if not os.path.isabs(input_dir):
        input_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            input_dir
        )

    input_dir = os.path.abspath(input_dir)

    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"CAL 输入目录不存在: {input_dir}")

    # 2. 搜索所有与计算日期有交集的 NPZ
    prefix = (
        f"match_result_{ipf_config.Sat_ID}_vs_"
        f"{ipf_config.Match_Data_Type}_"
    )

    name_re = re.compile(
        rf"^{re.escape(prefix)}(\d{{8}})_(\d{{8}})\.npz$",
        re.IGNORECASE
    )

    files_to_read = []

    for root, dirs, files in os.walk(input_dir):
        for name in files:
            m = name_re.fullmatch(name)

            if m is None:
                continue

            file_start, file_end = m.groups()

            # 文件日期范围与 CAL 日期范围存在交集
            if (file_start <= ipf_config.End_date
                    and file_end >= ipf_config.Start_date):
                files_to_read.append(os.path.join(root, name))

    files_to_read.sort()

    if not files_to_read:
        raise FileNotFoundError(
            f"未找到日期范围内的匹配 NPZ: {input_dir}"
        )

    Logger.info(f"找到 {len(files_to_read)} 个匹配文件")

    # 3. 将配置日期转换为 MATCH 使用的时间秒数
    epoch = datetime(2000, 1, 1)

    t_start = (start_date - epoch).total_seconds()
    t_end = (
        end_date + timedelta(days=1) - epoch
    ).total_seconds()

    fields = (
        'ssh_diff', 'ssh_primary', 'ssh_aux',
        'lon', 'lat', 'time_primary', 'time_aux',
        'distance_to_coast', 'depth', 'wind_speed',
        'distance'
    )

    required = (
        'ssh_diff', 'ssh_primary', 'ssh_aux',
        'lon', 'lat', 'time_primary', 'time_aux'
    )

    collected = {key: [] for key in fields}

    # 4. 逐文件读取，保留 CAL 日期范围内的观测点
    for path in files_to_read:
        with np.load(path, allow_pickle=True) as f:

            missing = [k for k in required if k not in f.files]

            if missing:
                raise ValueError(
                    f"{path} 缺少必要字段: {missing}"
                )

            n = len(f['ssh_diff'])

            tp = np.asarray(f['time_primary'], dtype=float)

            if tp.ndim != 1 or len(tp) != n:
                raise ValueError(
                    f"{path} 的 time_primary 长度不正确"
                )

            use = (
                np.isfinite(tp)
                & (tp >= t_start)
                & (tp < t_end)
            )

            count = int(use.sum())

            Logger.info(
                f"读取 {os.path.basename(path)}: "
                f"原始 {n} 点，日期范围内 {count} 点"
            )

            if count == 0:
                continue

            for key in fields:

                if key in f.files and np.asarray(f[key]).size > 0:
                    arr = np.asarray(f[key], dtype=float)

                    if arr.ndim != 1 or len(arr) != n:
                        raise ValueError(
                            f"{path} 的 {key} 长度不一致"
                        )

                elif key in required:
                    raise ValueError(
                        f"{path} 缺少必要字段: {key}"
                    )

                else:
                    arr = np.full(n, np.nan)

                collected[key].append(arr[use])

    if not collected['ssh_diff']:
        raise ValueError(
            "找到匹配文件，但所选日期范围内没有匹配观测点"
        )

    # 5. 合并所有匹配点
    data = {
        key: np.concatenate(value)
        for key, value in collected.items()
    }

    # 6. 检查用于去重的关键字段
    if not np.all(
        np.isfinite(data['time_primary'])
        & np.isfinite(data['lon'])
        & np.isfinite(data['lat'])
    ):
        raise ValueError(
            "存在无效的主卫星时间或经纬度，无法可靠去重"
        )

    # 7. 按主卫星时间与经纬度识别重复观测
    # 时间精确到毫秒，经纬度保留7位小数
    tk = np.round(data['time_primary'], 3)
    xk = np.round(data['lon'], 7)
    yk = np.round(data['lat'], 7)

    # 重复时优先选辅助邻点平均空间距离较小的记录
    distances = np.nan_to_num(
        data['distance'],
        nan=np.inf,
        posinf=np.inf,
        neginf=np.inf
    )

    # 空间距离相同时，优先选时间差较小的记录
    time_gaps = np.nan_to_num(
        np.abs(data['time_primary'] - data['time_aux']),
        nan=np.inf
    )

    # 先按观测点分组，再按空间距离、时间差排序
    order = np.lexsort((
        time_gaps,
        distances,
        yk,
        xk,
        tk
    ))

    # 同一主卫星观测点只保留排序后的第一条
    first = np.r_[
        True,
        (tk[order][1:] != tk[order][:-1])
        | (xk[order][1:] != xk[order][:-1])
        | (yk[order][1:] != yk[order][:-1])
    ]

    keep = np.sort(order[first])

    removed = len(tk) - len(keep)

    # 所有变量必须使用相同的索引去重
    data = {
        key: value[keep]
        for key, value in data.items()
    }

    Logger.info(
        f"合并前 {len(tk)} 点，"
        f"重复剔除 {removed} 点，"
        f"最终保留 {len(keep)} 点"
    )

    # 8. 检查哪些日期没有匹配点，但不终止程序
    current_date = start_date

    while current_date <= end_date:
        lo = (current_date - epoch).total_seconds()
        hi = lo + 86400

        nday = int(
            (
                (data['time_primary'] >= lo)
                & (data['time_primary'] < hi)
            ).sum()
        )

        if nday == 0:
            Logger.warn(
                f"{current_date:%Y%m%d} 没有可用匹配点，"
                "继续计算其他日期"
            )

        current_date += timedelta(days=1)

    # 9. 不累加旧 match_stats
    # 后续 CAL 会根据去重后的属性重新计算筛选统计

    ssh_diff = data['ssh_diff']
    ssh_primary = data['ssh_primary']
    ssh_aux = data['ssh_aux']

    lon = data['lon']
    lat = data['lat']

    distance_to_coast = data['distance_to_coast']
    depth = data['depth']
    wind_speed = data['wind_speed']



    #读取匹配数据集中的时间，根据两个时间间隔小于match_time的点进行筛选统计
    time_primary = data.get('time_primary', np.array([]))
    time_aux= data.get('time_aux', np.array([]))
    match_time = float(ipf_config.Match_time)
    mask = np.abs(time_primary - time_aux) < match_time * 3600  # 转换为秒
    # ssh_diff = ssh_diff[mask]
    # ssh_primary = ssh_primary[mask]
    # ssh_aux = ssh_aux[mask]
    # lon = lon[mask]
    # lat = lat[mask]
    # distance_to_coast = distance_to_coast[mask]
    # depth = depth[mask]
    # wind_speed = wind_speed[mask]
    # 读取匹配模块中计算的筛选统计信息
    # 初始化空字典，按原data键名筛选数据
    # filtered_data = {}
    # for key in data.keys():
    #     arr = data[key]
    #     # 仅对一维/二维数组应用掩码，空数组也兼容
    #     if arr.ndim >= 1:
    #         filtered_data[key] = arr[mask]
    #     else:
    #         filtered_data[key] = arr

    match_stats = data.get('match_stats', None)
 
    if match_stats is not None:
        match_stats = match_stats.item()  # 将 numpy array 转换为 dict
        Logger.info(f"读取到匹配点筛选统计信息")
        Logger.info(f"  总匹配点数: {match_stats.get('total_match', 0)}")
        Logger.info(f"  经纬度筛选通过: {match_stats.get('pass_area', 0)}")
        Logger.info(f"  离岸距离筛选通过: {match_stats.get('pass_coast', 0)}")
        Logger.info(f"  水深筛选通过: {match_stats.get('pass_depth', 0)}")
        Logger.info(f"  风速筛选通过: {match_stats.get('pass_wind', 0)}")
    else:
        pass

    Logger.info(f"读取到 {len(ssh_diff)} 个匹配点")

    Logger.info("Start data calabrating")
    Logger.info("开始定标计算...")

    # ==================== 计算百分比统计（基于匹配点） ====================
    total_match_points = len(ssh_diff)

    if match_stats is not None:
        # 使用匹配模块中统计的结果
        percent01 = f"{match_stats['pass_area'] / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"
        percent02 = f"{match_stats['pass_coast'] / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"
        percent03 = f"{match_stats['pass_depth'] / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"
        percent04 = f"{match_stats['pass_wind'] / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"

        Logger.info(f"匹配点筛选统计 (总匹配点数: {total_match_points}):")
        Logger.info(f"  经纬度筛选通过: {match_stats['pass_area']} ({percent01})")
        Logger.info(f"  离岸距离筛选通过: {match_stats['pass_coast']} ({percent02})")
        Logger.info(f"  水深筛选通过: {match_stats['pass_depth']} ({percent03})")
        Logger.info(f"  风速筛选通过: {match_stats['pass_wind']} ({percent04})")
    else:
        # 如果没有统计信息，从属性数据中计算
        Logger.info("根据合并去重后的匹配点重新计算筛选统计信息")

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

        # 经纬度筛选
        lon_mask = (lon >= min_lon) & (lon <= max_lon)
        lat_mask = (lat >= min_lat) & (lat <= max_lat)
        area_mask = lon_mask & lat_mask
        pass_area = np.sum(area_mask)
        percent01 = f"{pass_area / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"

        # 离岸距离筛选
        if len(distance_to_coast) > 0:
            coast_valid = ~np.isnan(distance_to_coast)
            coast_mask = distance_to_coast >= distance_threshold
        
            pass_coast = np.sum(coast_valid & coast_mask)
            percent02 = f"{pass_coast / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"
        else:
            percent02 = "N/A"

        # 水深筛选
        if len(depth) > 0:
            depth_valid = ~np.isnan(depth)
            depth_mask = depth < -depth_threshold
            pass_depth = np.sum(depth_valid & depth_mask)
            percent03 = f"{pass_depth / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"
        else:
            percent03 = "N/A"
    
        # 风速筛选
        if len(wind_speed) > 0:
            wind_valid = ~np.isnan(wind_speed)
            wind_mask = (wind_speed >= wind_min) & (wind_speed <= wind_max)
            pass_wind = np.sum(wind_valid & wind_mask)
            percent04 = f"{pass_wind / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"
        else:
            percent04 = "N/A"
        
        Logger.info(f"匹配点筛选统计 (总匹配点数: {total_match_points}):")
        Logger.info(f"  经纬度筛选通过: {pass_area} ({percent01})")
        Logger.info(f"  离岸距离筛选通过: {pass_coast} ({percent02})")
        Logger.info(f"  水深筛选通过: {pass_depth} ({percent03})")
        Logger.info(f"  风速筛选通过: {pass_wind} ({percent04})")


    # ==================== 时间筛选 ====================
    ssh_diff = ssh_diff[mask]
    ssh_primary = ssh_primary[mask]
    ssh_aux = ssh_aux[mask]
    lon = lon[mask]
    lat = lat[mask]
    distance_to_coast = distance_to_coast[mask]
    depth = depth[mask]
    wind_speed = wind_speed[mask]
    
    # 异常值处理 (阈值 ±15 cm)
    threshold_cm = 15
    threshold_m = threshold_cm / 100

    outlier_mask = np.abs(ssh_diff) > threshold_m
    num_outliers = np.sum(outlier_mask)

    if num_outliers > 0:
        Logger.info(
            f"检测到超出 ±{threshold_cm} cm 的异常点: {num_outliers} ({num_outliers / len(ssh_diff) * 100:.2f}%)")
        valid_mask = ~outlier_mask
        ssh_diff_clean = ssh_diff[valid_mask]
        ssh_primary_clean = ssh_primary[valid_mask]
        ssh_aux_clean = ssh_aux[valid_mask]
        if len(lon) > 0:
            lon_clean = lon[valid_mask]
            lat_clean = lat[valid_mask]
    else:
        ssh_diff_clean = ssh_diff
        ssh_primary_clean = ssh_primary
        ssh_aux_clean = ssh_aux
        if len(lon) > 0:
            lon_clean = lon
            lat_clean = lat

    # percent05: 异常值剔除保留率（相对于匹配点）
    percent05 = f"{(1 - num_outliers / total_match_points) * 100:.1f}%" if total_match_points > 0 else "N/A"

    # percent06: 最终有效数据占比（相对于匹配点）
    percent06 = f"{len(ssh_diff_clean) / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"

    Logger.info(f"异常值剔除保留率: {percent05}")
    Logger.info(f"最终有效数据占比: {percent06}")

    # ==================== 统计结果计算 ====================
    mean_diff = np.nanmean(ssh_diff_clean)
    std_diff = np.nanstd(ssh_diff_clean)
    rmse = np.sqrt(np.nanmean(ssh_diff_clean ** 2))
    median_diff = np.nanmedian(ssh_diff_clean)

    Logger.info("=" * 50)
    Logger.info(f"定标结果统计 ({ipf_config.Sat_ID} - {ipf_config.Match_Data_Type})")
    Logger.info("=" * 50)
    Logger.info(f"有效数据点数: {len(ssh_diff_clean)}")
    Logger.info(f"平均差值: {mean_diff:.6f} m ({mean_diff * 100:.3f} cm)")
    Logger.info(f"中位数差值: {median_diff:.6f} m ({median_diff * 100:.3f} cm)")
    Logger.info(f"标准差: {std_diff:.6f} m ({std_diff * 100:.3f} cm)")
    Logger.info(f"RMSE: {rmse:.6f} m ({rmse * 100:.3f} cm)")
    Logger.info("=" * 50)

    # 线性回归分析
    try:
        from scipy import stats as stats_lib
        slope, intercept, r_value, p_value, std_err = stats_lib.linregress(ssh_aux_clean, ssh_primary_clean)
        r_squared = r_value ** 2

        Logger.info("线性回归结果:")
        Logger.info(f"  截距: {intercept:.6f} m ({intercept * 100:.4f} cm)")
        Logger.info(f"  斜率: {slope:.4f}")
        Logger.info(f"  R²: {r_squared:.4f}")
    except Exception as e:
        Logger.warn(f"线性回归失败: {str(e)}")
        slope, intercept, r_squared = None, None, None

    # 保存计算结果
    cal_txt = os.path.join(outputPath,
                           f"calibration_result_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.txt")
    with open(cal_txt, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("卫星高度计交叉定标结果\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"主卫星: {ipf_config.Sat_ID}\n")
        f.write(f"辅助卫星: {ipf_config.Match_Data_Type}\n")
        f.write(f"时间范围: {ipf_config.Start_date} - {ipf_config.End_date}\n\n")
        f.write(f"有效数据点数: {len(ssh_diff_clean)}\n")
        f.write(f"异常值阈值: ±{threshold_cm} cm (移除 {num_outliers} 点)\n\n")
        f.write("统计结果:\n")
        f.write(f"  平均差值: {mean_diff * 100:.3f} cm\n")
        f.write(f"  中位数差值: {median_diff * 100:.3f} cm\n")
        f.write(f"  标准差: {std_diff * 100:.3f} cm\n")
        f.write(f"  RMSE: {rmse * 100:.3f} cm\n\n")
        if slope is not None:
            f.write("线性回归 (单位: m):\n")
            f.write(f"  y = {slope:.4f}x + {intercept:.4f}\n")
            f.write(f"  R² = {r_squared:.4f}\n")

    Logger.info(f"计算结果已保存至: {cal_txt}")

    # 保存为numpy格式
    cal_npz = os.path.join(outputPath,
                           f"calibration_data_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.npz")
    np.savez_compressed(cal_npz,
                        ssh_diff_clean=ssh_diff_clean,
                        ssh_primary_clean=ssh_primary_clean,
                        ssh_aux_clean=ssh_aux_clean,
                        lon_clean=lon_clean if len(lon) > 0 else np.array([]),
                        lat_clean=lat_clean if len(lat) > 0 else np.array([]))
    Logger.info(f"计算数据已保存至: {cal_npz}")
    
    # 生成图像
    Logger.info("生成可视化图像...")
    try:
        # 设置中文字体
        if os.path.exists(fontTTF):
            font_prop = FontProperties(fname=fontTTF)
            # plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
        else:
            plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
        plt.rcParams['axes.unicode_minus'] = False

        # 创建三个子图（散点图 + 直方图）
        fig1 = plt.figure(figsize=(12, 5))

        # 1. 散点图
        ax1 = plt.subplot(1, 2, 1)
        hb = ax1.hexbin(ssh_aux_clean * 100, ssh_primary_clean * 100, gridsize=50, cmap='YlOrRd', mincnt=1)
        cbar = plt.colorbar(hb, ax=ax1, label='点数')
        cbar.ax.set_ylabel('点数', fontproperties=font_prop if 'font_prop' in dir() else None)

        if slope is not None:
            x_range = np.array([np.min(ssh_aux_clean), np.max(ssh_aux_clean)]) * 100
            y_line = slope * x_range / 100 + intercept
            ax1.plot(x_range, y_line * 100, 'b-', linewidth=2, label='拟合线')

        x_range = np.array([np.min(ssh_aux_clean), np.max(ssh_aux_clean)]) * 100
        ax1.plot(x_range, x_range, 'k--', linewidth=1, alpha=0.5, label='1:1线')

        ax1.set_xlabel(f'{ipf_config.Match_Data_Type} SSH (cm)',
                       fontproperties=font_prop if 'font_prop' in dir() else None)
        ax1.set_ylabel(f'{ipf_config.Sat_ID} SSH (cm)', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax1.set_title(f'{ipf_config.Sat_ID} vs {ipf_config.Match_Data_Type} 交叉定标',
                      fontproperties=font_prop if 'font_prop' in dir() else None)
        ax1.grid(True, alpha=0.3)
        ax1.legend(prop=font_prop if 'font_prop' in dir() else None)

        # 添加统计信息文本框
        if slope is not None:
            textstr = f'y = {slope:.4f}x + {intercept * 100:.2f} cm\n'
            textstr += f'R² = {r_squared:.4f}\n'
            textstr += f'n = {len(ssh_diff_clean)}'
            ax1.text(0.05, 0.95, textstr, transform=ax1.transAxes, fontsize=9,
                     verticalalignment='top', fontproperties=font_prop if 'font_prop' in dir() else None,
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        # 2. 差值直方图
        ax2 = plt.subplot(1, 2, 2)
        diff_cm = ssh_diff_clean * 100
        n, bins, patches = ax2.hist(diff_cm, bins=30, color='steelblue', edgecolor='black', alpha=0.7)
        ax2.axvline(x=mean_diff * 100, color='red', linestyle='--', linewidth=2,
                    label=f'均值: {mean_diff * 100:.2f} cm')
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=1, alpha=0.5)

        ax2.set_xlabel('SSH差值 (cm)', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax2.set_ylabel('频数', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax2.set_title('SSH差值分布', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax2.grid(True, alpha=0.3)
        ax2.legend(prop=font_prop if 'font_prop' in dir() else None)

        # 添加统计信息文本框
        textstr2 = f'平均: {mean_diff * 100:.2f} cm\n'
        textstr2 += f'标准差: {std_diff * 100:.2f} cm\n'
        textstr2 += f'RMSE: {rmse * 100:.2f} cm'
        ax2.text(0.02, 0.95, textstr2, transform=ax2.transAxes, fontsize=9,
                 verticalalignment='top', fontproperties=font_prop if 'font_prop' in dir() else None,
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        plt.tight_layout()

        fig1_path = os.path.join(outputPath,
                                 f"calibration_plot_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.png")
        plt.savefig(fig1_path, dpi=300, bbox_inches='tight')
        plt.close(fig1)
        Logger.info(f"散点图和直方图已保存至: {fig1_path}")

        # 3. 空间分布图（单独一张图）
        try:
            # 指定本地 Natural Earth 数据目录，避免 cartopy 联网下载（打包环境可能无网络/证书问题）
            if getattr(sys, 'frozen', False):
                # 打包后：可执行程序上一级目录下的 config\cartopy_data
                _exe_dir = os.path.dirname(sys.executable)
                _cartopy_data = os.path.join(os.path.dirname(_exe_dir), 'config', 'cartopy_data')
            else:
                # 源码运行：脚本同级目录下的 cartopy_data
                _cartopy_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cartopy_data')
            _has_local_data = os.path.isdir(_cartopy_data)
            if _has_local_data:
                # 环境变量仅在 cartopy 首次导入时生效
                os.environ['CARTOPY_DATA_DIR'] = _cartopy_data

            import cartopy
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature

            # 直接改写运行时配置，避免 cartopy 已提前导入导致上面的环境变量失效，
            # 从而回退到 ~/.local/share/cartopy 并触发联网下载
            if _has_local_data:
                cartopy.config['pre_existing_data_dir'] = _cartopy_data
            
            fig2 = plt.figure(figsize=(12, 10))  # 稍微调高一点，为底部colorbar留空间
            ax3 = plt.subplot(1, 1, 1, projection=ccrs.PlateCarree())

            # 添加地图要素
            ax3.add_feature(cfeature.LAND, facecolor='lightgray', alpha=0.8)
            ax3.add_feature(cfeature.OCEAN, facecolor='lightblue', alpha=0.3)
            ax3.add_feature(cfeature.COASTLINE, linewidth=0.5)
            ax3.add_feature(cfeature.BORDERS, linewidth=0.3, alpha=0.5)

            # 绘制网格线
            gl = ax3.gridlines(draw_labels=True, linewidth=0.5, color='gray', alpha=0.3, crs=ccrs.PlateCarree())
            gl.top_labels = False
            gl.right_labels = False
            gl.xlabel_style = {'size': 10}
            gl.ylabel_style = {'size': 10}

            # 绘制差值散点
            if len(lon_clean) > 0 and len(lat_clean) > 0:
                sc = ax3.scatter(lon_clean, lat_clean, c=diff_cm,
                                 cmap='RdBu_r', s=10, alpha=0.6,
                                 vmin=-15, vmax=15, transform=ccrs.PlateCarree(),
                                 edgecolors='none')

                # 修改：colorbar放在底部
                cbar = plt.colorbar(sc, ax=ax3, label='SSH差值 (cm)',
                                    orientation='horizontal',  # 关键：水平方向
                                    extend='both', shrink=0.8, pad=0.08)  # pad控制与图的距离
                cbar.ax.set_xlabel('SSH差值 (cm)', fontproperties=font_prop if 'font_prop' in dir() else None,
                                   fontsize=10)

            # 设置地图范围
            ax3.set_global()
            ax3.set_extent([-180, 180, -60, 60], crs=ccrs.PlateCarree())

            ax3.set_title(f'SSH差值空间分布', fontsize=12, fontproperties=font_prop if 'font_prop' in dir() else None)

            plt.tight_layout()

            fig2_path = os.path.join(outputPath,
                                     f"spatial_distribution_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.png")
            plt.savefig(fig2_path, dpi=300, bbox_inches='tight')
            plt.close(fig2)
            Logger.info(f"空间分布图已保存至: {fig2_path}")

        except ImportError as e:
            Logger.warn(f"cartopy未安装，跳过空间分布图: {e}")
        except Exception as e:
            Logger.warn(f"生成空间分布图失败: {str(e)}")

    except Exception as e:
        Logger.warn(f"生成图像失败: {str(e)}")
        import traceback
        Logger.warn(traceback.format_exc())

    # ==================== 生成JSON格式的标签文件 ====================
    Logger.info("生成JSON标签文件...")

    import json

    # 获取图片路径（替换反斜杠为正斜杠，使JSON更规范）
    spatial_img = os.path.join(outputPath,
                               f"spatial_distribution_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.png").replace(
        '\\', '/')
    scatter_img = os.path.join(outputPath,
                               f"calibration_plot_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.png").replace(
        '\\', '/')

    # 构建JSON数据
    json_data = {
        "${satId}": "GL-SY",
        "${sensorId}": "ALT",
        "${sensorId_C}": "高度计",
        "${data_level}": "L2B_IGDR",
        "${method_name}": "CCS",
        "${method_name_C}": "星星交叉法",
        "${start_time}": ipf_config.Start_date,
        "${end_time}": ipf_config.End_date,
        "${parameter_C}": "海面高度",
        "${data_version}": ipf_config.Data_version,
        "${algo_version}": "V01",
        "${responsibler}": "丁超、闫鹏",
        "${programmer}": "王士帅",
        "${produce_time}": datetime.now().strftime("%Y年%m月%d日"),
        "${introduction}": "海面高度交叉定标法是指利用参考任务高度计观测的海面高度作为基准，对GL-SY星高度计观测的海面高度进行标定的方法，通过计算确定参考载荷与GL-SY载荷在全球的所有交叉点，根据数据匹配和质量控制准则，找出满足对比条件的交叉点，对比GL-SY星高度计与参考卫星高度计在交叉点处的海面高度，统计计算得出相对定标系数。",
        "${aux_data}": ipf_config.Match_Data_Type,
        "${level}": "L2",
        "${aft_num}": str(len(ssh_diff_clean)),
        "${aft_bias}": f"{mean_diff * 100:.2f}",
        "${aft_std}": f"{std_diff * 100:.2f}",
        "${coef}": f"{r_squared:.4f}" if r_squared is not None else "N/A",
        "${aux_data_des}": f"参考卫星高度计数据选用{ipf_config.Match_Data_Type}的IGDR数据。",
        "${percent01}": percent01,
        "${percent02}": percent02,
        "${percent03}": percent03,
        "${percent04}": percent04,
        "${percent05}": percent05,
        "${percent06}": percent06,
        "${image_dist}": spatial_img,
        "${image_scatter_hist}": scatter_img,
        "${image_trend}": scatter_img
    }

    # 保存JSON文件
    json_path = os.path.join(outputPath,
                             f"calibration_result_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    Logger.info(f"JSON标签文件已保存至: {json_path}")

    # ==================== 生成Word格式的报告文件 ====================
    Logger.info("生成Word报告文件...")

    try:
        from docx import Document
        from docx.shared import Inches, Cm, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        # 获取模板路径
        template_path = getattr(ipf_config, 'Template_docx', None)

        if not template_path:
            Logger.warn("未配置Template_docx参数，跳过Word报告生成")
        elif not os.path.exists(template_path):
            Logger.warn(f"Word模板文件不存在: {template_path}")
        else:
            # 加载模板文档
            doc = Document(template_path)

            # 替换段落中的占位符（保留格式）
            for paragraph in doc.paragraphs:
                # 跳过包含图片占位符的段落
                if "${image_dist}" in paragraph.text or "${image_scatter_hist}" in paragraph.text or "${image_trend}" in paragraph.text:
                    continue

                # 逐个 run 替换，保留格式
                for run in paragraph.runs:
                    for key, value in json_data.items():
                        if key in run.text:
                            run.text = run.text.replace(key, str(value))

            # 替换表格中的占位符（表格单元格需要特殊处理）
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                for key, value in json_data.items():
                                    if key in run.text:
                                        run.text = run.text.replace(key, str(value))

            # 处理图片插入（查找包含图片占位符的段落）
            # 1. 空间分布图
            for paragraph in doc.paragraphs:
                if "${image_dist}" in paragraph.text:
                    # 清空段落但保留格式
                    paragraph.clear()
                    # 添加图片
                    img_path = json_data["${image_dist}"]
                    if os.path.exists(img_path):
                        run = paragraph.add_run()
                        picture = run.add_picture(img_path, width=Inches(6.0))
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        Logger.info(f"已插入空间分布图: {img_path}")
                    else:
                        run = paragraph.add_run(f"[图片未生成: {img_path}]")
                        Logger.warn(f"空间分布图不存在: {img_path}")
                    break

            # 2. 散点图和直方图
            for paragraph in doc.paragraphs:
                if "${image_scatter_hist}" in paragraph.text:
                    paragraph.clear()
                    img_path = json_data["${image_scatter_hist}"]
                    if os.path.exists(img_path):
                        run = paragraph.add_run()
                        run.add_picture(img_path, width=Inches(6.0))
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        Logger.info(f"已插入散点直方图: {img_path}")
                    else:
                        run = paragraph.add_run(f"[图片未生成: {img_path}]")
                        Logger.warn(f"散点直方图不存在: {img_path}")
                    break

            # 3. 趋势图
            for paragraph in doc.paragraphs:
                if "${image_trend}" in paragraph.text:
                    paragraph.clear()
                    img_path = json_data["${image_trend}"]
                    if os.path.exists(img_path):
                        run = paragraph.add_run()
                        run.add_picture(img_path, width=Inches(6.0))
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        Logger.info(f"已插入趋势图: {img_path}")
                    else:
                        run = paragraph.add_run(f"[图片未生成: {img_path}]")
                        Logger.warn(f"趋势图不存在: {img_path}")
                    break

            # 保存生成的报告
            report_path = os.path.join(outputPath,
                                       f"calibration_report_{ipf_config.Sat_ID}_vs_{ipf_config.Match_Data_Type}_{ipf_config.Start_date}_{ipf_config.End_date}.docx")
            doc.save(report_path)
            Logger.info(f"Word报告已保存至: {report_path}")
        
    except ImportError as e:
        Logger.warn(f"python-docx未安装，跳过Word报告生成: {e}")
        Logger.warn("请安装: pip install python-docx")
    except Exception as e:
        Logger.warn(f"生成Word报告失败: {str(e)}")
        import traceback
        Logger.warn(traceback.format_exc())
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
    # write_product_xml(product_xml_path, outputPath, ipf_config.outputFileType)
    # 函数write_product_xml传参：
    Logger.progress(100)
    print("*-"*100)
    result = {
    "statistics": {
        "mean_diff_m": float(mean_diff),  # 显式转换为 float
        "mean_diff_cm": float(mean_diff * 100),
        "std_diff_m": float(std_diff),
        "rmse_m": float(rmse),
        "regression": {
            "slope": float(slope),
            "intercept": float(intercept),
            "r_squared": float(r_squared)
        },
        "num_valid_points": int(len(ssh_diff_clean)),  # 显式转换为 int
        "num_outliers": int(num_outliers)
    },
    "output_files": {
        "text_result": cal_txt,
        "data_file": cal_npz,
        "plots": [fig1_path, fig2_path],
        "metadata": json_path
    },
    "success": True
    }

    return result

