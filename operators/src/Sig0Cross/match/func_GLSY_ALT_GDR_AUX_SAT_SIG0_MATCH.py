# -*- coding: utf-8 -*-
import sys
import os
import json
import numpy as np
import time
import datetime
import warnings
import matplotlib
matplotlib.use('Agg')          # 避免服务器无图形界面报错

from netCDF4 import Dataset
from CrossOverCalibration import CrossOverCalibration
from IPFUtils import Logger

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
    start_dt = datetime.datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.datetime.strptime(end_date, "%Y%m%d") + datetime.timedelta(days=1) - datetime.timedelta(seconds=1)

    if not os.path.isdir(directory):
        print(f"警告: 目录 {directory} 不存在")
        return file_list

    import re

    directory = os.path.abspath(directory)
    for root, dirs, files in os.walk(directory):
        for filename in files:
            # sprint(filename)
            if not (filename.endswith('.nc') or filename.endswith('.h5')):
                continue
            if sat_id not in filename:
                continue
            # 提取文件名中的时间范围
            time_pattern = r'(\d{8})(?:T|_)(\d{6}).*?(\d{8})(?:T|_)(\d{6})'
            match = re.search(time_pattern, filename)
            if not match:
                continue
            groups = match.groups()
            try:
                start_time_str = f"{groups[0]}T{groups[1]}"
                end_time_str = f"{groups[2]}T{groups[3]}"
                file_start_dt = datetime.datetime.strptime(start_time_str, "%Y%m%dT%H%M%S")
                file_end_dt = datetime.datetime.strptime(end_time_str, "%Y%m%dT%H%M%S")
                if file_end_dt < start_dt or file_start_dt > end_dt:
                    continue
                filepath = os.path.join(root, filename)
                file_list.append(filepath)
            except ValueError as e:
                print(f"警告: 无法解析文件 {filename} 中的日期: {e}")
                continue

    return file_list


def func_cross_matching_pro(ipf_config):
    """
    数据匹配部分主入口
    1. 从工单读取两颗卫星的数据目录
    2. 加载变量配置文件 config_S3_J3_1hz.json
    3. 进行轨道交叉匹配与插值
    4. 输出 HDF5 格式的交叉点数据
    """
    current_dir = os.getcwd()

    # current_dir = sys._MEIPASS
    # current_dir = os.path.abspath(current_dir)

    # 创建带卫星标识和时间戳的输出目录
    output_dir = os.path.join(
        ipf_config.output,
        "MDS_" + ipf_config.Sat_ID + "_" +
        ipf_config.AUX_Sat + "_" + ipf_config.Product_Type + "_" +
        ipf_config.Start_date + "_" + ipf_config.End_date + "_V" +
        ipf_config.Data_version
    )
    os.makedirs(output_dir, exist_ok=True)

    Logger.info("Start data matching")
    Logger.info("Get file list in input directory within specified time range")

    # 1. 获取两颗卫星的输入文件列表
    input_files_prim = get_file_list(
        ipf_config.input,
        ipf_config.Sat_ID,
        ipf_config.Start_date,
        ipf_config.End_date
    )
    input_files_aux = get_file_list(
        ipf_config.input_AUX,
        ipf_config.AUX_Sat,
        ipf_config.Start_date,
        ipf_config.End_date
    )

    if not input_files_prim or not input_files_aux:
        Logger.error("No valid input files found in the specified time range.")
        return 255

    # 2. 加载变量配置文件
    #根据ipf_config.Sat_ID和ipf_config.AUX_Sat选择不同的配置文件,拼出config_“ipf_config.Sat_ID”_“ipf_config.AUX_Sat"_1hz.json这个文件名，并在config目录下读取
    config_path = os.path.join(current_dir + os.sep + "config", f"config_{ipf_config.Sat_ID}_{ipf_config.AUX_Sat}_1hz.json")
    if not os.path.exists(config_path):
        Logger.error(f"Config file not found: {config_path}")
        return 255

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    var_schema_cmp = config.get('var_schema', {}).get('compareALT', {})
    var_schema_ref = config.get('var_schema', {}).get('referenceALT', {})

    # 使用每个角色的第一个候选变量名构建变量列表
    var1 = tuple(info['candidates'][0] for info in var_schema_cmp.values())
    var2 = tuple(info['candidates'][0] for info in var_schema_ref.values())

    # 3. 从配置文件中读取处理参数
    processing_params = config.get('processing_params', {})

    params = processing_params.get('processing_params', {})

    workers_config = params.get('workers', 20)         # 并行线程/进程数
    starttime = ipf_config.Start_date   # 起始时间，可为空
    endtime = ipf_config.End_date      # 终止时间，可为空
    timespan = processing_params.get('timespan', 10)       # 轨道匹配时间窗（小时）
    latlim = processing_params.get('latlim', 50)           # 纬度筛选阈值
    depthlim = processing_params.get('depthlim', -1000)    # 水深筛选阈值
    varlim = processing_params.get('varlim', 0.2)          # 变量一致性阈值/离群限制
    timeediting = processing_params.get('timeediting', 3)  # 时间编辑阈值（小时）


    # 限制并行数不超过 CPU 核心数
    cpu_count = os.cpu_count()
    if cpu_count is not None:
        workers = min(workers_config, cpu_count)
    else:
        workers = workers_config

    Logger.info(f"Configuration loaded: workers={workers}, timespan={timespan} days")

    # 4. 初始化交叉定标主类
    Logger.info("Initializing CrossOverCalibration engine...")
    T = CrossOverCalibration(
        ipf_config.input,
        ipf_config.input_AUX,
        var1,
        var2,
        var_schema_cmp=var_schema_cmp,
        var_schema_ref=var_schema_ref,
        config=config
    )

    Logger.progress(20)
    Logger.info("Reading satellite data in parallel...")
    T.readdata_parallel(sensor=ipf_config.Sat_ID, max_workers=workers,
                        starttime=starttime, endtime=endtime)

    Logger.progress(40)
    Logger.info("Matching orbits and searching for cross-over points...")
    T.matchdata(timespan=timespan, max_workers=workers)

    Logger.progress(60)
    Logger.info("Computing precise cross-over interpolations...")
    T.crossoverpoint(max_workers=workers)

    Logger.progress(80)
    Logger.info("Saving cross-over results to HDF5...")
    h5_dir = output_dir
    os.makedirs(h5_dir, exist_ok=True)
    T.accuracy(
        latlim=latlim,
        depthlim=depthlim,
        varlim=varlim,
        timeediting=timeediting
    )
    T.save_XOverPoint(savepath_h5=h5_dir)

    Logger.progress(100)
    Logger.info("Cross-over matching completed successfully.")

    # ==================== 新增：组装返回值 ====================

    result = {
        "statistics": {
            "bias": float(T.result['bias']) if T.result else None,
            "precision": float(T.result['precision']) if T.result else None,
            "count": int(T.result['count']) if T.result else None,
            "corr_coef": float(T.result['corr_coef']) if T.result else None,
        },
        "output_files": {
            "output_dir": output_dir.replace('\\', '/'),
        },
        "success": True,
    }
    return result