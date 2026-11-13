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
from docx import Document
# from docx.shared import Cm
import shutil
import json
import pandas as pd
import sys

from CrossOverCalibration import CrossOverCalibration, _build_var_mapping
from IPFUtils import Logger, write_product_xml

def _parse_folder_date_range(folder_name):
    """
    从文件夹名称中解析日期范围。
    支持格式: MDS_JA3_xx6_SIG0_YYYYMMDD_YYYYMMDD_V001

    返回: (start_date: datetime, end_date: datetime) 或 None
    """
    # 匹配 YYYYMMDD_YYYYMMDD 模式
    match = re.search(r'(\d{8})_(\d{8})', folder_name)
    if match:
        try:
            start = datetime.strptime(match.group(1), '%Y%m%d')
            end = datetime.strptime(match.group(2), '%Y%m%d')
            return start, end
        except ValueError:
            pass
    return None


def _check_date_overlap(folder_start, folder_end, xml_start, xml_end):
    """
    检查文件夹的日期范围是否与XML指定的时间范围有交集。

    参数:
        folder_start, folder_end: 文件夹日期范围
        xml_start, xml_end: XML指定的时间范围

    返回: True 如果有交集
    """
    return folder_start <= xml_end and folder_end >= xml_start


def _find_matching_subdirs(input_dir, start_dt, end_dt):
    """
    扫描输入目录下的子文件夹，找到日期范围与XML时间范围有交集的文件夹。

    参数:
        input_dir: 输入目录路径
        start_dt: XML起始日期
        end_dt: XML结束日期

    返回: [(subdir_path, folder_start, folder_end), ...] 匹配的子目录列表
    """
    matching_dirs = []

    if not os.path.exists(input_dir):
        Logger.error(f"Input directory does not exist: {input_dir}")
        return matching_dirs

    for item in os.listdir(input_dir):
        item_path = os.path.join(input_dir, item)
        if not os.path.isdir(item_path):
            continue

        date_range = _parse_folder_date_range(item)
        if date_range is None:
            continue

        folder_start, folder_end = date_range
        if _check_date_overlap(folder_start, folder_end, start_dt, end_dt):
            matching_dirs.append((item_path, folder_start, folder_end))
            Logger.info(f"Found matching directory: {item} "
                        f"(folder range: {folder_start.strftime('%Y%m%d')}-{folder_end.strftime('%Y%m%d')}, "
                        f"XML range: {start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')})")
        else:
            Logger.debug(f"Skipping directory {item}: no overlap with XML time range")

    return matching_dirs


def _read_h5_files_from_subdir(subdir_path, start_dt, end_dt):
    """
    从子目录中读取所有H5文件，按类型分类。

    参数:
        subdir_path: 子目录路径
        start_dt, end_dt: 时间范围（用于文件名时间过滤）

    返回: dict 包含三种类型的H5文件路径列表
        {
            'editing': [...],     # XOver_data_1_editing_*.h5
            'data_1': [...],      # XOver_data_1_*.h5 (排除 editing)
            'data_8': [...]       # XOver_data_8_*.h5
        }
    """
    h5_files = {'editing': [], 'data_1': [], 'data_8': []}

    if not os.path.exists(subdir_path):
        return h5_files

    for f in os.listdir(subdir_path):
        if not f.endswith('.h5'):
            continue

        fpath = os.path.join(subdir_path, f)

        # 从文件名中提取时间范围用于过滤
        # 文件名格式: XOver_data_N_YYYYMMDD_HHMMSS_YYYYMMDD_HHMMSS.h5
        time_match = re.search(r'(\d{8})_(\d{6})_(\d{8})_(\d{6})', f)
        if time_match:
            try:
                file_start = datetime.strptime(time_match.group(1) + time_match.group(2), '%Y%m%d%H%M%S')
                file_end = datetime.strptime(time_match.group(3) + time_match.group(4), '%Y%m%d%H%M%S')

                # 检查文件时间范围是否与XML时间范围有交集
                if not (file_start.replace(hour=0, minute=0, second=0) <= end_dt and
                        file_end.replace(hour=23, minute=59, second=59) >= start_dt):
                    Logger.debug(f"Skipping H5 file {f}: time range outside XML window")
                    continue
            except ValueError:
                Logger.warn(f"Cannot parse time from filename: {f}, including anyway")

        # 按类型分类
        if 'editing' in f.lower():
            h5_files['editing'].append(fpath)
        elif f.startswith('XOver_data_1_'):
            h5_files['data_1'].append(fpath)
        elif f.startswith('XOver_data_8_'):
            h5_files['data_8'].append(fpath)
        else:
            # 尝试根据内容判断类型
            try:
                with pd.HDFStore(fpath, 'r') as store:
                    keys = store.keys()
                    if any('editing' in k.lower() for k in keys):
                        h5_files['editing'].append(fpath)
                    else:
                        h5_files['data_1'].append(fpath)
            except Exception:
                Logger.warn(f"Cannot determine H5 file type: {f}, skipping")

    return h5_files


