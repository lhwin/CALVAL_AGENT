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


def func_ycz_matching_pro(ipf_config):
    # 非打包情况下使用
    current_dir = os.getcwd()
    # 打包时使用
    # current_dir = sys._MEIPASS
    # current_dir = os.path.abspath(current_dir)

    fontTTF = os.path.join(current_dir, "conf", "SimHei.ttf")
    font_prop = FontProperties(fname=fontTTF)
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams.update({'font.size': 14})

    # stpe1 配置文件加载及解析
    # 在输出目录下创建文件同名的文件夹，以存放产品
    new_dir_path = os.path.join(ipf_config.output, "MDS_" + ipf_config.Sat_ID + "_" +
                                ipf_config.AUX_YCZ + "_" + ipf_config.Product_Type + "_" +
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
    aux_file_list = get_file_list(ipf_config.input_AUX, ipf_config.AUX_YCZ, ipf_config.Start_date, ipf_config.End_date)

    Logger.info("Start data reading")

    Logger.info("Start data matching")

    # ========================== 新增的工程化匹配与底层模型读取代码开始 ==========================
    import netCDF4 as nc

    # --------- 1. 初始化 FES2014 和 DTU18 的数据读取器 ---------
    _FES2014_PATH = ipf_config.FES2014_PATH
    _DTU18_PATH = ipf_config.MSS_PATH # r'E:\dingbiao\DTU18MSS_1min.nc'

    TIDAL_FILES = {
        'M2': 'm2.nc', 'S2': 's2.nc', 'N2': 'n2.nc', 'K2': 'k2.nc', 'K1': 'k1.nc',
        'O1': 'o1.nc', 'P1': 'p1.nc', 'Q1': 'q1.nc', 'M4': 'm4.nc', 'M6': 'm6.nc'
    }

    _LON_LAT_CACHE = {}

    def get_fes_tidecons(lons, lats):
        """只负责读取 FES2014 的原始振幅和相位 (不计算)"""
        res = {name: np.zeros((len(lons), 4)) for name in TIDAL_FILES.keys()}
        search_radius = 0.05
        for name, fname in TIDAL_FILES.items():
            filepath = os.path.join(_FES2014_PATH, fname)
            try:
                if fname not in _LON_LAT_CACHE:
                    with nc.Dataset(filepath, 'r') as ds:
                        _LON_LAT_CACHE[fname] = {'lon': np.array(ds.variables['lon'][:], dtype=float),
                                                 'lat': np.array(ds.variables['lat'][:], dtype=float)}
                flon, flat = _LON_LAT_CACHE[fname]['lon'], _LON_LAT_CACHE[fname]['lat']

                with nc.Dataset(filepath, 'r') as ds:
                    for i in range(len(lons)):
                        lonp = np.where((flon > lons[i] - search_radius) & (flon < lons[i] + search_radius))[0]
                        latp = np.where((flat > lats[i] - search_radius) & (flat < lats[i] + search_radius))[0]
                        if len(lonp) == 0 or len(latp) == 0:
                            res[name][i] = [np.nan, 1.0, np.nan, 1.0];
                            continue

                        amp_sub = ds.variables['amplitude'][latp[0]:latp[-1] + 1, lonp[0]:lonp[-1] + 1]
                        pha_sub = ds.variables['phase'][latp[0]:latp[-1] + 1, lonp[0]:lonp[-1] + 1]
                        if hasattr(amp_sub, 'filled'): amp_sub = amp_sub.filled(np.nan)
                        if hasattr(pha_sub, 'filled'): pha_sub = pha_sub.filled(np.nan)

                        ampp, phsp = np.nanmean(np.array(amp_sub, dtype=float)), np.nanmean(
                            np.array(pha_sub, dtype=float))
                        if np.isnan(ampp) or np.isnan(phsp) or ampp == 0:
                            res[name][i] = [np.nan, 1.0, np.nan, 1.0]
                        else:
                            res[name][i] = [ampp, 1.0, phsp, 1.0]
            except Exception:
                for i in range(len(lons)): res[name][i] = [np.nan, 1.0, np.nan, 1.0]
        return res

    _MSS_DATA_CACHE = None

    def get_dtu_raw_mss(lons, lats):
        """只负责读取 DTU18 原始网格的海平面高度 (不加椭球修正)"""
        nonlocal _MSS_DATA_CACHE
        if _MSS_DATA_CACHE is None:
            with nc.Dataset(_DTU18_PATH, 'r') as dataset:
                londtu, latdtu = dataset.variables['lon'][:], dataset.variables['lat'][:]
                mss_raw = dataset.variables['mss'][:]
                if hasattr(mss_raw, 'filled'): mss_raw = mss_raw.filled(np.nan)
                _MSS_DATA_CACHE = {'lon': np.array(londtu, dtype=float), 'lat': np.array(latdtu, dtype=float),
                                   'mss': np.array(mss_raw, dtype=float)}

        londtu, latdtu, mssdtu = _MSS_DATA_CACHE['lon'], _MSS_DATA_CACHE['lat'], _MSS_DATA_CACHE['mss']
        out = np.zeros(len(lons))
        for i in range(len(lons)):
            p1 = np.where((londtu > lons[i] - 0.01) & (londtu < lons[i] + 0.01))[0]
            p2 = np.where((latdtu > lats[i] - 0.01) & (latdtu < lats[i] + 0.01))[0]
            if len(p1) == 0 or len(p2) == 0:
                out[i] = np.nan
            else:
                out[i] = np.nanmean(mssdtu[np.ix_(p2, p1)])
        return out

    # --------- 2. 原始卫星及辅助数据提取逻辑 ---------
    stations_config = {
        'zhiwan': {'id': 1, 'lon': 114.1479, 'lat': 21.9949, 'shift': 0.0},
        'wailingding': {'id': 2, 'lon': 114.0294, 'lat': 22.108, 'shift': 0.0356},
        'dangan': {'id': 3, 'lon': 114.3036, 'lat': 22.0594, 'shift': 0.0177}
    }

    def extract_date(name, is_nc=True, site=None):
        try:
            if is_nc and len(name) >= 35:
                d = name[27:35]
                if d.isdigit(): return d
            elif not is_nc:
                if site == 'zhiwan' and len(name) >= 24: return name[16:24]
                if site == 'wailingding' and len(name) >= 29: return name[21:29]
                if site == 'dangan' and len(name) >= 24: return name[16:24]
        except Exception:
            pass
        matches = re.findall(r'\d{8}', name)
        for m in matches:
            try:
                datetime.strptime(m, "%Y%m%d");
                return m
            except ValueError:
                pass
        return None

    real_nc_files = []
    if os.path.isdir(ipf_config.input):
        for root_dir, _, files in os.walk(ipf_config.input):
            for f in files:
                if f.endswith('.nc') and extract_date(f, is_nc=True):
                    real_nc_files.append(os.path.join(root_dir, f))

    real_aux_files = []
    if os.path.isdir(ipf_config.input_AUX):
        for root_dir, _, files in os.walk(ipf_config.input_AUX):
            for f in files:
                if f.endswith('.txt'): real_aux_files.append(os.path.join(root_dir, f))

    Logger.info(f"Found {len(real_nc_files)} NetCDF and {len(real_aux_files)} TXT files.")

    def load_tide_gauge_data(filepath):
        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1', 'cp1252']:
            try:
                return np.loadtxt(filepath, skiprows=37, encoding=encoding)
            except:
                continue
        return None

    matched_data_list = []

    for nc_path in real_nc_files:
        nc_basename = os.path.basename(nc_path)
        nc_date = extract_date(nc_basename, is_nc=True)
        if not nc_date: continue

        try:
            cycle_num = int(nc_basename[18:21])
        except Exception:
            cycle_num = 0

        try:
            with nc.Dataset(nc_path, 'r') as dataset:
                lon, lat = dataset.variables['lon'][:], dataset.variables['lat'][:]

                for site_name, cfg in stations_config.items():
                    lontg, lattg = cfg['lon'], cfg['lat']

                    lonp = np.where((lon < lontg + 0.15) & (lon > lontg - 0.15))[0]
                    latp = np.where((lat < lattg) & (lat > lattg - 0.15))[0]
                    position = np.intersect1d(lonp, latp)
                    if len(position) == 0: continue

                    alt = dataset.variables['alt'][position]
                    range_ku = dataset.variables['range_ku'][position]
                    dry = dataset.variables['model_dry_tropo_corr'][position]
                    wet = dataset.variables['rad_wet_tropo_corr'][position]
                    wetmod = dataset.variables['model_wet_tropo_corr'][position]
                    iono = dataset.variables['iono_corr_alt_ku'][position]
                    ssb = dataset.variables['sea_state_bias_ku'][position]
                    sol = dataset.variables['solid_earth_tide'][position]
                    load = dataset.variables['load_tide_sol1'][position]
                    pole = dataset.variables['pole_tide'][position]
                    time_sec = dataset.variables['time_sec'][position]

                    lon_p, lat_p = lon[position], lat[position]
                    sshalt = alt - (range_ku + dry + wet + iono + ssb) - sol - load - pole

                    valid_mask = ~np.isnan(sshalt)
                    if not np.any(valid_mask): continue

                    site_ycz_file = None
                    for yf in real_aux_files:
                        tg_date = extract_date(os.path.basename(yf), is_nc=False, site=site_name)
                        if tg_date == nc_date and (
                                site_name.lower() in yf.lower() or site_name.lower() in os.path.dirname(yf).lower()):
                            site_ycz_file = yf;
                            break

                    if not site_ycz_file: continue
                    tgdata = load_tide_gauge_data(site_ycz_file)
                    if tgdata is None: continue

                    timetg, tgssh = tgdata[:, 1], tgdata[:, 9] + cfg['shift']
                    positiontg = np.where((timetg > 180600) & (timetg < 182400))[0]
                    if len(positiontg) == 0: continue

                    tide001 = np.mean(tgssh[positiontg]) + 0.7118

                    time_first = time_sec[valid_mask][0]
                    hour = int(time_first // 3600)
                    minute = int((time_first - hour * 3600) // 60)
                    sec = int(time_first - hour * 3600 - minute * 60)
                    pass_time_str = f"{nc_date} {hour:02d}:{minute:02d}:{sec:02d}"

                    lon_p_valid = lon_p[valid_mask]
                    lat_p_valid = lat_p[valid_mask]

                    # ---------------- 执行 I/O: 抽取底层网格数据 ----------------
                    mss_raw_tg = get_dtu_raw_mss([lontg], [lattg])[0]
                    mss_raw_alt = get_dtu_raw_mss(lon_p_valid, lat_p_valid)

                    tidecons_tg = get_fes_tidecons([lontg], [lattg])
                    tidecons_alt = get_fes_tidecons(lon_p_valid, lat_p_valid)
                    # -------------------------------------------------------------

                    matched_data_list.append({
                        'site_name': site_name,
                        'site_id': cfg['id'],
                        'date': nc_date,
                        'pass_time_str': pass_time_str,
                        'cycle': cycle_num,
                        'sshalt': sshalt[valid_mask],
                        'tide001': tide001,
                        'lon_p': lon_p_valid,
                        'lat_p': lat_p_valid,
                        'lontg': lontg,
                        'lattg': lattg,
                        'mss_raw_tg': mss_raw_tg,
                        'mss_raw_alt': mss_raw_alt,
                        'tidecons_tg': tidecons_tg,
                        'tidecons_alt': tidecons_alt
                    })
        except Exception as e:
            Logger.warn(f"Error matching NetCDF file {nc_basename}: {str(e)}")

    Logger.info(f"Successfully IO extracted and matched {len(matched_data_list)} valid pass events.")

    npz_filename = f"MATCHED_{ipf_config.Sat_ID}_YCZ_{ipf_config.Start_date}_{ipf_config.End_date}.npz"
    npz_filepath = os.path.join(outputPath, npz_filename)
    np.savez_compressed(npz_filepath, match_records=np.array(matched_data_list, dtype=object))
    Logger.info(f"Matched raw data successfully exported to: {npz_filepath}")
    # ========================== 新增的工程化匹配与底层模型读取代码结束 ==========================

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
            "sat_id": ipf_config.Sat_ID,
            "aux_ycz": ipf_config.AUX_YCZ,
            "total_match_points": len(matched_data_list) if 'matched_data_list' in dir() else 0,
        },
        "output_files": {
            "npz": npz_filepath.replace('\\', '/') if 'npz_filepath' in dir() else '',
            "output_dir": outputPath.replace('\\', '/') if 'outputPath' in dir() else '',
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