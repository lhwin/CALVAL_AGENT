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


def func_self_cross_cal_pro(ipf_config):
    # 非打包情况下使用
    current_dir = os.getcwd()
    # 打包时使用
    # current_dir = sys._MEIPASS
    # current_dir = os.path.abspath(current_dir)

    fontTTF = os.path.join(current_dir, "config", "SimHei.ttf")
    font_prop = FontProperties(fname=fontTTF)
    fm.fontManager.addfont(fontTTF) 
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams.update({'font.size': 14})

    # stpe1 配置文件加载及解析
    # 在输出目录下创建文件同名的文件夹，以存放产品
    new_dir_path = os.path.join(ipf_config.output, "CAL_GL_SSH_SELF_CROSS_CAL_RESULT_" +
                                ipf_config.Start_date + "_" + ipf_config.End_date + "_V" +
                                ipf_config.Data_version)
    os.makedirs(new_dir_path, exist_ok=True)
    outputPath = new_dir_path
    # 将生产的nc等文件放到outputPath目录下。
    # +-------------此处添加核心处理代码-----------------------#
    Logger.info("Start data processing")

    # ==================== 多日期自交叉匹配结果读取 ====================
    Logger.info("Start data reading")
    Logger.info("开始读取多日期自交叉匹配结果")

    import pandas as pd
    import json

    sat_id = ipf_config.Sat_ID
    start_dt = datetime.strptime(ipf_config.Start_date, "%Y%m%d")
    end_dt = datetime.strptime(ipf_config.End_date, "%Y%m%d")

    if end_dt < start_dt:
        raise ValueError("结束日期不能早于开始日期")

    # 读取 CAL 的 input 目录
    input_dir = ipf_config.input

    if not os.path.isabs(input_dir):
        input_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            input_dir
        )

    input_dir = os.path.abspath(input_dir)

    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    Logger.info(f"实际搜索目录: {input_dir}")


    # 支持单日文件和跨日期文件
    pattern = re.compile(
        rf"^{re.escape(sat_id)}_self_cross_matches_"
        rf"(\d{{8}})_(\d{{8}})\.(parquet|csv)$",
        re.IGNORECASE
    )

    sources = {}

    for root, dirs, files in os.walk(input_dir):
        for filename in files:
            m = pattern.fullmatch(filename)
            if not m:
                continue

            file_start, file_end, ext = m.groups()

            # 文件日期范围与 CAL 日期范围有交集
            if (file_start <= ipf_config.End_date
                    and file_end >= ipf_config.Start_date):

                key = (file_start, file_end)
                options = sources.setdefault(key, {})
                ext = ext.lower()

                if ext in options:
                    raise ValueError(
                        f"发现日期范围重复的 {ext} 文件: {key}"
                    )

                options[ext] = os.path.join(root, filename)

    Logger.info(f"找到 {len(sources)} 组匹配文件")

    frames = []
    daily_stats = []
    used_days = []
    missing_days = []
    covered_days = set()

    for (file_start, file_end), options in sorted(sources.items()):

        # 检查文件之间是否存在日期重叠，避免重复统计
        overlap_start = max(file_start, ipf_config.Start_date)
        overlap_end = min(file_end, ipf_config.End_date)

        d = datetime.strptime(overlap_start, "%Y%m%d")
        d_end = datetime.strptime(overlap_end, "%Y%m%d")
        this_days = set()

        while d <= d_end:
            day = d.strftime("%Y%m%d")
            this_days.add(day)
            d += timedelta(days=1)

        covered_days.update(this_days)

        # 优先读取 Parquet，失败时回退 CSV
        if "parquet" in options:
            match_file = options["parquet"]
            try:
                df_day = pd.read_parquet(match_file)
            except Exception as e:
                if "csv" not in options:
                    raise
                Logger.warn(f"Parquet读取失败，改用CSV: {e}")
                match_file = options["csv"]
                df_day = pd.read_csv(match_file)
        else:
            match_file = options["csv"]
            df_day = pd.read_csv(match_file)

        required = {"date", "time_asc", "lon", "lat",
                    "ssh_asc", "ssh_desc", "diff"}
        missing = required - set(df_day.columns)

        if missing:
            raise ValueError(
                f"文件缺少字段 {sorted(missing)}: {match_file}"
            )

        # 根据 CAL 设置的日期筛选文件内部记录
        dates = pd.to_numeric(df_day["date"], errors="coerce")

        if dates.isna().any():
            raise ValueError(
                f"date 列存在无法识别的日期: {match_file}"
            )

        date_mask = (
            (dates >= int(ipf_config.Start_date))
            & (dates <= int(ipf_config.End_date))
        )

        df_day = df_day.loc[date_mask].copy()

        Logger.info(
            f"读取: {os.path.basename(match_file)}, "
            f"有效匹配点: {len(df_day)}"
        )

        if df_day.empty:
            continue

        frames.append(df_day)

        used_days.extend(
            str(int(x)) for x in df_day["date"].unique()
        )

        # 读取 MATCH 保存的统计 JSON
        stats_file = os.path.join(
            os.path.dirname(match_file),
            f"{sat_id}_self_cross_match_stats_"
            f"{file_start}_{file_end}.json"
        )

        # 仅完整使用文件时，才能直接累加原统计量
        if (file_start >= ipf_config.Start_date
                and file_end <= ipf_config.End_date
                and os.path.isfile(stats_file)):
            with open(stats_file, "r", encoding="utf-8") as f:
                daily_stats.append(json.load(f))
        else:
            Logger.warn(
                f"无法直接使用统计JSON: {file_start}-{file_end}"
            )

    # 检查哪些日期没有匹配点
    current_date = start_dt
    used_days = sorted(set(used_days))

    while current_date <= end_dt:
        date_str = current_date.strftime("%Y%m%d")
        if date_str not in used_days:
            missing_days.append(date_str)
        current_date += timedelta(days=1)


    # ==================== 合并全部数据 ====================
    if not frames:
        raise FileNotFoundError(
            f"未找到 {sat_id} 在 "
            f"{ipf_config.Start_date}-{ipf_config.End_date} "
            f"之间的每日匹配文件。搜索目录: {input_dir}"
        )


    df_matches = pd.concat(frames, ignore_index=True)

    # 记录去重前数量
    before_count = len(df_matches)

    # 转换数据类型
    for col in ['date', 'time_asc', 'lon', 'lat',
                'ssh_asc', 'distance', 'std']:
        df_matches[col] = pd.to_numeric(
            df_matches[col], errors='coerce'
        )

    # 必要字段必须有效
    keys = ['date', 'time_asc', 'lon', 'lat', 'ssh_asc']
    if df_matches[keys].isna().any().any():
        raise ValueError("匹配结果存在无效的日期、位置或SSHA")

    # 与星星交叉CAL保持一致：时间 + 经纬度去重
    df_matches['_time'] = df_matches['time_asc'].round(3)
    df_matches['_lon'] = df_matches['lon'].round(7)
    df_matches['_lat'] = df_matches['lat'].round(7)

    # 确保用于去重的时间和位置有效
    if not np.isfinite(
            df_matches[['time_asc', 'lon', 'lat']].to_numpy(dtype=float)
    ).all():
        raise ValueError("存在无效的观测时间或经纬度，无法去重")

    # 同一原始观测点有多条匹配结果时，
    # 优先保留空间匹配距离较小、STD较小的结果
    df_matches = (
        df_matches
        .sort_values(
            ['distance', 'std'],
            ascending=[True, True],
            na_position='last',
            kind='stable'
        )
        .drop_duplicates(
            subset=['_time', '_lon', '_lat'],
            keep='first'
        )
        .drop(columns=['_time', '_lon', '_lat'])
        .reset_index(drop=True)
    )

    Logger.info(
        f"合并前: {before_count} 点，"
        f"重复剔除: {before_count - len(df_matches)} 点，"
        f"最终保留: {len(df_matches)} 点"
    )


    if df_matches.empty:
        raise ValueError("找到匹配文件，但合并后的数据为空")

    Logger.info("=" * 50)
    Logger.info(f"成功合并日期数量: {len(used_days)}")
    Logger.info(f"合并后的总匹配点数: {len(df_matches)}")


    # ==================== 去重后重新计算筛选统计 ====================

    min_lat, max_lat, min_lon, max_lon = [
        float(x) for x in
        ipf_config.Select_Area.strip('[]').split(',')
    ]

    wind_min, wind_max = 0.0, 40.0
    if ipf_config.wind_speed:
        wind_min, wind_max = [
            float(x) for x in
            ipf_config.wind_speed.strip('[]').split(',')
        ]

    area_mask = (
        df_matches['lon'].between(min_lon, max_lon)
        & df_matches['lat'].between(min_lat, max_lat)
    )

    coast_mask = (
        df_matches['distance_to_coast']
        >= ipf_config.distance_to_coast
    )

    depth_mask = (
        df_matches['depth']
        < -ipf_config.ocean_depth
    )

    wind_mask = (
        df_matches['wind_speed']
        .between(wind_min, wind_max)
    )

    match_stats = {
        'total_match': len(df_matches),
        'pass_area': int(area_mask.sum()),
        'pass_coast': int(coast_mask.sum()),
        'pass_depth': int(depth_mask.sum()),
        'pass_wind': int(wind_mask.sum()),
        'pass_all': int((
            area_mask & coast_mask & depth_mask & wind_mask
        ).sum())
    }

    Logger.info("已根据合并去重后的数据重新计算筛选统计信息")

    if missing_days:
        Logger.warn(
            f"缺失 {len(missing_days)} 个日期: "
            f"{', '.join(missing_days)}"
        )
        Logger.warn("本次结果仅代表实际读取到的日期")

    Logger.info("=" * 50)


    Logger.info("Start data calabrating")
    Logger.info("开始自交叉定标计算...")

    from scipy import stats as stats_lib

    # 获取卫星ID，用于显示名称
    sat_id = ipf_config.Sat_ID
    if sat_id.upper() == 'S6A':
        satellite_name = 'Sentinel-6'
        satellite_name_display = '哨兵6A'
    elif sat_id.upper() == 'JASON3' or sat_id.upper() == 'JA3':
        satellite_name = 'Jason-3'
        satellite_name_display = 'Jason-3'
    else:
        satellite_name = sat_id
        satellite_name_display = sat_id

    # ==================== 计算百分比统计（基于匹配点） ====================
    total_match_points = len(df_matches)

    if match_stats is not None:
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
        percent01 = percent02 = percent03 = percent04 = "N/A"
        Logger.warn("未找到筛选统计信息")

    # ==================== 应用筛选条件（离岸距离、水深、风速） ====================
    Logger.info("应用筛选条件...")

    # 获取筛选阈值
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

    # 创建筛选掩码
    mask = np.ones(len(df_matches), dtype=bool)

    # 经纬度筛选
    if 'lon' in df_matches.columns and 'lat' in df_matches.columns:
        lon_mask = (df_matches['lon'] >= min_lon) & (df_matches['lon'] <= max_lon)
        lat_mask = (df_matches['lat'] >= min_lat) & (df_matches['lat'] <= max_lat)
        mask = mask & lon_mask & lat_mask

    # 离岸距离筛选
    if 'distance_to_coast' in df_matches.columns:
        coast_valid = ~df_matches['distance_to_coast'].isna()
        coast_mask = df_matches['distance_to_coast'] >= distance_threshold
        mask = mask & coast_valid & coast_mask
        pass_coast_count = np.sum(coast_valid & coast_mask)
        Logger.info(f"  离岸距离筛选通过: {pass_coast_count} ({pass_coast_count / total_match_points * 100:.1f}%)")

    # 水深筛选
    if 'depth' in df_matches.columns:
        depth_valid = ~df_matches['depth'].isna()
        depth_mask = df_matches['depth'] < -depth_threshold
        mask = mask & depth_valid & depth_mask
        pass_depth_count = np.sum(depth_valid & depth_mask)
        Logger.info(f"  水深筛选通过: {pass_depth_count} ({pass_depth_count / total_match_points * 100:.1f}%)")

    # 风速筛选
    if 'wind_speed' in df_matches.columns:
        wind_valid = ~df_matches['wind_speed'].isna()
        wind_mask = (df_matches['wind_speed'] >= wind_min) & (df_matches['wind_speed'] <= wind_max)
        mask = mask & wind_valid & wind_mask
        pass_wind_count = np.sum(wind_valid & wind_mask)
        Logger.info(f"  风速筛选通过: {pass_wind_count} ({pass_wind_count / total_match_points * 100:.1f}%)")

    # 应用筛选
    df_filtered_by_criteria = df_matches[mask]
    pass_all_count = len(df_filtered_by_criteria)
    Logger.info(f"  所有条件通过: {pass_all_count} ({pass_all_count / total_match_points * 100:.1f}%)")
    Logger.info(f"筛选前匹配点数: {len(df_matches)}")
    Logger.info(f"筛选后匹配点数: {len(df_filtered_by_criteria)}")

    # ==================== 异常值处理（±15 cm） ====================
    threshold_cm = 15
    threshold_m = threshold_cm / 100

    outlier_mask = np.abs(df_filtered_by_criteria['diff']) > threshold_m
    num_outliers = np.sum(outlier_mask)

    if num_outliers > 0:
        Logger.info(
            f"检测到超出 ±{threshold_cm} cm 的异常点: {num_outliers} ({num_outliers / len(df_filtered_by_criteria) * 100:.2f}%)")
        df_cal = df_filtered_by_criteria[~outlier_mask]
    else:
        df_cal = df_filtered_by_criteria.copy()

    # percent05: 异常值剔除保留率（相对于筛选后的匹配点）
    percent05 = f"{(1 - num_outliers / len(df_filtered_by_criteria)) * 100:.1f}%" if len(
        df_filtered_by_criteria) > 0 else "N/A"

    # percent06: 最终有效数据占比（相对于原始匹配点）
    percent06 = f"{len(df_cal) / total_match_points * 100:.1f}%" if total_match_points > 0 else "N/A"

    Logger.info(f"异常值剔除保留率: {percent05}")
    Logger.info(f"最终有效数据占比: {percent06}")

    # ==================== 统计结果计算 ====================
    mean_diff = df_cal['diff'].mean()
    std_diff = df_cal['diff'].std()
    rmse = np.sqrt((df_cal['diff'] ** 2).mean())
    median_diff = df_cal['diff'].median()

    Logger.info("=" * 50)
    Logger.info(f"自交叉定标结果统计 ({satellite_name})")
    Logger.info("=" * 50)
    Logger.info(f"有效数据点数: {len(df_cal)}")
    Logger.info(f"平均差值 (上升轨-下降轨): {mean_diff:.6f} m ({mean_diff * 100:.3f} cm)")
    Logger.info(f"中位数差值: {median_diff:.6f} m ({median_diff * 100:.3f} cm)")
    Logger.info(f"标准差: {std_diff:.6f} m ({std_diff * 100:.3f} cm)")
    Logger.info(f"RMSE: {rmse:.6f} m ({rmse * 100:.3f} cm)")
    Logger.info("=" * 50)

    # 线性回归
    try:
        slope, intercept, r_value, p_value, std_err = stats_lib.linregress(df_cal['ssh_desc'], df_cal['ssh_asc'])
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
                           f"calibration_result_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.txt")
    with open(cal_txt, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("卫星高度计自交叉定标结果\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"卫星: {satellite_name}\n")
        f.write(f"时间范围: {ipf_config.Start_date} - {ipf_config.End_date}\n\n")
        f.write(f"有效数据点数: {len(df_cal)}\n")
        f.write(f"异常值阈值: ±{threshold_cm} cm (移除 {num_outliers} 点)\n\n")
        f.write("统计结果:\n")
        f.write(f"  平均差值 (上升轨-下降轨): {mean_diff * 100:.3f} cm\n")
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
                           f"calibration_data_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.npz")
    np.savez_compressed(cal_npz,
                        diff=df_cal['diff'].values,
                        ssh_asc=df_cal['ssh_asc'].values,
                        ssh_desc=df_cal['ssh_desc'].values,
                        lon=df_cal['lon'].values,
                        lat=df_cal['lat'].values)
    Logger.info(f"计算数据已保存至: {cal_npz}")

    # 生成图像
    Logger.info("生成可视化图像...")
    try:
        # 设置中文字体
        if os.path.exists(fontTTF):
            font_prop = FontProperties(fname=fontTTF)
            plt.rcParams['font.sans-serif'] = [font_prop.get_name()]
        else:
            plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
        plt.rcParams['axes.unicode_minus'] = False

        # 创建散点图 + 直方图
        fig1 = plt.figure(figsize=(12, 5))

        # 1. 散点图
        ax1 = plt.subplot(1, 2, 1)
        hb = ax1.hexbin(df_cal['ssh_desc'] * 100, df_cal['ssh_asc'] * 100,
                        gridsize=50, cmap='YlOrRd', mincnt=1)
        cbar = plt.colorbar(hb, ax=ax1, label='点数')
        cbar.ax.set_ylabel('点数', fontproperties=font_prop if 'font_prop' in dir() else None)

        if slope is not None:
            x_range = np.array([np.min(df_cal['ssh_desc']), np.max(df_cal['ssh_desc'])]) * 100
            y_line = slope * x_range / 100 + intercept
            ax1.plot(x_range, y_line * 100, 'b-', linewidth=2, label='拟合线')

        x_range = np.array([np.min(df_cal['ssh_desc']), np.max(df_cal['ssh_desc'])]) * 100
        ax1.plot(x_range, x_range, 'k--', linewidth=1, alpha=0.5, label='1:1线')

        ax1.set_xlabel('下降轨 SSH (cm)', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax1.set_ylabel('上升轨 SSH (cm)', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax1.set_title(f'{satellite_name} 自交叉定标', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax1.grid(True, alpha=0.3)
        ax1.legend(prop=font_prop if 'font_prop' in dir() else None)

        if slope is not None:
            textstr = f'y = {slope:.4f}x + {intercept * 100:.2f} cm\n'
            textstr += f'R² = {r_squared:.4f}\n'
            textstr += f'n = {len(df_cal)}'
            ax1.text(0.05, 0.95, textstr, transform=ax1.transAxes, fontsize=9,
                     verticalalignment='top', fontproperties=font_prop if 'font_prop' in dir() else None,
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        # 2. 差值直方图
        ax2 = plt.subplot(1, 2, 2)
        diff_cm = df_cal['diff'] * 100
        n, bins, patches = ax2.hist(diff_cm, bins=30, color='steelblue', edgecolor='black', alpha=0.7)
        ax2.axvline(x=mean_diff * 100, color='red', linestyle='--', linewidth=2,
                    label=f'均值: {mean_diff * 100:.2f} cm')
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=1, alpha=0.5)

        ax2.set_xlabel('SSH差值 (上升轨-下降轨) (cm)', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax2.set_ylabel('频数', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax2.set_title('SSH差值分布', fontproperties=font_prop if 'font_prop' in dir() else None)
        ax2.grid(True, alpha=0.3)
        ax2.legend(prop=font_prop if 'font_prop' in dir() else None)

        textstr2 = f'平均: {mean_diff * 100:.2f} cm\n'
        textstr2 += f'标准差: {std_diff * 100:.2f} cm\n'
        textstr2 += f'RMSE: {rmse * 100:.2f} cm'
        ax2.text(0.98, 0.95, textstr2, transform=ax2.transAxes, fontsize=9,
                 verticalalignment='top', horizontalalignment='right',
                 fontproperties=font_prop if 'font_prop' in dir() else None,
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

        plt.tight_layout()

        fig1_path = os.path.join(outputPath,
                                 f"calibration_plot_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.png")
        plt.savefig(fig1_path, dpi=300, bbox_inches='tight')
        plt.close(fig1)
        Logger.info(f"散点图和直方图已保存至: {fig1_path}")

        # 3. 空间分布图
        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature

            fig2 = plt.figure(figsize=(12, 10))
            ax3 = plt.subplot(1, 1, 1, projection=ccrs.PlateCarree())

            ax3.add_feature(cfeature.LAND, facecolor='lightgray', alpha=0.8)
            ax3.add_feature(cfeature.OCEAN, facecolor='lightblue', alpha=0.3)
            ax3.add_feature(cfeature.COASTLINE, linewidth=0.5)
            ax3.add_feature(cfeature.BORDERS, linewidth=0.3, alpha=0.5)

            gl = ax3.gridlines(draw_labels=True, linewidth=0.5, color='gray', alpha=0.3, crs=ccrs.PlateCarree())
            gl.top_labels = False
            gl.right_labels = False
            gl.xlabel_style = {'size': 10}
            gl.ylabel_style = {'size': 10}

            if len(df_cal) > 0:
                sc = ax3.scatter(df_cal['lon'], df_cal['lat'], c=df_cal['diff'] * 100,
                                 cmap='RdBu_r', s=15, alpha=0.6,
                                 vmin=-15, vmax=15, transform=ccrs.PlateCarree(),
                                 edgecolors='black', linewidth=0.3)

                cbar = plt.colorbar(sc, ax=ax3, label='SSH差值 (上升轨-下降轨) (cm)',
                                    orientation='horizontal', extend='both', shrink=0.8, pad=0.08)
                cbar.ax.set_xlabel('SSH差值 (cm)', fontproperties=font_prop if 'font_prop' in dir() else None,
                                   fontsize=10)

            ax3.set_global()
            ax3.set_extent([-180, 180, -60, 60], crs=ccrs.PlateCarree())
            ax3.set_title(f'{satellite_name} SSH差值空间分布', fontsize=12,
                          fontproperties=font_prop if 'font_prop' in dir() else None)

            plt.tight_layout()

            fig2_path = os.path.join(outputPath,
                                     f"spatial_distribution_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.png")
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

    # 获取图片路径
    spatial_img = os.path.join(outputPath,
                               f"spatial_distribution_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.png").replace(
        '\\', '/')
    scatter_img = os.path.join(outputPath,
                               f"calibration_plot_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.png").replace(
        '\\', '/')

    # 构建JSON数据
    json_data = {
        "${satId}": satellite_name_display,
        "${sensorId}": "ALT",
        "${sensorId_C}": "高度计",
        "${data_level}": "L2B_IGDR",
        "${method_name}": "SCC",
        "${method_name_C}": "自交叉法",
        "${start_time}": ipf_config.Start_date,
        "${end_time}": ipf_config.End_date,
        "${parameter_C}": "海面高度",
        "${data_version}": ipf_config.Data_version,
        "${algo_version}": "V01",
        "${responsibler}": "闫鹏",
        "${programmer}": "王士帅",
        "${produce_time}": datetime.now().strftime("%Y年%m月%d日"),
        "${introduction}": "海面高度自交叉定标法是指利用同一颗卫星的上升轨和下降轨交叉点处的海面高度观测值进行对比标定的方法，通过计算确定上升轨与下降轨之间的系统偏差，实现卫星高度计的自定标。",
        "${aux_data}": satellite_name_display,
        "${level}": "L2",
        "${aft_num}": str(len(df_cal)),
        "${aft_bias}": f"{mean_diff * 100:.2f}",
        "${aft_std}": f"{std_diff * 100:.2f}",
        "${coef}": f"{r_squared:.4f}" if r_squared is not None else "N/A",
        "${aux_data_des}": f"自交叉定标使用{satellite_name_display}卫星自身的上升轨和下降轨数据进行交叉比对。",
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
                             f"calibration_result_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    Logger.info(f"JSON标签文件已保存至: {json_path}")

    # ==================== 生成Word格式的报告文件 ====================
    Logger.info("生成Word报告文件...")

    try:
        from docx import Document
        from docx.shared import Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH

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
                if "${image_dist}" in paragraph.text or "${image_scatter_hist}" in paragraph.text or "${image_trend}" in paragraph.text:
                    continue
                for run in paragraph.runs:
                    for key, value in json_data.items():
                        if key in run.text:
                            run.text = run.text.replace(key, str(value))

            # 替换表格中的占位符
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            for run in paragraph.runs:
                                for key, value in json_data.items():
                                    if key in run.text:
                                        run.text = run.text.replace(key, str(value))

            # 处理图片插入
            for paragraph in doc.paragraphs:
                if "${image_dist}" in paragraph.text:
                    paragraph.clear()
                    img_path = json_data["${image_dist}"]
                    if os.path.exists(img_path):
                        run = paragraph.add_run()
                        run.add_picture(img_path, width=Inches(6.0))
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        Logger.info(f"已插入空间分布图: {img_path}")
                    else:
                        run = paragraph.add_run(f"[图片未生成: {img_path}]")
                        Logger.warn(f"空间分布图不存在: {img_path}")
                    break

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
                                       f"calibration_report_{sat_id}_self_cross_{ipf_config.Start_date}_{ipf_config.End_date}.docx")
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
    write_product_xml(product_xml_path, outputPath, ipf_config.outputFileType)
    # 函数write_product_xml传参：
    Logger.progress(100)

    result = {
        "statistics": {
            "satellite": satellite_name_display,
            "valid_points": int(len(df_cal)),
            "total_match_points": int(total_match_points),
            "outliers_removed": int(num_outliers),
            "mean_diff_cm": float(mean_diff * 100),
            "median_diff_cm": float(median_diff * 100),
            "std_diff_cm": float(std_diff * 100),
            "rmse_cm": float(rmse * 100),
            "slope": float(slope) if slope is not None else None,
            "intercept_cm": float(intercept * 100) if intercept is not None else None,
            "r_squared": float(r_squared) if r_squared is not None else None,
            "pass_area": match_stats.get('pass_area', 0),
            "pass_coast": match_stats.get('pass_coast', 0),
            "pass_depth": match_stats.get('pass_depth', 0),
            "pass_wind": match_stats.get('pass_wind', 0),
            "pass_all": pass_all_count,
        },
        "output_files": {
            "txt": cal_txt.replace('\\\\', '/'),
            "npz": cal_npz.replace('\\\\', '/'),
            "scatter_hist_png": scatter_img.replace('\\\\', '/'),
            "spatial_distribution_png": spatial_img.replace('\\\\', '/'),
            "json": json_path.replace('\\\\', '/'),
        },
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

    # 遍历目录中的所有文件
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)

        # 只处理文件，不处理目录
        if not os.path.isfile(filepath):
            continue
        # 检查文件后缀是否为.nc或.h5
        if not (filename.endswith('.nc') or filename.endswith('.h5')):
            continue
        # 检查文件名中是否包含卫星ID
        if sat_id not in filename:
            continue

        # 使用正则表达式提取文件名中的时间范围
        time_pattern = r'(\d{8}T\d{6})_(\d{8}T\d{6})'
        match = re.search(time_pattern, filename)

        if not match:
            continue

        # 提取时间范围
        start_time_str, end_time_str = match.groups()

        try:
            # 将时间字符串转换为datetime对象
            file_start_dt = datetime.strptime(start_time_str, "%Y%m%dT%H%M%S")
            file_end_dt = datetime.strptime(end_time_str, "%Y%m%dT%H%M%S")

            # 检查文件时间范围是否与查询时间范围有交集
            if file_end_dt < start_dt or file_start_dt > end_dt:
                continue

            # 如果有交集，则添加到文件列表
            file_list.append(filepath)

        except ValueError as e:
            print(f"警告: 无法解析文件 {filename} 中的日期: {e}")
            continue