def _read_h5_data(h5_file_path):
    """
    读取单个H5文件中的数据。

    参数:
        h5_file_path: H5文件路径

    返回: dict 包含文件中所有数据表
    """
    data = {}
    try:
        with pd.HDFStore(h5_file_path, 'r') as store:
            for key in store.keys():
                # 移除前导 '/' 以便后续访问
                clean_key = key.lstrip('/')
                data[clean_key] = store[key]
        Logger.debug(f"Read H5 file: {os.path.basename(h5_file_path)}, "
                     f"keys: {list(data.keys())}")
    except Exception as e:
        Logger.error(f"Failed to read H5 file {h5_file_path}: {str(e)}")

    return data


def _load_all_matching_data(input_dir, start_dt, end_dt):
    """
    从所有匹配的子目录中加载H5数据。

    参数:
        input_dir: 输入目录路径
        start_dt, end_dt: XML时间范围

    返回: dict 包含所有加载的数据
        {
            'editing': {
                'XOver_editing1': [df1, df2, ...],
                'XOver_editing2': [df1, df2, ...],
                'XOver_editing_ssh1': [df1, df2, ...],
                'XOver_editing_ssh2': [df1, df2, ...]
            },
            'data_1': {
                'XOver_no_editing1': [df1, df2, ...],
                'XOver_no_editing2': [df1, df2, ...],
                'XOver_no_editing_ssh1': [df1, df2, ...],
                'XOver_no_editing_ssh2': [df1, df2, ...]
            },
            'data_8': {
                'XOver_data1': [df1, df2, ...],
                'XOver_data2': [df1, df2, ...]
            }
        }
    """
    # 找到所有匹配的子目录
    matching_dirs = _find_matching_subdirs(input_dir, start_dt, end_dt)

    if not matching_dirs:
        Logger.warn(f"No matching subdirectories found in {input_dir} "
                    f"for date range {start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')}")
        return None

    Logger.info(f"Found {len(matching_dirs)} matching subdirectories")

    # 初始化数据容器
    all_data = {
        'editing': {
            'XOver_editing1': [],
            'XOver_editing2': [],
            'XOver_editing_ssh1': [],
            'XOver_editing_ssh2': []
        },
        'data_1': {
            'XOver_no_editing1': [],
            'XOver_no_editing2': [],
            'XOver_no_editing_ssh1': [],
            'XOver_no_editing_ssh2': []
        },
        'data_8': {
            'XOver_data1': [],
            'XOver_data2': []
        },
        'matched_count': len(matching_dirs)  # 记录匹配的子目录数量
    }

    # 遍历所有匹配的子目录
    for subdir_path, folder_start, folder_end in sorted(matching_dirs, key=lambda x: x[1]):
        Logger.info(f"Processing directory: {os.path.basename(subdir_path)}")

        # 读取该子目录下的H5文件
        h5_files = _read_h5_files_from_subdir(subdir_path, start_dt, end_dt)

        # 处理 editing 文件
        for h5_path in h5_files['editing']:
            data = _read_h5_data(h5_path)
            for key in ['XOver_editing1', 'XOver_editing2',
                        'XOver_editing_ssh1', 'XOver_editing_ssh2']:
                if key in data:
                    all_data['editing'][key].append(data[key])

        # 处理 data_1 文件（编辑前数据）
        for h5_path in h5_files['data_1']:
            data = _read_h5_data(h5_path)
            for key in ['XOver_no_editing1', 'XOver_no_editing2',
                        'XOver_no_editing_ssh1', 'XOver_no_editing_ssh2']:
                if key in data:
                    all_data['data_1'][key].append(data[key])

        # 处理 data_8 文件（8点匹配数据）
        for h5_path in h5_files['data_8']:
            data = _read_h5_data(h5_path)
            for key in ['XOver_data1', 'XOver_data2']:
                if key in data:
                    all_data['data_8'][key].append(data[key])

    # 统计加载的数据量
    total_editing = sum(len(dfs) for dfs in all_data['editing'].values())
    total_data1 = sum(len(dfs) for dfs in all_data['data_1'].values())
    total_data8 = sum(len(dfs) for dfs in all_data['data_8'].values())

    if total_editing == 0 and total_data1 == 0 and total_data8 == 0:
        Logger.warn("No valid data found in any matching H5 files")
        return None

    Logger.info(f"Loaded data: editing={total_editing} datasets, "
                f"data_1={total_data1} datasets, data_8={total_data8} datasets")

    return all_data


def _generate_report(template_path, output_path, placeholders):
    """
    生成单份报告。

    参数:
        template_path: 模板文件路径
        output_path: 输出文件路径
        placeholders: 占位符字典

    返回: True 如果成功
    """
    try:
        from docx.shared import Cm
        doc = Document(template_path)

        # 替换段落中的占位符
        for para in doc.paragraphs:
            for key, val in placeholders.items():
                if key in para.text:
                    # 特殊处理：${image_Analysis} 需要插入图片而非替换为文字
                    if key == '${image_Analysis}' and val and os.path.exists(str(val)):
                        # 清空段落文本
                        for run in para.runs:
                            run.text = ''
                        # 在段落中插入图片（宽度15cm）
                        run = para.add_run()
                        run.add_picture(str(val), width=Cm(15))
                        break  # 图片已插入，不再处理其他占位符
                    else:
                        para.text = para.text.replace(key, str(val))

        # 替换表格中的占位符
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for key, val in placeholders.items():
                            if key in para.text:
                                para.text = para.text.replace(key, str(val))

        doc.save(output_path)
        Logger.info(f"Report saved: {output_path}")
        return True
    except Exception as e:
        Logger.error(f"Failed to generate report {output_path}: {str(e)}")
        return False


def func_cross_cal_pro(ipf_config):
    """
    统计计算部分：
    1. 从XML读取起始时间
    2. 扫描输出目录下的子文件夹，找到日期范围与XML时间有交集的文件夹
    3. 从匹配的子文件夹中读取所有H5数据
    4. 进行海洋气象参数时空分析（SIG0、SWH、Wind Speed）
    5. 根据分析结果和三份报告模板生成定标报告

    优化说明：
    - CrossOverCalibration.py 不参与修改
    - 所有数据加载、目录扫描、报告生成逻辑在此模块中实现
    - 支持多子目录数据合并分析
    """
    # =============================================================
    # 基本路径设置
    # =============================================================
    
    current_dir = os.getcwd()

    # current_dir = sys._MEIPASS
    # current_dir = os.path.abspath(current_dir)
    
    output_dir = ipf_config.output
    new_dir_path = os.path.join(ipf_config.output, "CAL_" + ipf_config.outputFileType + "_" +
                                ipf_config.Start_date + "_" + ipf_config.End_date + "_V" +
                                ipf_config.Data_version)
    output_dir = new_dir_path
    input_dir = ipf_config.input

    # 从XML解析时间范围
    start_dt = datetime.strptime(ipf_config.Start_date, "%Y%m%d")
    end_dt = datetime.strptime(ipf_config.End_date, "%Y%m%d") + timedelta(days=1) - timedelta(seconds=1)

    Logger.info(f"XML Time Range: {ipf_config.Start_date} to {ipf_config.End_date}")
    Logger.info(f"Input Directory: {input_dir}")
    Logger.info(f"Output Directory: {output_dir}")

    # =============================================================
    # 加载配置文件
    # =============================================================
    config_path = os.path.join(current_dir + os.sep + "config", f"config_{ipf_config.Sat_ID}_{ipf_config.AUX_Sat}_1hz.json")
    if not os.path.exists(config_path):
        if hasattr(sys, '_MEIPASS'):
            config_path = os.path.join(sys._MEIPASS, f"config_{ipf_config.Sat_ID}_{ipf_config.AUX_Sat}_1hz.json")

    if not os.path.exists(config_path):
        Logger.error(f"Config file not found: {config_path}")
        return 255

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    sat_cmp = config['compareALT']      # J3A
    sat_ref = config['referenceALT']    # S3A

    # 变量列表
    var_list_cmp = list(config['var_schema']['compareALT'].keys()) + ['cycle', 'pass']
    var_list_ref = list(config['var_schema']['referenceALT'].keys()) + ['cycle', 'pass']

    # =============================================================
    # 步骤1: 扫描匹配的子目录并加载H5数据
    # =============================================================
    Logger.info("=" * 80)
    Logger.info("Step 1: Scanning for matching subdirectories...")
    Logger.info("=" * 80)

    all_data = _load_all_matching_data(input_dir, start_dt, end_dt)

    if all_data is None:
        Logger.error("No matching data found. Exiting.")
        return 255

    # =============================================================
    # 步骤2: 合并非编辑数据（XOver_data_1）用于分析
    # =============================================================
    Logger.info("=" * 80)
    Logger.info("Step 2: Merging non-editing data (XOver_data_1) for analysis...")
    Logger.info("=" * 80)

    # 从配置中读取分析时间窗口（小时），默认2小时
    analysis_time_window_hours = config.get('processing_params', {}).get('analysis_time_window_hours', 2)
    Logger.info(f"Analysis time window: {analysis_time_window_hours} hours")

    # 使用非编辑数据（data_1）进行分析
    data_1 = all_data['data_1']
    XoverSub1_list = data_1['XOver_no_editing1']
    XoverSub2_list = data_1['XOver_no_editing2']

    if not XoverSub1_list or not XoverSub2_list:
        Logger.warn("No non-editing data_1 found, falling back to editing data...")
        editing_data = all_data['editing']
        XoverSub1_list = editing_data['XOver_editing1']
        XoverSub2_list = editing_data['XOver_editing2']

    if not XoverSub1_list or not XoverSub2_list:
        Logger.error("No data available for analysis (neither non-editing nor editing)")
        return 255

    # 合并非编辑数据
    XoverSub1 = pd.concat(XoverSub1_list, ignore_index=True)
    XoverSub2 = pd.concat(XoverSub2_list, ignore_index=True)

    Logger.info(f"Merged non-editing data: XoverSub1={len(XoverSub1)} rows, XoverSub2={len(XoverSub2)} rows")

    # 合并非编辑SSH数据（如果存在）
    ssh1_list = data_1.get('XOver_no_editing_ssh1', [])
    ssh2_list = data_1.get('XOver_no_editing_ssh2', [])

    if ssh1_list and ssh2_list:
        ssh1_merged = pd.concat(ssh1_list, ignore_index=True)
        ssh2_merged = pd.concat(ssh2_list, ignore_index=True)
        Logger.info(f"Merged non-editing SSH data: ssh1={len(ssh1_merged)} rows, ssh2={len(ssh2_merged)} rows")
    else:
        Logger.warn("No non-editing SSH data found, will skip SSH-related calculations")
        ssh1_merged = None
        ssh2_merged = None

    # =============================================================
    # 步骤2.5: 按时间窗口筛选数据
    # =============================================================
    Logger.info("=" * 80)
    Logger.info(f"Step 2.5: Filtering data by {analysis_time_window_hours}h time window...")
    Logger.info("=" * 80)

    # 获取变量映射以确定时间列名
    temp_var_schema_cmp = config['var_schema']['compareALT']
    temp_var_schema_ref = config['var_schema']['referenceALT']
    temp_vm1 = _build_var_mapping(temp_var_schema_cmp, XoverSub1.columns.tolist())
    temp_vm2 = _build_var_mapping(temp_var_schema_ref, XoverSub2.columns.tolist())

    time_col1 = temp_vm1.get('time')
    time_col2 = temp_vm2.get('time')

    if time_col1 and time_col2 and time_col1 in XoverSub1.columns and time_col2 in XoverSub2.columns:
        time1_vals = pd.to_numeric(XoverSub1[time_col1], errors='coerce')
        time2_vals = pd.to_numeric(XoverSub2[time_col2], errors='coerce')
        dt_hours = np.abs(time2_vals - time1_vals) / 3600.0
        time_mask = dt_hours <= analysis_time_window_hours

        n_before = len(XoverSub1)
        XoverSub1 = XoverSub1[time_mask].reset_index(drop=True)
        XoverSub2 = XoverSub2[time_mask].reset_index(drop=True)

        Logger.info(f"Time window filter: {n_before} → {len(XoverSub1)} rows "
                     f"(removed {n_before - len(XoverSub1)} points outside {analysis_time_window_hours}h window)")

        # 同步筛选SSH数据
        if ssh1_merged is not None and ssh2_merged is not None:
            ssh1_merged = ssh1_merged[time_mask].reset_index(drop=True)
            ssh2_merged = ssh2_merged[time_mask].reset_index(drop=True)
    else:
        Logger.warn(f"Cannot apply time window filter: time columns not found "
                     f"(time_col1={time_col1}, time_col2={time_col2})")

    # =============================================================
    # 步骤3: 构建 CrossOverCalibration 对象并注入数据
    # =============================================================
    Logger.info("=" * 80)
    Logger.info("Step 3: Building CrossOverCalibration object...")
    Logger.info("=" * 80)

    cal = CrossOverCalibration(
        path1='', path2='',
        var1=var_list_cmp, var2=var_list_ref,
        var_schema_cmp=config['var_schema']['compareALT'],
        var_schema_ref=config['var_schema']['referenceALT'],
        config=config
    )

    # 注入合并后的数据
    cal.XoverSub1 = XoverSub1
    cal.XoverSub2 = XoverSub2

    # 构建变量映射
    cal.var_mapping1 = _build_var_mapping(config['var_schema']['compareALT'], XoverSub1.columns.tolist())
    cal.var_mapping2 = _build_var_mapping(config['var_schema']['referenceALT'], XoverSub2.columns.tolist())

    # =============================================================
    # 步骤4: 设置输出目录
    # =============================================================
    fig_dir = os.path.join(output_dir, 'result', 'fig')
    csv_dir = os.path.join(output_dir, 'result', 'csv')
    # doc_dir = os.path.join(output_dir, 'result', 'doc')
    os.makedirs(fig_dir, exist_ok=True)
    os.makedirs(csv_dir, exist_ok=True)

    # 更新config中的路径（不修改CrossOverCalibration.py）
    config['path'][0]['savepath_fig'] = fig_dir
    config['path'][0]['csv_path'] = csv_dir

    # =============================================================
    # 步骤5: 执行海洋气象参数时空分析
    # =============================================================
    Logger.info("=" * 80)
    Logger.info("Step 5: Starting metocean spatial-temporal analysis...")
    Logger.info("=" * 80)

    cal.analyze_metocean_spatial_temporal(config)
    Logger.info("Analysis finished.")

    # =============================================================
    # 步骤6: 获取报告模板参数（由 analyze_metocean_spatial_temporal 计算并返回）
    # =============================================================
    Logger.info("=" * 80)
    Logger.info("Step 6: Retrieving report template parameters...")
    Logger.info("=" * 80)

    if not hasattr(cal, 'report_params') or not cal.report_params:
        Logger.warn("No report parameters generated, skipping report creation.")
        return 0

    report_params = cal.report_params

    # =============================================================
    # 步骤7: 生成报告
    # =============================================================
    Logger.info("=" * 80)
    Logger.info("Step 8: Generating reports...")
    Logger.info("=" * 80)

    report_dir = os.path.join(output_dir, 'reports')
    os.makedirs(report_dir, exist_ok=True)

    def find_2h_plot(var_fig_name):
        """找到2h时间窗口分析图路径（如 Analysis_S3A_vs_J3A_Sigma0_2h.png）"""
        target_suffix = f'{var_fig_name}_2h.png'
        for f in os.listdir(fig_dir):
            if f.endswith(target_suffix):
                return os.path.join(fig_dir, f)
        # 备选：匹配包含变量名和2h的文件
        for f in os.listdir(fig_dir):
            if f.endswith('.png') and var_fig_name in f and '2h' in f:
                return os.path.join(fig_dir, f)
        Logger.warn(f"2h plot not found for {var_fig_name} in {fig_dir}")
        return ''

    # 三份报告配置（各自携带独立的质量控制统计）
    params_config = [
        {
            'template': os.path.join(ipf_config.template_doc, 'MCS_GL_ALT_SIG0_CCS.docx'),
            'output': os.path.join(report_dir, f'MCS_GL_ALT_SIG0_{ipf_config.Start_date}_{ipf_config.End_date}.docx'),
            'parameter_name': '后向散射系数',
            'param_key': 'Sigma0',
            'fig_key': 'Sigma0'
        },
        {
            'template': os.path.join(ipf_config.template_doc, 'MCS_GL_ALT_SWH_CCS.docx'),
            'output': os.path.join(report_dir, f'MCS_GL_ALT_SWH_{ipf_config.Start_date}_{ipf_config.End_date}.docx'),
            'parameter_name': '有效波高',
            'param_key': 'SWH',
            'fig_key': 'SWH'
        },
        {
            'template': os.path.join(ipf_config.template_doc, 'MCS_GL_ALT_WS_CCS.docx'),
            'output': os.path.join(report_dir, f'MCS_GL_ALT_WS_{ipf_config.Start_date}_{ipf_config.End_date}.docx'),
            'parameter_name': '海面风速',
            'param_key': 'Wind Speed',
            'fig_key': 'Wind_Speed'
        }
    ]

    success_count = 0
    for p in params_config:
        if not os.path.exists(p['template']):
            Logger.warn(f"Template {p['template']} not found, skipping.")
            continue

        # 从 report_params 中获取该参数的模板参数
        rp = report_params.get(p['param_key'], {})

        placeholders = {
            '${satId}': sat_cmp,
            '${aux_data}': sat_ref,
            '${sensorId}': 'ALT',
            '${sensorId_C}': '高度计（ALT）',
            '${parameter_C}': p['parameter_name'],
            '${data_version}': ipf_config.Data_version,
            '${start_time}': ipf_config.Start_date,
            '${end_time}': ipf_config.End_date,
            '${aft_num}': str(rp.get('aft_num', 0)),
            '${aft_bias}': f"{rp.get('aft_bias', 0):.4f}",
            '${aft_std}': f"{rp.get('aft_std', 0):.4f}",
            '${coef}': f"{rp.get('coef', 0):.4f}",
            '${percent01}': f"{rp.get('percent01', 0) * 100:.1f}%",
            '${percent02}': f"{rp.get('percent02', 0) * 100:.1f}%",
            '${percent03}': f"{rp.get('percent03', 0) * 100:.1f}%",
            '${percent04}': f"{rp.get('percent04', 0) * 100:.1f}%",
            '${percent05}': f"{rp.get('percent05', 0) * 100:.1f}%",
            '${percent06}': f"{rp.get('percent06', 0) * 100:.1f}%",
            '${image_Analysis}': find_2h_plot(p['fig_key']),
            '${introduction}': '',
            '${data_level}': '',
            '${level}': '',
            '${aux_data_des}': '',
            '${algo_version}': '',
            '${responsibler}': '',
            '${programmer}': '',
            '${produce_time}': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        if _generate_report(p['template'], p['output'], placeholders):
            success_count += 1

    Logger.info(f"Generated {success_count}/{len(params_config)} reports successfully.")

    # =============================================================
    # 步骤8: 保存处理摘要
    # =============================================================
    summary = {
        'processing_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'xml_time_range': f"{ipf_config.Start_date} - {ipf_config.End_date}",
        'input_directory': input_dir,
        'output_directory': output_dir,
        'matched_subdirectories': all_data.get('matched_count', 0) if all_data else 0,
        'total_crossover_points': len(XoverSub1),
        'satellites': f"{sat_ref} vs {sat_cmp}",
        'report_params': report_params
    }

    summary_path = os.path.join(output_dir, 'processing_summary.json')
    try:
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
        Logger.info(f"Processing summary saved: {summary_path}")
    except Exception as e:
        Logger.warn(f"Failed to save processing summary: {str(e)}")

    Logger.info("=" * 80)
    Logger.info("All processing completed successfully!")
    Logger.info("=" * 80)

    str_order_id = "%010d" % int(ipf_config.order_id)
    product_xml_name = str_order_id + ".product.xml"
    product_xml_path = os.path.join(ipf_config.output, product_xml_name)
    outputPath = new_dir_path
    write_product_xml(product_xml_path, outputPath, ipf_config.outputFileType)
    # 函数write_product_xml传参：
    Logger.progress(100)

    result = {
        "statistics": {
            "matched_subdirectories": summary.get('matched_subdirectories', 0) if 'summary' in dir() else 0,
            "total_crossover_points": summary.get('total_crossover_points', 0) if 'summary' in dir() else 0,
            "satellites": summary.get('satellites', '') if 'summary' in dir() else '',
            "report_params": report_params if 'report_params' in dir() else None,
        },
        "output_files": {
            "output_dir": outputPath.replace('\\', '/') if 'outputPath' in dir() else output_dir.replace('\\', '/'),
            "processing_summary": os.path.join(output_dir, 'processing_summary.json').replace('\\', '/') if 'output_dir' in dir() else '',
            "fig_dir": os.path.join(output_dir, 'result', 'fig').replace('\\', '/') if 'output_dir' in dir() else '',
            "csv_dir": os.path.join(output_dir, 'result', 'csv').replace('\\', '/') if 'output_dir' in dir() else '',
        },
        "success": True,
    }
    
    return result
