# -*- coding: utf-8 -*-
"""
================================================================================
卫星测高交叉点校准系统 (Satellite Altimetry Cross-Over Calibration)
================================================================================

【项目概述】
本模块实现卫星测高数据的交叉点（Cross-Over）校准分析，用于评估和比较不同卫星
测高传感器（如Sentinel-3A、Jason-3等）的海面高度测量精度。

【核心功能】
1. 并行读取多源NetCDF格式卫星测高数据
2. 轨道交叉点匹配与筛选
3. 交叉点精确位置插值计算
4. 海面高度（SSH）精度评估与统计分析
5. 海洋气象参数（风速、有效波高、后向散射系数）的时空分布分析
6. 多格式数据导出（HDF5、CSV、Excel、可视化图表）

【技术特点】
- 支持双卫星独立变量映射配置
- 多进程并行处理大数据集
- 配置文件驱动的灵活参数设置
- 完善的质量控制与数据筛选机制
- 丰富的可视化输出（地理分布图、散点图、直方图、KDE等）

【依赖库】
- numpy, pandas: 数据处理与分析
- netCDF4: NetCDF文件读写
- scipy: 信号处理与插值
- matplotlib, seaborn, cartopy: 数据可视化
- concurrent.futures: 多进程并行计算
- tqdm: 进度条显示

================================================================================
版本: 1.0
================================================================================
"""

import warnings
import re
from concurrent.futures import ProcessPoolExecutor
from netCDF4 import Dataset, date2num, num2date
from os import listdir, path
import os
from pylab import zeros, arange, vstack, logical_and, logical_or, shape, subplot, save, plot, nan, float64, int32, \
    nanmean, nanstd, histogram, show, isnan, size, ones, convolve, clim, legend, xlabel, ylabel, array, savefig, log10, \
    any, where
from pandas import DataFrame, to_datetime, ExcelWriter
from XOver import XOverMatch, XOverPoint, smooth_iono, moving_average, smooth, smooth_v2, rollavg_pandas
from datetime import datetime
from tqdm import tqdm
import numpy as np
from matplotlib import cm
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
from scipy.interpolate import RegularGridInterpolator
import seaborn as sns
from scipy import stats
from scipy.interpolate import interp1d
import pandas as pd
import cartopy.feature as cfeature
from scipy.stats import binned_statistic
import pickle

# 抑制所有警告，避免输出信息过于杂乱
warnings.filterwarnings("ignore")


# =============================================================================
# 辅助函数模块
# =============================================================================
# 本模块包含数据处理中常用的辅助函数，包括NetCDF变量读取、变量名自动匹配、
# 变量映射构建等功能。这些函数被主类调用，完成数据预处理和准备工作。

def _read_nc_var(nc_obj, var_path):
    """
    【函数功能】
    解析带有Group路径的NetCDF变量，支持嵌套Group结构的变量访问。

    【参数说明】
    - nc_obj: netCDF4.Dataset对象，已打开的NetCDF文件句柄
    - var_path: 字符串，变量路径，格式如"group1/group2/variable_name"
               支持多层嵌套的Group结构

    【返回值】
    - 成功找到变量时返回变量数据数组（numpy.ndarray）
    - 未找到变量时返回None

    【使用示例】
    >>> data = _read_nc_var(nc_file, "data_01/latitude")
    >>> # 访问嵌套Group中的变量
    >>> range_data = _read_nc_var(nc_file, "data_01/ku/range_ocean")

    【技术实现】
    该函数通过递归遍历路径的每个部分，检查当前对象是否为Group或Variable。
    当找到对应的Variable时，返回其数据数组。如果路径中的任何部分不匹配，
    函数将返回None而不抛出异常。
    """
    parts = var_path.split('/')  # 将路径按'/'分割成各部分
    curr = nc_obj  # 从根对象开始遍历
    for p in parts:
        if p in curr.groups:  # 检查当前对象是否包含指定的Group
            curr = curr.groups[p]  # 进入下一层Group
        elif p in curr.variables:  # 检查当前对象是否包含指定的Variable
            return curr.variables[p][:]  # 找到变量，返回数据
    return None  # 路径遍历完毕未找到变量


def _resolve_var_name(actual_columns, candidates):
    """
    【函数功能】
    根据候选列表自动匹配实际数据中的列名，支持精确匹配和部分匹配两种模式。

    【参数说明】
    - actual_columns: list类型，数据帧（DataFrame）的实际列名列表
    - candidates: list类型，配置文件中定义的候选名称列表
                     按优先级排序，前面的名称优先匹配

    【返回值】
    - 匹配成功：返回实际数据中对应的列名（字符串）
    - 匹配失败：返回None

    【匹配策略】
    1. 精确匹配：检查候选名称是否完全等于某个实际列名
    2. 部分匹配（备选）：当精确匹配失败时，
       - 提取候选名称的基本名（去除路径后的最后一部分）
       - 检查基本名是否包含在任何实际列名中，或反之

    【使用场景】
    不同卫星数据源的NetCDF文件可能使用不同的变量命名规范，
    本函数通过灵活匹配机制实现配置的通用性。例如：
    - 配置中定义: ["data_01/latitude", "latitude"]
    - 实际文件可能使用: "lat" 或 "latitude" 或 "Latitude"
    """
    # 第一轮：精确匹配
    for candidate in candidates:
        if candidate in actual_columns:
            return candidate

    # 第二轮：部分匹配（处理命名变体）
    for candidate in candidates:
        # 提取候选名称的基本名（去除路径前缀）
        base_name = candidate.split('/')[-1] if '/' in candidate else candidate
        for col in actual_columns:
            # 检查双向包含关系
            if base_name in col or col in candidate:
                return col
    return None


def _build_var_mapping(var_schema, data_columns):
    """
    【函数功能】
    根据配置文件中的变量模式（schema）构建实际可用的变量映射字典。

    【参数说明】
    - var_schema: dict类型，配置文件中的变量模式，格式如下：
        {
            "lat": {"candidates": ["data_01/latitude", "lat"]},
            "lon": {"candidates": ["data_01/longitude", "lon"]},
            ...
        }
    - data_columns: list类型，实际数据帧中的列名列表

    【返回值】
    - dict类型，映射字典 {角色名: 实际列名}，格式：
        {
            "lat": "data_01/latitude",  # 匹配成功
            "lon": "longitude",         # 匹配成功
            "alt": None                 # 匹配失败
        }

    【设计目的】
    实现配置文件驱动的变量映射机制，使同一套代码能够处理不同数据源：
    - compareALT（待校准卫星）和referenceALT（参考卫星）可有独立的变量配置
    - 即使数据格式变化，只需修改配置文件，无需修改代码

    【错误处理】
    当某个角色名在数据中找不到匹配时：
    - 在映射字典中将该角色名映射为None
    - 打印警告信息提示用户
    """
    var_mapping = {}
    for role_name, role_info in var_schema.items():
        # 从角色信息中提取候选名称列表
        candidates = role_info.get('candidates', [])
        # 使用辅助函数进行匹配
        actual_name = _resolve_var_name(data_columns, candidates)
        if actual_name:
            var_mapping[role_name] = actual_name
        else:
            # 记录未匹配的变量，但不中断程序
            var_mapping[role_name] = None
            print(f"⚠️ 警告：未找到变量 '{role_name}' 的匹配列，候选：{candidates}")
    return var_mapping


# =============================================================================
# 多进程Worker函数模块
# =============================================================================
# 本模块定义用于多进程并行计算的工作函数。这些函数作为独立的worker进程运行，
# 负责处理单个任务（如读取文件、计算交叉点等）。

# 全局变量用于Worker进程间共享数据
_global_data1 = None  # 存储compareALT的完整数据矩阵
_global_data2 = None  # 存储referenceALT的完整数据矩阵


def _init_match_worker(d1, d2):
    """
    【函数功能】
    初始化Worker进程的全局变量，用于交叉点匹配计算。

    【参数说明】
    - d1: numpy.ndarray，compareALT的完整数据矩阵
    - d2: numpy.ndarray，referenceALT的完整数据矩阵

    【实现说明】
    由于ProcessPoolExecutor的worker进程无法直接访问主进程中的变量，
    需要通过全局变量机制在worker初始化时传入共享数据。
    每个worker进程维护一份数据的副本。
    """
    global _global_data1, _global_data2
    _global_data1 = d1
    _global_data2 = d2


def _process_single_nc(args):
    """
    【函数功能】
    多进程Worker：读取单个NetCDF文件并转换为数据矩阵。

    【参数说明】
    - args: tuple类型，包含以下元素：
        - file_path: str，NetCDF文件的完整路径
        - var_list: list，需要读取的变量名列表

    【返回值】
    - 成功读取：numpy.ndarray，数据矩阵，shape为(数据点数, 变量数+2)
               最后两列分别是cycleid和passid（初始化为0）
    - 读取失败或数据不足：None

    【数据处理流程】
    1. 打开NetCDF文件
    2. 读取基础变量（如经纬度）确定数据长度
    3. 数据长度过滤：少于160个点视为无效轨道
    4. 逐个读取指定变量并进行长度对齐
    5. 添加cycleid和passid占位列
    6. 替换无效值（32767、2147483647等填充值）为NaN

    【技术细节】
    - 变量长度不一致时进行线性插值对齐
    - 使用flatten()展平多维数据
    - 无效值自动替换避免后续计算出错
    """
    file_path, var_list = args
    try:
        with Dataset(file_path, 'r') as F:
            # 读取基础变量以确定数据长度
            base_var = _read_nc_var(F, var_list[0])
            if base_var is None:
                return None

            array_base = base_var.flatten()
            length = array_base.shape[0]

            # 数据长度过滤：排除无效的短轨道
            if length < 160:
                return None

            # 逐个读取变量并处理
            data_cols = []
            for var_name in var_list:
                val = _read_nc_var(F, var_name)
                if val is not None:
                    val = val.flatten()
                    # 处理长度不一致的情况（进行插值对齐）
                    if len(val) != length and len(val) > length:
                        x_old = np.linspace(0, 1, len(val))
                        x_new = np.linspace(0, 1, length)
                        val = np.interp(x_new, x_old, val)
                    data_cols.append(val)
                else:
                    # 变量缺失时用NaN填充
                    data_cols.append(np.full(length, np.nan))

            # 添加cycleid和passid占位列
            data_cols.append(np.zeros(length))  # cycleid
            data_cols.append(np.zeros(length))  # passid

            # 合并为数据矩阵
            matrix = np.column_stack(data_cols)

            # 替换NetCDF中的无效填充值为NaN
            matrix[np.logical_or(matrix == 32767, matrix == 2147483647)] = np.nan

            return matrix

    except Exception as e:
        # 任何读取错误都返回None，由主进程统一处理
        return None


def _process_match_task(args):
    """
    【函数功能】
    Worker函数：处理一对轨道的交叉点匹配计算。

    【参数说明】
    - args: tuple类型，包含：
        - idx1: int，compareALT数据中的轨道起始索引
        - len1: int，该轨道的数据点长度
        - idx2: int，referenceALT数据中的轨道起始索引
        - len2: int，该轨道的数据点长度

    【返回值】
    - 匹配成功：tuple类型，(Data1, Data2)，分别是两个轨道的8个匹配点数据
    - 匹配失败：None

    【匹配算法说明】
    1. 提取对应的轨道数据片段
    2. 调用XOverMatch函数进行交叉点搜索
    3. 验证SSH差异是否满足阈值条件
    4. 过滤异常海面高度值（>1500000m视为异常）

    【质量控制】
    - SSH差异阈值：两个方向的SSH差异之和应小于1000m
      这是基于物理常识的简单筛选条件
    """
    idx1, len1, idx2, len2 = args
    # 使用全局数据提取轨道片段
    data1_temp = _global_data1[idx1: idx1 + len1, :]
    data2_temp = _global_data2[idx2: idx2 + len2, :]

    from XOver import XOverMatch
    Data1, Data2 = XOverMatch(data1_temp, len1, data2_temp, len2)

    # 检查匹配是否有效（Data1首元素为NaN表示无匹配）
    if np.isnan(Data1[0, 0]):
        return None

    # 过滤异常SSH值（测高值通常在合理范围内）
    Data1[Data1[:, 3] > 1500000, 3] = np.nan
    Data2[Data2[:, 3] > 1500000, 3] = np.nan

    # 计算SSH差异用于质量筛选
    SSH_diff_1 = np.abs(Data1[:, 2] - Data1[:, 3])
    SSH_diff_2 = np.abs(Data2[:, 2] - Data2[:, 3])

    # 差异阈值筛选
    if np.nansum(SSH_diff_1) < 1000 and np.nansum(SSH_diff_2) < 1000:
        return Data1, Data2
    return None


def _process_crossover_point_task(args):
    """
    【函数功能】
    Worker函数：对8个匹配点进行精确的交叉点插值计算。

    【参数说明】
    - args: tuple类型，包含：
        - sub1: numpy.ndarray，compareALT的8个匹配点数据
        - sub2: numpy.ndarray，referenceALT的8个匹配点数据

    【返回值】
    - tuple类型，(p1, p2)，分别是两个卫星在交叉点的精确插值数据

    【算法说明】
    调用XOverPoint函数，通过线性回归拟合轨道轨迹，
    然后计算两条轨道的交点，并在交点处对各参数进行三次样条插值。

    【应用场景】
    XOverMatch返回的是8个近似匹配点，本函数进一步精确定位
    两条轨道的实际交叉位置，并获取该位置的完整测高参数。
    """
    sub1, sub2 = args
    from XOver import XOverPoint
    p1, p2 = XOverPoint(sub1, sub2)
    return p1, p2


# =============================================================================
# 主类定义
# =============================================================================

class CrossOverCalibration:
    """
    ========================================================================
    卫星测高交叉点校准主类
    ========================================================================

    【类概述】
    本类是卫星测高交叉点校准系统的核心，实现从原始NetCDF数据到精度评估的
    完整处理流程。采用面向对象设计，将数据和操作封装在一起。

    【设计特点】
    1. 配置文件驱动：所有可变参数从JSON配置读取
    2. 双卫星独立映射：支持compareALT和referenceALT使用不同的变量配置
    3. 多进程并行：利用ProcessPoolExecutor加速数据处理
    4. 链式调用：方法返回self，支持流畅接口（Fluent Interface）

    【核心数据结构】
    - Data1_ALL: compareALT的完整数据矩阵
    - Data2_ALL: referenceALT的完整数据矩阵
    - XoverMatchArray: 交叉匹配点数据
    - XoverSub: 交叉点精确插值数据
    - result: 精度评估结果字典

    【使用示例】
    >>> from CrossOverCalibration import CrossOverCalibration
    >>> T = CrossOverCalibration(path1, path2, var1, var2,
    ...                          var_schema_cmp, var_schema_ref, config)
    >>> T.readdata_parallel()
    >>> T.matchdata(timespan=10)
    >>> T.crossoverpoint()
    >>> T.accuracy()
    >>> T.save_XOverPoint()
    >>> T.cross_plot()
    """

    def __init__(self, path1, path2, var1, var2,
                 var_schema_cmp=None, var_schema_ref=None, config=None):
        """
        =====================================================================
        构造函数：初始化交叉点校准对象
        =====================================================================

        【参数说明】
        - path1: str，compareALT（待校准卫星）数据文件目录路径
        - path2: str，referenceALT（参考卫星）数据文件目录路径
        - var1: tuple/list，compareALT的变量列表，按顺序对应数据列
        - var2: tuple/list，referenceALT的变量列表
        - var_schema_cmp: dict，compareALT的变量映射模式（可选）
        - var_schema_ref: dict，referenceALT的变量映射模式（可选）
        - config: dict，完整配置文件字典（可选）

        【变量角色说明】
        变量模式定义每个变量的作用（角色），常见角色包括：
        - lat: 纬度
        - lon: 经度
        - alt: 卫星高度
        - range_ku: Ku波段测距值
        - time: 时间
        - dry: 干对流层校正
        - wet: 湿对流层校正
        - iono: 电离层校正
        - ssb_ku: 海况偏差（Ku波段）
        - ocean_tide: 海洋潮汐
        - solid_earth: 固体潮汐
        - pole_tide: 极潮
        - dac: 干空气压校正
        - inv_bar: 反气压计校正
        - swh: 有效波高
        - sig0: 后向散射系数
        - wind_speed: 风速
        - depth: 深度/高程

        【属性初始化】
        所有核心数据属性初始化为None，表示尚未加载处理。
        """
        # =============================================================
        # 路径和基础配置
        # =============================================================
        self.path1 = path1          # 待校准卫星数据路径
        self.path2 = path2          # 参考卫星数据路径
        self.var1 = var1            # 待校准卫星变量列表
        self.var2 = var2            # 参考卫星变量列表
        self.var_schema_cmp = var_schema_cmp or {}  # 待校准卫星变量模式
        self.var_schema_ref = var_schema_ref or {}  # 参考卫星变量模式
        self.config = config or {}  # 完整配置字典

        # =============================================================
        # 双卫星独立变量映射
        # =============================================================
        # 将配置中的角色名映射到实际数据列名
        # 例如: {"lat": "data_01/latitude", "lon": "data_01/longitude", ...}
        self.var_mapping1 = {}  # compareALT的变量映射
        self.var_mapping2 = {}  # referenceALT的变量映射

        # =============================================================
        # 核心数据矩阵
        # =============================================================
        self.Data1_ALL = None        # compareALT完整数据矩阵
        self.Data2_ALL = None        # referenceALT完整数据矩阵
        self.Data1_ALL_Length = None # compareALT各轨道数据长度
        self.Data2_ALL_Length = None # referenceALT各轨道数据长度

        # =============================================================
        # 交叉点相关数据
        # =============================================================
        self.XoverMatchArray_1 = None   # compareALT交叉匹配点
        self.XoverMatchArray_2 = None   # referenceALT交叉匹配点
        self.XoverSub1 = None           # compareALT交叉点精确插值
        self.XoverSub2 = None           # referenceALT交叉点精确插值
        self.data1_SSH = None           # compareALT海面高度
        self.data2_SSH = None           # referenceALT海面高度
        self.XoverSub1_valid = None    # 筛选后的compareALT数据
        self.XoverSub2_valid = None    # 筛选后的referenceALT数据
        self.data1_SSH_valid = None     # 筛选后的compareALT SSH
        self.data2_SSH_valid = None     # 筛选后的referenceALT SSH
        self.ssh_diff = None            # SSH差异（data1_SSH - data2_SSH）

        # =============================================================
        # 结果和输出路径
        # =============================================================
        self.result = None          # 精度评估结果字典
        self.bias_path = None       # 偏差结果文件路径
        self.savepath1 = None       # 地理分布图保存路径
        self.savepath2 = None       # 直方图保存路径

    @staticmethod
    def _extract_time_from_filename(filename):
        """
        =====================================================================
        从文件名中提取起始时间
        =====================================================================

        【支持的文件名格式】
        1. 含有 YYYYMMDD_HHMMSS 格式的时间戳
           例: JA3_GPN_2PfP128_006_20190730_220242_20190730_225854.nc
           提取第一个匹配: 20190730_220242 → datetime(2019,7,30,22,2,42)

        2. 含有 YYYYMMDDTHHMMSS 格式的时间戳
           例: xx6-01A_ALT_CSM_L2_GDR_0047_0307_20190801T101824_20190801T110551_V001.nc
           提取第一个匹配: 20190801T101824 → datetime(2019,8,1,10,18,24)

        【参数说明】
        - filename: str，文件名（不含路径）

        【返回值】
        - datetime 对象，若无法解析则返回 None
        """
        # 格式1: YYYYMMDD_HHMMSS
        m = re.search(r'(\d{8})_(\d{6})', filename)
        if m:
            try:
                return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
            except ValueError:
                pass

        # 格式2: YYYYMMDDTHHMMSS
        m = re.search(r'(\d{8})T(\d{6})', filename)
        if m:
            try:
                return datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
            except ValueError:
                pass

        return None

    def _get_files(self, path, starttime=None, endtime=None):
        """
        =====================================================================
        获取目录下的NetCDF文件（可选按文件名时间筛选）
        =====================================================================

        【参数说明】
        - path: str，目录路径
        - starttime: 起始时间筛选，支持 int(如20190801)、str(如"20190801")、datetime
        - endtime: 结束时间筛选，支持 int(如20190831)、str(如"20190831")、datetime

        【返回值】
        - list，排序后的NetCDF文件完整路径列表

        【功能说明】
        1. 检查目录是否存在
        2. 筛选扩展名为.nc的文件
        3. 若指定 starttime/endtime，根据文件名中的时间戳过滤
        4. 按文件名排序保证处理顺序一致
        """
        if not os.path.exists(path):
            return []
        # 列表推导式筛选.nc文件
        files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.nc')]

        # 如果指定了时间范围，按文件名时间过滤
        if starttime is not None or endtime is not None:
            # 统一转为 datetime 对象
            def _to_datetime(t):
                if isinstance(t, datetime):
                    return t
                if isinstance(t, int):
                    return datetime.strptime(str(t), '%Y%m%d')
                if isinstance(t, str):
                    t = t.strip()
                    for fmt in ('%Y%m%d', '%Y%m%d%H%M%S', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
                        try:
                            return datetime.strptime(t, fmt)
                        except ValueError:
                            continue
                return None

            dt_start = _to_datetime(starttime)
            dt_end = _to_datetime(endtime)
            # 若 endtime 为日期（无时分秒），扩展到当天末尾以包含当天所有文件
            if dt_end is not None and isinstance(endtime, (int, str)):
                s = str(endtime).strip()
                if len(s) == 8 and 'T' not in s:
                    dt_end = dt_end.replace(hour=23, minute=59, second=59)

            filtered = []
            for fpath in files:
                fname = os.path.basename(fpath)
                ftime = self._extract_time_from_filename(fname)
                if ftime is None:
                    # 无法从文件名解析时间的文件，跳过
                    continue
                if dt_start and ftime < dt_start:
                    continue
                if dt_end and ftime > dt_end:
                    continue
                filtered.append(fpath)

            total_before = len(files)
            files = filtered
            print(f"📂 时间筛选 {path}: {total_before} 个文件 → {len(files)} 个在范围 [{starttime} ~ {endtime}] 内")

        return sorted(files)

    def readdata_parallel(self, starttime=None, endtime=None, sensor='S3A', max_workers=12):
        """
        =====================================================================
        并行读取大批量NetCDF数据
        =====================================================================

        【参数说明】
        - starttime: 起始时间筛选（可选，秒为单位的时间戳）
        - endtime: 结束时间筛选（可选，秒为单位的时间戳）
        - sensor: 传感器标识符（用于日志输出）
        - max_workers: 最大并行worker数量，默认12

        【处理流程】
        1. 获取两个数据目录中的NetCDF文件列表
        2. 构建参数任务列表
        3. 使用ProcessPoolExecutor并行读取文件
        4. 合并各文件数据为完整数据矩阵
        5. 根据时间范围筛选数据（如果指定）

        【数据质量】
        - 过滤掉数据点少于160的轨道
        - 过滤掉cycleid为0的数据（无效标记）

        【日志输出】
        打印读取进度、文件数量、有效数据点数等信息

        【性能优化】
        - 使用ProcessPoolExecutor充分利用多核CPU
        - 使用tqdm显示读取进度
        - 批量合并数据减少内存碎片
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始并行读取卫星数据，Max_Workers: {max_workers}")

        # 获取文件列表（按文件名时间筛选）
        files1 = self._get_files(self.path1, starttime=starttime, endtime=endtime)
        files2 = self._get_files(self.path2, starttime=starttime, endtime=endtime)

        def run_parallel(file_list, vars_list, desc_text):
            """
            并行读取文件的核心函数

            参数:
            - file_list: NetCDF文件路径列表
            - vars_list: 需要读取的变量列表
            - desc_text: 进度条描述文字

            返回:
            - combined_data: 合并后的数据矩阵
            - combined_len: 各文件的数据长度数组
            """
            all_data = []   # 存储所有成功读取的数据
            all_len = []    # 存储各数据的长度
            args_list = [(f, vars_list) for f in file_list]

            # 使用进程池并行执行
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                results = list(tqdm(
                    executor.map(_process_single_nc, args_list),
                    total=len(args_list),
                    desc=desc_text
                ))

            # 收集有效结果
            for res_matrix in results:
                if res_matrix is not None:
                    all_data.append(res_matrix)
                    all_len.append(res_matrix.shape[0])

            if len(all_data) == 0:
                return None, None

            # 合并所有数据
            combined_data = np.vstack(all_data)
            combined_len = np.array(all_len)
            return combined_data, combined_len

        # =============================================================
        # 读取compareALT数据（待校准卫星）
        # =============================================================
        if files1:
            data1, len1 = run_parallel(files1, self.var1, 'Reading Data1 (compareALT)')
            if data1 is not None:
                # 过滤cycleid为0的数据（标记为无效）
                self.Data1_ALL = data1[data1[:, 5] != 0, :]
                self.Data1_ALL_Length = len1[len1 > 0]
                print(f"✅ Data1 (compareALT) 读取完成，有效数据点数：{self.Data1_ALL.shape[0]}")
            else:
                print("⚠️ 警告：Data1 文件夹中没有解析出有效数据。")
        else:
            print(f"⚠️ 警告：未找到 Data1 路径下的 .nc 文件 ({self.path1})")

        # =============================================================
        # 读取referenceALT数据（参考卫星）
        # =============================================================
        # 特殊情况：当两个路径相同时，执行自身交叉验证
        if self.path1 == self.path2:
            print("ℹ️  Path1 与 Path2 相同，执行自身交叉验证读取...")
            self.Data2_ALL = self.Data1_ALL
            self.Data2_ALL_Length = self.Data1_ALL_Length
        else:
            if files2:
                data2, len2 = run_parallel(files2, self.var2, 'Reading Data2 (referenceALT)')
                if data2 is not None:
                    self.Data2_ALL = data2[data2[:, 5] != 0, :]
                    self.Data2_ALL_Length = len2[len2 > 0]
                    print(f"✅ Data2 (referenceALT) 读取完成，有效数据点数：{self.Data2_ALL.shape[0]}")
                else:
                    print("⚠️ 警告：Data2 文件夹中没有解析出有效数据。")
            else:
                print(f"⚠️ 警告：未找到 Data2 路径下的 .nc 文件 ({self.path2})")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 并行读取阶段结束！\n")

    def matchdata(self, timespan=10, max_workers=12):
        """
        =====================================================================
        计算时空匹配组合
        =====================================================================

        【参数说明】
        - timespan: 时间跨度阈值（天），默认10天
        - max_workers: 最大并行worker数量

        【功能说明】
        1. 构建所有轨道的时空匹配任务
        2. 筛选时间差在阈值内的轨道对
        3. 并行计算每对轨道的交叉点
        4. 应用双卫星独立质量筛选

        【匹配策略】
        - 轨道对的时间差 < timespan * 86400秒
        - 使用XOverMatch算法寻找交叉点
        - SSH差异阈值筛选

        【质量筛选】
        - 基于var_schema配置的双卫星独立筛选
        - 逻辑AND合并两个卫星的筛选条件

        【异常处理】
        若未找到任何有效交叉点，抛出ValueError异常
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始计算时空匹配组合...")

        # 数据完整性检查
        if self.Data1_ALL is None or self.Data2_ALL is None:
            raise ValueError("数据未加载完成，请先执行 readdata_parallel()")

        # 计算各轨道的起始索引
        idx_starts_1 = np.insert(np.cumsum(self.Data1_ALL_Length)[:-1], 0, 0)
        idx_starts_2 = np.insert(np.cumsum(self.Data2_ALL_Length)[:-1], 0, 0)

        # 构建匹配任务列表
        tasks = []
        for start1, len1 in zip(idx_starts_1, self.Data1_ALL_Length):
            time1 = self.Data1_ALL[start1, 5]  # 获取轨道起始时间
            for start2, len2 in zip(idx_starts_2, self.Data2_ALL_Length):
                time2 = self.Data2_ALL[start2, 5]
                # 时间跨度筛选
                if abs(time1 - time2) < timespan * 86400:
                    tasks.append((start1, len1, start2, len2))

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功筛选 {len(tasks)} 对符合时间约束的轨道，开始并行计算交叉点...")

        # 存储匹配结果
        matched_1 = []
        matched_2 = []

        # 并行执行交叉点匹配
        with ProcessPoolExecutor(max_workers=max_workers,
                                 initializer=_init_match_worker,
                                 initargs=(self.Data1_ALL, self.Data2_ALL)) as executor:

            results = list(tqdm(
                executor.map(_process_match_task, tasks, chunksize=50),
                total=len(tasks),
                desc="Matching Data"
            ))

        # 收集有效匹配结果
        for res in results:
            if res is not None:
                matched_1.append(res[0])
                matched_2.append(res[1])

        # 检查是否有有效匹配
        if not matched_1:
            raise ValueError("在指定的 timespan 内未找到任何有效的时空交叉点！")

        # 合并匹配数据
        XoverMatchArray_1 = np.vstack(matched_1)
        XoverMatchArray_2 = np.vstack(matched_2)

        # 转换为DataFrame便于后续处理
        data1 = pd.DataFrame(XoverMatchArray_1, columns=self.var1 + ('cycle', 'pass'))
        data2 = pd.DataFrame(XoverMatchArray_2, columns=self.var2 + ('cycle', 'pass'))

        # =============================================================
        # 双卫星独立质量筛选
        # =============================================================
        idx_vld1 = self._apply_quality_filter(
            data1, self.var1, self.var_schema_cmp,
            self.config.get('quality_filter', {}).get('compareALT', {})
        )
        idx_vld2 = self._apply_quality_filter(
            data2, self.var2, self.var_schema_ref,
            self.config.get('quality_filter', {}).get('referenceALT', {})
        )

        # 合并筛选条件（数据点必须同时满足两个卫星的筛选条件）
        idx_vld = np.logical_and(idx_vld1, idx_vld2)
        # 剔除整组8个点（交叉点组）
        idx_vld_num = 8 * np.unique(np.array(np.where(~idx_vld)) // 8).reshape((-1, 1)) + np.arange(8)
        idx_vld_num = idx_vld_num.flatten()

        # 应用筛选，保留无效点
        self.XoverMatchArray_1 = data1.drop(index=idx_vld_num)
        self.XoverMatchArray_2 = data2.drop(index=idx_vld_num)

        # 建立双卫星独立变量映射
        self.var_mapping1 = _build_var_mapping(self.var_schema_cmp, data1.columns)
        self.var_mapping2 = _build_var_mapping(self.var_schema_ref, data2.columns)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 匹配筛选完毕！")

    def _apply_quality_filter(self, data, var_list, var_schema, quality_filter):
        """
        =====================================================================
        根据配置文件应用质量筛选
        =====================================================================

        【参数说明】
        - data: pandas.DataFrame，待筛选的数据
        - var_list: list，变量列表（列名）
        - var_schema: dict，变量模式配置
        - quality_filter: dict，质量过滤配置，格式如：
            {
                "dry": {"min": -2.5, "max": -1.9},
                "wet": {"min": -0.5, "max": -0.001},
                ...
            }

        【返回值】
        - numpy.ndarray，布尔掩码数组，True表示该行数据有效

        【筛选逻辑】
        1. 遍历质量过滤配置的每个变量
        2. 解析变量名（从var_schema获取候选列表）
        3. 查找数据中对应的实际列
        4. 应用min/max阈值范围筛选
        5. 所有条件取逻辑AND

        【设计目的】
        支持双卫星使用不同的质量筛选标准，实现灵活的参数控制
        """
        if not quality_filter:
            return np.ones(len(data), dtype=bool)

        # 构建变量名到列索引的映射
        col_mapping = {var_name: idx for idx, var_name in enumerate(var_list)}

        conditions = []
        for var_role, filter_range in quality_filter.items():
            actual_var = None
            if var_role in var_schema:
                # 获取该变量的候选名称列表
                candidates = var_schema[var_role].get('candidates', [])
                actual_var = _resolve_var_name(list(col_mapping.keys()), candidates)

            if actual_var and actual_var in col_mapping:
                col_idx = col_mapping[actual_var]
                min_val = filter_range.get('min', -np.inf)
                max_val = filter_range.get('max', np.inf)
                # 构建该变量的筛选条件
                conditions.append((data.iloc[:, col_idx] >= min_val) & (data.iloc[:, col_idx] <= max_val))

        if conditions:
            return np.logical_and.reduce(conditions)
        else:
            return np.ones(len(data), dtype=bool)

    def crossoverpoint(self, max_workers=12):
        """
        =====================================================================
        并行计算交叉点精确插值位置
        =====================================================================

        【参数说明】
        - max_workers: 最大并行worker数量

        【功能说明】
        对matchdata步骤找到的8点匹配组进行精确的交叉点计算：
        1. 拟合每条轨道的轨迹方程
        2. 计算两条轨道的交点坐标
        3. 在交点处对所有参数进行三次样条插值

        【数据要求】
        - XoverMatchArray_1和XoverMatchArray_2必须已初始化
        - 数据以8个点为一组（交叉点组）

        【算法实现】
        使用XOverPoint函数完成，详见XOver.py模块

        【输出说明】
        - XoverSub1: compareALT交叉点数据（DataFrame格式）
        - XoverSub2: referenceALT交叉点数据（DataFrame格式）
        """
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始并行计算交叉点精确插值位置...")

        # 数据完整性检查
        if self.XoverMatchArray_1 is None or self.XoverMatchArray_2 is None:
            raise ValueError("交叉匹配数据未生成，请先执行 matchdata()")

        XoverMatchArray_1 = np.array(self.XoverMatchArray_1)
        XoverMatchArray_2 = np.array(self.XoverMatchArray_2)

        # 计算交叉点数量（每8个点为一个交叉点组）
        n_points = shape(XoverMatchArray_1)[0] // 8

        # 初始化输出数组
        XoverSub1 = np.zeros((n_points, self.Data2_ALL.shape[1]))
        XoverSub2 = np.zeros((n_points, self.Data2_ALL.shape[1]))

        # 构建任务列表
        tasks = []
        for i in range(n_points):
            sub1 = XoverMatchArray_1[i * 8:(i + 1) * 8, :]
            sub2 = XoverMatchArray_2[i * 8:(i + 1) * 8, :]
            tasks.append((sub1, sub2))

        # 并行执行插值计算
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            results = list(tqdm(
                executor.map(_process_crossover_point_task, tasks, chunksize=1000),
                total=len(tasks),
                desc="Interpolating Points"
            ))

        # 收集结果
        for i, (p1, p2) in enumerate(results):
            XoverSub1[i, :] = p1
            XoverSub2[i, :] = p2

        # 转换为DataFrame格式并重置索引
        self.XoverSub1 = DataFrame(XoverSub1, columns=self.var1 + ('cycle', 'pass')).reset_index(drop=True)
        self.XoverSub2 = DataFrame(XoverSub2, columns=self.var2 + ('cycle', 'pass')).reset_index(drop=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 插值计算完毕！")

    def accuracy(self, latlim=50, depthlim=-1000, varlim=0.2, timeediting=10):
        """
        =====================================================================
        计算SSH精度
        =====================================================================

        【参数说明】
        - latlim: 纬度限制（度），默认±50°
        - depthlim: 深度限制（米），默认-1000m（海洋）
        - varlim: 差异阈值（米），默认0.2m
        - timeediting: 时间编辑阈值（天），默认10天

        【功能说明】
        1. 计算两条轨道的海面高度（SSH）
        2. 计算SSH差异并进行质量筛选
        3. 统计精度指标（STD、Bias等）
        4. 剔除异常值（基于IQR方法）

        【SSH计算公式】
        SSH = 卫星高度 - 测距值 - 各项校正
            = alt - (range_ku + dry + wet + iono + ssb_ku
                   + ocean_tide + solid_earth + pole_tide + dac/inv_bar)

        【质量筛选条件】
        - |SSH| < 120m（物理范围）
        - |纬度| < latlim
        - |时间差| < timeediting天
        - 深度 < depthlim（海洋区域）

        【异常值剔除】
        - IQR方法：Q1-3*(Q3-Q2) < value < Q4+3*(Q3-Q2)
        - 差异阈值：|diff - mean| < varlim

        【输出结果】
        self.result字典包含：
        - precision: 标准差（STD）
        - bias: 平均偏差
        - count: 有效点数
        - corr_coef: 相关系数
        - data1_MSS: 待校准卫星平均海面高
        - data2_MSS: 参考卫星平均海面高
        - remove_rate: 各类剔除率统计
        """
        if self.XoverSub1 is None or self.XoverSub2 is None:
            raise ValueError("交叉点数据未生成，请先执行 crossoverpoint()")

        # 重置DataFrame索引
        self.XoverSub1 = self.XoverSub1.reset_index(drop=True)
        self.XoverSub2 = self.XoverSub2.reset_index(drop=True)

        XoverSub1 = self.XoverSub1
        XoverSub2 = self.XoverSub2

        # =============================================================
        # 使用双卫星独立变量映射获取关键变量名
        # =============================================================
        vm1 = self.var_mapping1  # compareALT
        vm2 = self.var_mapping2  # referenceALT

        # 获取各变量的实际列名
        time1, alt1, lat1 = vm1.get('time'), vm1.get('alt'), vm1.get('lat')
        range_ku1, dry1, wet1 = vm1.get('range_ku'), vm1.get('dry'), vm1.get('wet')
        iono1, sea_state1 = vm1.get('iono'), vm1.get('ssb_ku')
        ocean_tide1, solid_earth1, pole_tide1 = vm1.get('ocean_tide'), vm1.get('solid_earth'), vm1.get('pole_tide')
        hf1, inv1 = vm1.get('dac'), vm1.get('inv_bar')
        depth1 = vm1.get('depth')

        time2, alt2, lat2 = vm2.get('time'), vm2.get('alt'), vm2.get('lat')
        range_ku2, dry2, wet2 = vm2.get('range_ku'), vm2.get('dry'), vm2.get('wet')
        iono2, sea_state2 = vm2.get('iono'), vm2.get('ssb_ku')
        ocean_tide2, solid_earth2, pole_tide2 = vm2.get('ocean_tide'), vm2.get('solid_earth'), vm2.get('pole_tide')
        hf2, inv2 = vm2.get('dac'), vm2.get('inv_bar')
        depth2 = vm2.get('depth')

        # =============================================================
        # 必要变量检查
        # =============================================================
        required_vars1 = [time1, alt1, lat1, range_ku1, dry1, wet1, iono1, sea_state1,
                          ocean_tide1, solid_earth1, pole_tide1, depth1]
        required_vars2 = [time2, alt2, lat2, range_ku2, dry2, wet2, iono2, sea_state2,
                          ocean_tide2, solid_earth2, pole_tide2, depth2]

        missing1 = [k for k, v in vm1.items() if v is None and k in ['time', 'alt', 'lat', 'range_ku']]
        missing2 = [k for k, v in vm2.items() if v is None and k in ['time', 'alt', 'lat', 'range_ku']]

        if missing1 or missing2:
            raise ValueError(f"❌ 变量映射不完整 - Data1缺失：{missing1}, Data2缺失：{missing2}")

        # =============================================================
        # 计算SSH（双卫星独立计算）
        # =============================================================
        # compareALT的SSH计算
        if hf1 and 'dac' in hf1.lower():
            data1_SSH = XoverSub1[alt1] - (XoverSub1[range_ku1] + XoverSub1[dry1] +
                                           XoverSub1[wet1] + XoverSub1[iono1] +
                                           XoverSub1[sea_state1] + XoverSub1[ocean_tide1] +
                                           XoverSub1[solid_earth1] + XoverSub1[pole_tide1] +
                                           XoverSub1[hf1])
        else:
            data1_SSH = XoverSub1[alt1] - (XoverSub1[range_ku1] + XoverSub1[dry1] +
                                           XoverSub1[wet1] + XoverSub1[iono1] +
                                           XoverSub1[sea_state1] + XoverSub1[ocean_tide1] +
                                           XoverSub1[solid_earth1] + XoverSub1[pole_tide1] +
                                           XoverSub1.get(inv1, 0) + XoverSub1.get(hf1, 0))
        self.data1_SSH = data1_SSH

        # referenceALT的SSH计算
        if hf2 and 'dac' in hf2.lower():
            data2_SSH = XoverSub2[alt2] - (XoverSub2[range_ku2] + XoverSub2[dry2] +
                                           XoverSub2[wet2] + XoverSub2[iono2] +
                                           XoverSub2[sea_state2] + XoverSub2[ocean_tide2] +
                                           XoverSub2[solid_earth2] + XoverSub2[pole_tide2] +
                                           XoverSub2[hf2])
        else:
            data2_SSH = XoverSub2[alt2] - (XoverSub2[range_ku2] + XoverSub2[dry2] +
                                           XoverSub2[wet2] + XoverSub2[iono2] +
                                           XoverSub2[sea_state2] + XoverSub2[ocean_tide2] +
                                           XoverSub2[solid_earth2] + XoverSub2[pole_tide2] +
                                           XoverSub2.get(inv2, 0) + XoverSub2.get(hf2, 0))
        self.data2_SSH = data2_SSH

        # =============================================================
        # 质量筛选
        # =============================================================
        idx0 = logical_and.reduce((
            abs(data1_SSH) < 120,              # SSH物理范围
            abs(data2_SSH) < 120,              # SSH物理范围
            abs(XoverSub1[lat1]) < latlim,     # 纬度限制
            np.abs(XoverSub1[time1] - XoverSub2[time2]) / 86400.0 < timeediting,  # 时间差限制
            XoverSub1[depth1] < depthlim        # 海洋深度限制
        ))

        # 统计各类剔除率
        lat_remove_rate = np.sum(abs(XoverSub1[lat1]) > latlim) / len(abs(XoverSub1[lat1]))
        depth_remove_rate = np.sum(XoverSub1[depth1] > depthlim) / len(abs(XoverSub1[depth1]))
        time_remove_rate = np.sum(np.abs(XoverSub1[time1] - XoverSub2[time2]) / 86400.0 > timeediting) / len(
            abs(XoverSub1[depth1]))
        ssh_diff = data1_SSH - data2_SSH
        SSH_all_num = np.sum(~np.isnan(ssh_diff))
        var_remove_rate = np.sum(abs(ssh_diff - nanmean(ssh_diff)) > varlim) / SSH_all_num

        # 应用筛选
        ssh_diff[~idx0] = nan

        # =============================================================
        # IQR异常值剔除
        # =============================================================
        Q1 = ssh_diff.quantile(q=0.05)
        Q2 = ssh_diff.quantile(q=0.25)
        Q3 = ssh_diff.quantile(q=0.75)
        Q4 = ssh_diff.quantile(q=0.95)
        ssh_diff[logical_or(ssh_diff < Q1 - 3 * (Q3 - Q2), ssh_diff > Q4 + 3 * (Q3 - Q2))] = nan
        ssh_diff[abs(ssh_diff - nanmean(ssh_diff)) > varlim] = nan

        # 保存筛选后的数据
        self.XoverSub1_valid = XoverSub1[~isnan(ssh_diff)]
        self.XoverSub2_valid = XoverSub2[~isnan(ssh_diff)]
        self.data1_SSH_valid = data1_SSH[~isnan(ssh_diff)]
        self.data2_SSH_valid = data2_SSH[~isnan(ssh_diff)]
        self.ssh_diff = ssh_diff[~isnan(ssh_diff)]

        # 统计总剔除率和相关系数
        total_remove_rate = (SSH_all_num - np.sum(~np.isnan(ssh_diff))) / SSH_all_num
        corr_coef = np.corrcoef(data1_SSH[~isnan(ssh_diff)], data2_SSH[~isnan(ssh_diff)])[0][1]

        # 保存结果字典
        self.result = {
            'precision': nanstd(ssh_diff),
            'bias': nanmean(ssh_diff),
            'count': sum(~isnan(ssh_diff)),
            'remove_rate': {
                'lat_remove_rate': lat_remove_rate,
                'depth_remove_rate': depth_remove_rate,
                'time_remove_rate': time_remove_rate,
                'var_remove_rate': var_remove_rate,
                'total_remove_rate': total_remove_rate
            },
            'corr_coef': corr_coef,
            'data1_MSS': np.nanmean(data1_SSH[~isnan(ssh_diff)]),
            'data2_MSS': np.nanmean(data2_SSH[~isnan(ssh_diff)])
        }

        # 打印结果摘要
        print(f"\n{'='*60}")
        print(f"SSH 精度计算结果:")
        print(f"  Precision (STD): {self.result['precision']:.4f} m")
        print(f"  Bias (Mean):     {self.result['bias']:.4f} m")
        print(f"  Valid Count:     {self.result['count']}")
        print(f"  Correlation:     {self.result['corr_coef']:.4f}")
        print(f"{'='*60}\n")

    @staticmethod
    def _format_obs_time_range(time_series):
        """
        从时间序列中提取观测起止时间，返回格式化字符串用于文件名。

        参数
        ----
        time_series : pandas.Series 或 numpy.ndarray
            时间数据，单位为 seconds since 2000-1-1 00:00:00

        返回
        ----
        str
            格式化的时间范围字符串，如 "_20190827_102546_20190905_121613"
            若无法解析则返回空字符串
        """
        try:
            vals = np.array(time_series.dropna() if hasattr(time_series, 'dropna') else time_series)
            vals = vals[np.isfinite(vals)]
            if len(vals) == 0:
                return ""
            t_min = num2date(np.min(vals), units='seconds since 2000-1-1 00:00:00')
            t_max = num2date(np.max(vals), units='seconds since 2000-1-1 00:00:00')
            return "_%s_%s" % (t_min.strftime('%Y%m%d_%H%M%S'), t_max.strftime('%Y%m%d_%H%M%S'))
        except Exception:
            return ""

    def save_XOverPoint(self, savepath_h5=r'./result/h5', csv_path=r'./result/csv'):
        """
        =====================================================================
        保存交叉点数据到多种格式
        =====================================================================

        【参数说明】
        - savepath_h5: HDF5文件保存目录路径
        - csv_path: CSV偏差文件保存目录路径

        【输出格式】
        1. HDF5文件（.h5）：
           - XOver_data_8_YYYYMMDD_HHMMSS_YYYYMMDD_HHMMSS.h5：8点匹配组原始数据
           - XOver_data_1_YYYYMMDD_HHMMSS_YYYYMMDD_HHMMSS.h5：交叉点插值数据（编辑前）
           - XOver_data_1_editing_YYYYMMDD_HHMMSS_YYYYMMDD_HHMMSS.h5：交叉点插值数据（编辑后）
           文件名中的时间范围为匹配数据的观测起止时间
        2. CSV文件：
           - bias_YYYYMMDDHHMMSS.csv：偏差统计结果

        【数据结构】
        - XOver_data1: compareALT交叉点数据
        - XOver_data2: referenceALT交叉点数据
        - XOver_no_editing_ssh1/ssh2: 编辑前SSH数据
        - XOver_editing_ssh1/ssh2: 编辑后SSH数据
        """
        XOver_data1 = self.XoverMatchArray_1
        XOver_data2 = self.XoverMatchArray_2

        # 确保目录存在
        if not os.path.exists(savepath_h5):
            os.makedirs(savepath_h5, exist_ok=True)

        # =============================================================
        # 提取匹配数据的观测起止时间范围，用于文件名
        # =============================================================
        time_col1 = self.var_mapping1.get('time') if hasattr(self, 'var_mapping1') else None
        time_col2 = self.var_mapping2.get('time') if hasattr(self, 'var_mapping2') else None
        time_str = ""
        if time_col1 and time_col1 in XOver_data1.columns:
            time_str = self._format_obs_time_range(XOver_data1[time_col1])
        elif time_col2 and time_col2 in XOver_data2.columns:
            time_str = self._format_obs_time_range(XOver_data2[time_col2])
        if not time_str:
            # 回退：尝试用第5列（time列的默认位置）
            try:
                time_str = self._format_obs_time_range(XOver_data1.iloc[:, 5])
            except Exception:
                time_str = "_%s" % datetime.now().strftime('%Y%m%d')

        # =============================================================
        # 保存8点匹配组数据
        # =============================================================
        H5 = pd.HDFStore(path.join(savepath_h5, 'XOver_data_8%s.h5' % time_str), 'a',
                         complevel=9, complib='zlib')
        H5.put('XOver_data1', XOver_data1)
        H5.put('XOver_data2', XOver_data2)
        H5.close()

        # =============================================================
        # 保存编辑前交叉点数据
        # =============================================================
        XOver_no_editing1 = self.XoverSub1
        XOver_no_editing2 = self.XoverSub2
        XOver_no_editing_ssh1 = self.data1_SSH
        XOver_no_editing_ssh2 = self.data2_SSH
        H5 = pd.HDFStore(path.join(savepath_h5, 'XOver_data_1%s.h5' % time_str), 'a',
                         complevel=9, complib='zlib')
        H5.put('XOver_no_editing1', XOver_no_editing1)
        H5.put('XOver_no_editing2', XOver_no_editing2)
        H5.put('XOver_no_editing_ssh1', XOver_no_editing_ssh1)
        H5.put('XOver_no_editing_ssh2', XOver_no_editing_ssh2)
        H5.close()

        # =============================================================
        # 保存编辑后交叉点数据
        # =============================================================
        XOver_editing1 = self.XoverSub1_valid
        XOver_editing2 = self.XoverSub2_valid
        XOver_editing_ssh1 = self.data1_SSH_valid
        XOver_editing_ssh2 = self.data2_SSH_valid
        H5 = pd.HDFStore(path.join(savepath_h5, 'XOver_data_1_editing%s.h5' % time_str), 'a',
                         complevel=9, complib='zlib')
        H5.put('XOver_editing1', XOver_editing1)
        H5.put('XOver_editing2', XOver_editing2)
        H5.put('XOver_editing_ssh1', XOver_editing_ssh1)
        H5.put('XOver_editing_ssh2', XOver_editing_ssh2)
        H5.close()

        # =============================================================
        # 保存偏差统计CSV
        # =============================================================
        if csv_path and not os.path.exists(csv_path):
            os.makedirs(csv_path, exist_ok=True)

        period_start = np.max([np.min(self.XoverMatchArray_1.iloc[:, 5]), np.min(self.XoverMatchArray_2.iloc[:, 5])])
        period_end = np.min([np.max(self.XoverMatchArray_1.iloc[:, 5]), np.max(self.XoverMatchArray_2.iloc[:, 5])])
        mean_time = np.mean([period_start, period_end])
        out_csv = pd.DataFrame(
            data=[[num2date(mean_time, units='seconds since 2000-1-1 00:00:00'), mean_time, self.result['bias']]])
        bias_path = path.join(csv_path, 'bias_%s.csv' % datetime.now().strftime('%Y%m%d%H%M%S'))
        out_csv.to_csv(bias_path, header=['date', 'time (seconds since 2000-1-1 00:00:00)', 'bias (m)'], index=False,
                       mode='a')
        self.bias_path = bias_path
        print(f"✅ 数据已保存至：{savepath_h5}")

    def cross_plot(self, shift=False, savepath_fig=r'./result/fig', fname=r'./ne_50m_land.shp'):
        """
        =====================================================================
        绘制交叉点结果图
        =====================================================================

        【参数说明】
        - shift: 布尔值，是否对SSH差异进行偏差校正
                True: 绘制 (data1_SSH - data2_SSH - bias)
                False: 绘制 (data1_SSH - data2_SSH)
        - savepath_fig: 图像保存目录
        - fname: 地图背景shapefile文件路径

        【输出图表】
        1. SSH差异地理分布图：
           - 使用Cartopy绘制带地理底图的散点图
           - 颜色映射表示SSH差异大小
           - 中心经度180°（太平洋视角）

        2. SSH差异直方图：
           - 使用Seaborn绘制分布直方图
           - 叠加核密度估计（KDE）
           - 拟合正态分布曲线
           - 显示统计参数（均值、标准差等）

        【可视化设置】
        - 散点大小: 3像素
        - 颜色映射: jet
        - 分辨率: 600 DPI
        - 地理范围: 0-360°经度，-70°至70°纬度
        """
        if not os.path.exists(savepath_fig):
            os.makedirs(savepath_fig, exist_ok=True)

        # 确定绘制数据（是否进行偏差校正）
        if shift:
            ssh = self.data1_SSH_valid - self.data2_SSH_valid - self.result['bias']
        else:
            ssh = self.data1_SSH_valid - self.data2_SSH_valid

        # =============================================================
        # 绘制地理分布图
        # =============================================================
        fig = plt.figure()
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

        # 添加地理底图
        shape_feature = ShapelyFeature(Reader(fname).geometries(), ccrs.PlateCarree(),
                                       edgecolor=None, facecolor='#CCCCCC')
        ax.add_feature(shape_feature)

        # 设置经纬度刻度
        xticks = [0, 60, 120, 180, 240, 300, 360]
        yticks = [-90, -60, -30, 0, 30, 60, 90]
        ax.set_xticks(xticks, crs=ccrs.PlateCarree())
        ax.set_yticks(yticks, crs=ccrs.PlateCarree())
        lon_formatter = LongitudeFormatter(zero_direction_label=True)
        lat_formatter = LatitudeFormatter()
        ax.xaxis.set_major_formatter(lon_formatter)
        ax.yaxis.set_major_formatter(lat_formatter)
        ax.gridlines(draw_labels=False, xlocs=xticks, ylocs=yticks)

        # 绘制散点图
        sc = plt.scatter(self.XoverSub1_valid.iloc[:, 1], self.XoverSub1_valid.iloc[:, 0],
                         s=3, c=ssh, cmap='jet', transform=ccrs.PlateCarree())
        h = plt.colorbar(sc, orientation="horizontal", fraction=0.03, pad=0.05, aspect=50, extend='both')
        h.set_label('units: cm')
        plt.clim(self.result['bias'] - 0.1, self.result['bias'] + 0.1)
        ax.set_extent([0, 359.9, -70, 70], crs=ccrs.PlateCarree())
        fig.set_figheight(7)
        fig.set_figwidth(11)

        # 保存地理分布图
        savepath1 = path.join(savepath_fig, 'SSH_difference_%s.jpg' % datetime.now().strftime('%Y%m%d%H%M%S'))
        self.savepath1 = savepath1
        plt.savefig(savepath1, dpi=600)
        plt.draw()
        plt.close(fig)

        # =============================================================
        # 绘制直方图
        # =============================================================
        fig, ax = plt.subplots()
        sns.set_style('darkgrid')
        dist = DataFrame(ssh, columns=['SSH differences'])
        sns.distplot(dist, fit=stats.norm,
                     hist_kws={'color': 'lightskyblue', 'edgecolor': 'w', 'linewidth': 1, 'linestyle': '--',
                               'alpha': 0.9},
                     kde_kws={'color': 'r', 'linewidth': 2, 'linestyle': '--', 'alpha': 0.9, 'label': 'KDE'},
                     fit_kws={'color': 'g', 'linewidth': 2, 'linestyle': '--', 'alpha': 0.9, 'label': 'normal fit'},
                     label='SSH differences')
        plt.legend()
        plt.xlabel('units: m')
        savepath2 = path.join(savepath_fig, 'SSH_histogram_%s.jpg' % datetime.now().strftime('%Y%m%d%H%M%S'))
        self.savepath2 = savepath2
        plt.savefig(savepath2, dpi=600)
        plt.draw()
        plt.close(fig)

        print(f"✅ 图表已保存至：{savepath_fig}")

    def analyze_metocean_spatial_temporal(self, json_data):
        """
        =====================================================================
        海洋气象参数时空分析（含质量控制与报告模板参数计算）
        =====================================================================

        【参数说明】
        - json_data: dict，完整配置文件数据

        【功能说明】
        对海洋气象参数（风速、有效波高、后向散射系数）进行精细化的
        时空分布和统计分析，支持多个时间窗口的对比分析。
        同时计算质量控制剔除率和报告模板所需的全部参数。

        【分析参数】
        - Wind Speed (风速): 有效范围 0-30 m/s
        - SWH (有效波高): 有效范围 0-12 m
        - Sigma0 (后向散射系数): 有效范围 5-30 dB

        【时间窗口】
        - 累积窗口: 0-2h, 0-3h, 0-6h, 0-12h
        - 单独窗口: 2h, 3h, 6h

        【输出内容】
        1. 累积时间窗口图（每个参数）：
           - 散点图（按时间窗口着色）
           - KDE分布图
           - 纬度依赖性图
           - 时间窗口影响曲线

        2. 单独时间窗口图（每个参数×每个窗口）：
           - 地理分布图
           - 散点图（回归直线 + 标准公式）
           - 直方图（Bias/STD/RMSE）

        3. 统计表格（CSV和Excel）：
           - 各参数各时间窗口的统计指标
           - 完整的差异数据记录

        4. 报告模板参数（存储于 self.report_params）：
           - 每个参数的 aft_num, aft_bias, aft_std, coef
           - 质量控制剔除率 percent01~percent06

        【设计特点】
        - 支持双卫星独立变量配置
        - 绘图顺序优化（避免遮挡）
        - 颜色对比鲜明
        - 完整的公式标注
        """
        import os
        from datetime import datetime
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        import seaborn as sns

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 开始进行精细化时空分布与统计分析...")

        # =============================================================
        # 配置解析
        # =============================================================
        fig_dir = json_data['path'][0]['savepath_fig']
        csv_dir = json_data['path'][0]['csv_path']
        os.makedirs(fig_dir, exist_ok=True)
        os.makedirs(csv_dir, exist_ok=True)

        sat1_name = json_data.get('referenceALT', 'REF')
        sat2_name = json_data.get('compareALT', 'CMP')

        sns.set_theme(style="whitegrid", font_scale=1.05)

        # 分析目标参数配置
        targets = {
            'Wind Speed': {
                'range': (0.0, 40.0),
                'diff_name': 'wind_speed_diff',
                'fig_name': 'Wind_Speed'
            },
            'SWH': {
                'range': (0.0, 15.0),
                'diff_name': 'swh_diff',
                'fig_name': 'SWH'
            },
            'Sigma0': {
                'range': (5.0, 30.0),
                'diff_name': 'sigma0_diff',
                'fig_name': 'Sigma0'
            }
        }

        # =============================================================
        # 数据检查
        # =============================================================
        if not hasattr(self, 'XoverSub1') or not hasattr(self, 'XoverSub2'):
            print("⚠️ 未找到交叉点数据：self.XoverSub1 / self.XoverSub2")
            return

        df1 = self.XoverSub1
        df2 = self.XoverSub2

        if df1 is None or df2 is None:
            print("⚠️ 交叉点数据为空")
            return

        # 数据类型标准化
        if isinstance(df1, pd.Series):
            df1 = df1.to_frame().T
        if isinstance(df2, pd.Series):
            df2 = df2.to_frame().T
        if not isinstance(df1, pd.DataFrame):
            df1 = pd.DataFrame(df1)
        if not isinstance(df2, pd.DataFrame):
            df2 = pd.DataFrame(df2)

        if df1.empty or df2.empty:
            print("⚠️ 交叉点数据为空")
            return

        # =============================================================
        # 变量名获取
        # =============================================================
        vm1 = getattr(self, 'var_mapping1', {})
        vm2 = getattr(self, 'var_mapping2', {})

        lat_col1 = vm1.get('lat')
        lon_col1 = vm1.get('lon')
        time_col1 = vm1.get('time')

        lat_col2 = vm2.get('lat')
        lon_col2 = vm2.get('lon')
        time_col2 = vm2.get('time')

        swh_col1 = vm1.get('swh')
        sig0_col1 = vm1.get('sig0')
        wind_col1 = vm1.get('wind_speed')

        swh_col2 = vm2.get('swh')
        sig0_col2 = vm2.get('sig0')
        wind_col2 = vm2.get('wind_speed')

        # 额外变量（用于质量控制）
        depth_col1 = vm1.get('depth')
        depth_col2 = vm2.get('depth')
        dist_col1 = vm1.get('distance')
        dist_col2 = vm2.get('distance')

        # =============================================================
        # 辅助函数定义
        # =============================================================
        def _exist_col(df, col):
            """检查列是否存在"""
            return col is not None and col in df.columns

        def _calc_stats(v1, v2):
            """
            计算统计指标
            返回: bias, std, rmse, corr, diff
            """
            diff = v2 - v1
            bias = np.nanmean(diff)
            std = np.nanstd(diff, ddof=1) if len(diff) > 1 else np.nan
            rmse = np.sqrt(np.nanmean(diff ** 2))
            corr = np.corrcoef(v1, v2)[0, 1] if len(v1) > 1 else np.nan
            return bias, std, rmse, corr, diff

        def _linear_regression(v1, v2):
            """
            线性回归计算
            返回: slope, intercept, r, r2
            """
            if len(v1) < 2:
                return np.nan, np.nan, np.nan, np.nan
            try:
                slope, intercept = np.polyfit(v1, v2, 1)
                r = np.corrcoef(v1, v2)[0, 1]
                r2 = r ** 2 if np.isfinite(r) else np.nan
                return slope, intercept, r, r2
            except Exception:
                return np.nan, np.nan, np.nan, np.nan

        def _format_equation(slope, intercept, r2):
            """
            格式化回归方程字符串
            格式: y = ax + b, R² = value
            """
            if np.isnan(slope) or np.isnan(intercept):
                return "y = NaNx + NaN\nR² = NaN"

            sign = "+" if intercept >= 0 else "-"
            return f"y = {slope:.4f}x {sign} {abs(intercept):.4f}\nR² = {r2:.4f}"

        def _save_single_window_plot(df_plot, var_name, fig_name, label_window):
            """
            绘制单独时间窗口分析图

            布局结构：
            - 第一行：地理分布图
            - 第二行左：散点图（回归线 + 方程）
            - 第二行右：直方图（Bias/STD/RMSE）
            """
            if df_plot is None or df_plot.empty or len(df_plot) < 5:
                print(f"[{var_name}-{label_window}] ⚠️ 有效点过少({0 if df_plot is None else len(df_plot)}), 跳过单独作图。")
                return

            # 提取数据
            v1 = df_plot['v1'].to_numpy()
            v2 = df_plot['v2'].to_numpy()
            lat = df_plot['latitude'].to_numpy()
            lon = df_plot['longitude'].to_numpy()
            dt = df_plot['time_diff_hours'].to_numpy()
            diff = df_plot['bias'].to_numpy()

            # 计算统计量
            bias_val, std_val, rmse_val, corr_val, _ = _calc_stats(v1, v2)
            slope, intercept, r_reg, r2 = _linear_regression(v1, v2)

            # 创建图表
            fig = plt.figure(figsize=(16, 10))
            gs = fig.add_gridspec(2, 2, height_ratios=[1.05, 1.0], hspace=0.28, wspace=0.22)

            ax_map = fig.add_subplot(gs[0, :])
            ax_scatter = fig.add_subplot(gs[1, 0])
            ax_hist = fig.add_subplot(gs[1, 1])

            # 地理分布图
            diff_mean = np.nanmean(diff)
            diff_std = np.nanstd(diff, ddof=1) if len(diff) > 1 else np.nan

            # 颜色范围：mean-std ~ mean+std
            if np.isfinite(diff_mean) and np.isfinite(diff_std) and diff_std > 0:
                vmin_map = diff_mean - diff_std
                vmax_map = diff_mean + diff_std
            else:
                vmax_abs = np.nanmax(np.abs(diff)) if len(diff) > 0 else 1.0
                if not np.isfinite(vmax_abs) or vmax_abs == 0:
                    vmax_abs = 1.0
                vmin_map, vmax_map = -vmax_abs, vmax_abs

            sc_map = ax_map.scatter(lon, lat, c=diff, s=24, cmap='coolwarm',
                                    vmin=vmin_map, vmax=vmax_map, alpha=0.88, edgecolors='none')
            ax_map.set_title(f'{var_name} Difference Geographic Distribution ({label_window})', fontweight='bold')
            ax_map.set_xlabel('Longitude')
            ax_map.set_ylabel('Latitude')
            ax_map.grid(True, linestyle='--', alpha=0.35)
            cbar = plt.colorbar(sc_map, ax=ax_map, pad=0.01)
            cbar.set_label(f'{sat2_name} - {sat1_name}')

            # 地图统计信息
            text_map = (f'N = {len(diff)}   Bias = {bias_val:.4f}   STD = {std_val:.4f}   '
                       f'RMSE = {rmse_val:.4f}   Corr = {corr_val:.4f}')
            ax_map.text(0.01, 0.02, text_map, transform=ax_map.transAxes,
                       ha='left', va='bottom', fontsize=10.5,
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.88, edgecolor='gray'))

            # 散点图
            sc = ax_scatter.scatter(v1, v2, c=dt, cmap='viridis', s=26,
                                   alpha=0.82, edgecolors='none')
            vmin_sc = np.nanmin([np.nanmin(v1), np.nanmin(v2)])
            vmax_sc = np.nanmax([np.nanmax(v1), np.nanmax(v2)])

            if np.isfinite(vmin_sc) and np.isfinite(vmax_sc):
                ax_scatter.plot([vmin_sc, vmax_sc], [vmin_sc, vmax_sc], 'k--', lw=1.4, label='1:1 line')
                if np.isfinite(slope) and np.isfinite(intercept):
                    xfit = np.linspace(vmin_sc, vmax_sc, 300)
                    yfit = slope * xfit + intercept
                    ax_scatter.plot(xfit, yfit, color='red', lw=2.1, label='Regression line')

            ax_scatter.set_xlabel(f'{sat1_name}')
            ax_scatter.set_ylabel(f'{sat2_name}')
            ax_scatter.set_title(f'{var_name} Scatter Plot ({label_window})', fontweight='bold')
            ax_scatter.grid(True, linestyle='--', alpha=0.35)
            ax_scatter.legend(loc='lower right')

            # 散点图统计信息
            eq_text = _format_equation(slope, intercept, r2)
            stat_text = (f'{eq_text}\nN = {len(v1)}\nBias = {bias_val:.4f}\nRMSE = {rmse_val:.4f}')
            ax_scatter.text(0.03, 0.97, stat_text, transform=ax_scatter.transAxes,
                           ha='left', va='top', fontsize=10.5,
                           bbox=dict(boxstyle='round', facecolor='white', alpha=0.90, edgecolor='gray'))
            cbar_sc = plt.colorbar(sc, ax=ax_scatter, pad=0.01)
            cbar_sc.set_label('Time Difference (hours)')

            # 直方图
            sns.histplot(diff, bins=40, kde=True, ax=ax_hist, color='steelblue',
                        stat='density', alpha=0.72)
            ax_hist.axvline(0, color='black', ls='--', lw=1.2, label='Zero line')
            if np.isfinite(bias_val):
                ax_hist.axvline(bias_val, color='red', ls='-', lw=1.8, label=f'Bias = {bias_val:.4f}')
            if np.isfinite(std_val) and np.isfinite(bias_val):
                ax_hist.axvline(bias_val + std_val, color='darkorange', ls='--', lw=1.5,
                               label=f'+1 STD = {std_val:.4f}')
                ax_hist.axvline(bias_val - std_val, color='darkorange', ls='--', lw=1.5,
                               label=f'-1 STD = {std_val:.4f}')

            ax_hist.set_title(f'{var_name} Histogram ({sat2_name} - {sat1_name}, {label_window})',
                             fontweight='bold')
            ax_hist.set_xlabel('Difference')
            ax_hist.set_ylabel('Density')
            ax_hist.grid(True, linestyle='--', alpha=0.35)

            hist_text = (f'N = {len(diff)}\nBias = {bias_val:.4f}\nSTD = {std_val:.4f}\n'
                        f'RMSE = {rmse_val:.4f}\nCorr = {corr_val:.4f}')
            ax_hist.text(0.97, 0.97, hist_text, transform=ax_hist.transAxes,
                        ha='right', va='top', fontsize=10.5,
                        bbox=dict(boxstyle='round', facecolor='white', alpha=0.90, edgecolor='gray'))
            ax_hist.legend(loc='upper left')

            plt.suptitle(f'{sat1_name} vs {sat2_name} - {var_name} - {label_window}',
                        fontsize=16, fontweight='bold', y=0.98)
            plt.tight_layout(rect=[0, 0, 1, 0.965])

            # 保存图表
            out_path = os.path.join(fig_dir, f'Analysis_{sat1_name}_vs_{sat2_name}_{fig_name}_{label_window}.png')
            plt.savefig(out_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功导出单独时间窗分析图：{out_path}")

        # =============================================================
        # 质量控制剔除率计算函数
        # =============================================================
        def _compute_quality_control_stats(ssh_diff_arr, lat_arr, depth_arr, time_diff_arr,
                                            distance_arr=None, param_values_arr=None,
                                            config=None, param_type='sigma0'):
            """
            计算质量控制剔除率统计（配置驱动，无硬编码阈值）。

            ─────────────────────────────────────────────────────────────
            处理流程（两阶段筛选）：
            ─────────────────────────────────────────────────────────────

            阶段一：时间窗口预筛选
                从 config['processing_params']['analysis_time_window_hours'] 读取
                时间窗口（默认 2 小时），仅保留 |time_diff| <= window_hours
                的数据点，作为后续所有质控计算的基准数据集。

            阶段二：在时间窗口数据集上逐条件计算通过率
                从 config['quality_control'][param_type] 读取所有阈值，
                逐条件计算通过该条件的数据点占比（相对于阶段一的总数）：
                  - percent01  纬度范围通过率      [lat_min, lat_max]
                  - percent02  离岸距离通过率      > distance_min
                  - percent03  水深范围通过率      |depth| > depth_min
                  - percent04  sigma0/swh/wind范围  [param_min, param_max]
                  - percent05  粗大误差通过率      |diff - mean| < threshold
                  - percent06  全部条件联合通过率  (01 & 02 & 03 & 04 & 05)

            ─────────────────────────────────────────────────────────────
            参数说明：
            ─────────────────────────────────────────────────────────────
                ssh_diff_arr      np.ndarray  参数差异数组（如 sig0_diff, swh_diff, ws_diff）
                lat_arr           np.ndarray  纬度数组（单位：度）
                depth_arr         np.ndarray  水深数组（单位：米，负值表示水下）
                time_diff_arr     np.ndarray  时间差异数组（单位：小时），即两颗卫星观测时间之差
                distance_arr      np.ndarray  离岸距离数组（单位：米），可选，缺省时跳过离岸距离筛选
                param_values_arr  np.ndarray  参数原始值数组（两颗卫星均值），用于 percent04 范围筛选
                config            dict        完整配置字典
                param_type        str         配置键名，可选值: 'sigma0' | 'swh' | 'wind'

            ─────────────────────────────────────────────────────────────
            返回值：
            ─────────────────────────────────────────────────────────────
                dict: {
                    'percent01': float,   # 纬度范围通过率
                    'percent02': float,   # 离岸距离通过率
                    'percent03': float,   # 水深范围通过率
                    'percent04': float,   # 参数值范围通过率 (sigma0/swh/wind)
                    'percent05': float,   # 粗大误差通过率
                    'percent06': float,   # 全部条件联合通过率
                    'n_total':   int,     # 原始数据总点数
                    'n_2h':      int,     # 2小时时间窗口内的点数
                }

            ─────────────────────────────────────────────────────────────
            配置字典结构示例 (config['quality_control']['sigma0'])：
            ─────────────────────────────────────────────────────────────
                {
                    "lat_min": -60.0,               # 纬度下限（度）
                    "lat_max": 60.0,                # 纬度上限（度）
                    "distance_min": 50000.0,        # 最小离岸距离（米）
                    "depth_min": 1000.0,            # 最小水深绝对值（米）
                    "param_min": 5.0,               # 参数下限 (sigma0: 5dB, swh: 0m, wind: 2m/s)
                    "param_max": 30.0,              # 参数上限 (sigma0: 30dB, swh: 15m, wind: 40m/s)
                    "gross_error_threshold": 1.5    # 粗大误差阈值（与均值的偏差）
                }
            """

            # ================================================================
            # 第一步：从配置中读取阈值参数
            # ================================================================
            qc_config = (config or {}).get('quality_control', {}).get(param_type, {})

            lat_min               = qc_config.get('lat_min', -60.0)
            lat_max               = qc_config.get('lat_max', 60.0)
            distance_min          = qc_config.get('distance_min', 50000.0)   # 单位：米
            depth_min             = qc_config.get('depth_min', 1000.0)       # 单位：米
            param_min             = qc_config.get('param_min', 0.0)
            param_max             = qc_config.get('param_max', 1e9)
            gross_error_threshold = qc_config.get('gross_error_threshold', 1.5)

            proc_params = (config or {}).get('processing_params', {})
            window_hours = proc_params.get('analysis_time_window_hours', 2)

            # ================================================================
            # 第二步：对齐所有输入数组到统一长度，防止越界
            # ================================================================
            array_lengths = [len(lat_arr)]
            if ssh_diff_arr is not None:
                array_lengths.append(len(ssh_diff_arr))
            if time_diff_arr is not None:
                array_lengths.append(len(time_diff_arr))
            if depth_arr is not None:
                array_lengths.append(len(depth_arr))
            if distance_arr is not None:
                array_lengths.append(len(distance_arr))
            if param_values_arr is not None:
                array_lengths.append(len(param_values_arr))

            n_total = min(array_lengths) if array_lengths else 0

            if n_total == 0:
                return {
                    'percent01': 0.0, 'percent02': 0.0, 'percent03': 0.0,
                    'percent04': 0.0, 'percent05': 0.0, 'percent06': 0.0,
                    'n_total': 0, 'n_2h': 0
                }

            # ================================================================
            # 第三步：计算2小时以内的子集（核心！后续所有质控以此为基准）
            # ================================================================
            # 计算两颗卫星的时间差（小时），取绝对值兼容正负差
            time_diff_hours = np.abs(time_diff_arr[:n_total])

            # 构建时间窗口掩码：|time_diff| <= window_hours
            mask_2h = time_diff_hours <= window_hours
            n_2h = int(np.sum(mask_2h))

            print(f"    [{param_type}] 原始数据共 {n_total} 个，"
                  f"时间差≤{window_hours}h 的点共 {n_2h} 个")

            if n_2h == 0:
                return {
                    'percent01': 0.0, 'percent02': 0.0, 'percent03': 0.0,
                    'percent04': 0.0, 'percent05': 0.0, 'percent06': 0.0,
                    'n_total': n_total, 'n_2h': 0
                }

            # ================================================================
            # 第四步：在2h子集上，逐条件计算通过率
            # ================================================================
            # 辅助：从全量数组中提取2h子集
            def _sub(arr):
                """截取到 n_total 长度后，用 mask_2h 筛选2h子集。"""
                if arr is None:
                    return None
                return arr[:n_total][mask_2h]

            # ────────────────────────────────────────────────────────────────
            # 条件1：纬度范围  lat_min <= lat <= lat_max
            # ────────────────────────────────────────────────────────────────
            lat_sub = _sub(lat_arr)
            mask_lat = (lat_sub >= lat_min) & (lat_sub <= lat_max)
            ratio_lat = mask_lat.sum() / n_2h
            print(f"      percent01 纬度 [{lat_min}, {lat_max}°]: "
                  f"{mask_lat.sum()}/{n_2h} = {ratio_lat:.4f}")

            # ────────────────────────────────────────────────────────────────
            # 条件2：离岸距离  distance > distance_min
            # ────────────────────────────────────────────────────────────────
            dist_sub = _sub(distance_arr)
            if dist_sub is not None and len(dist_sub) == n_2h:
                mask_dist = dist_sub > distance_min
            else:
                mask_dist = np.ones(n_2h, dtype=bool)
            ratio_dist = mask_dist.sum() / n_2h
            print(f"      percent02 离岸距离 > {distance_min/1000:.0f}km: "
                  f"{mask_dist.sum()}/{n_2h} = {ratio_dist:.4f}")

            # ────────────────────────────────────────────────────────────────
            # 条件3：水深范围  |depth| > depth_min
            # ────────────────────────────────────────────────────────────────
            depth_sub = _sub(depth_arr)
            if depth_sub is not None and len(depth_sub) == n_2h:
                mask_depth = np.abs(depth_sub) > depth_min
            else:
                mask_depth = np.ones(n_2h, dtype=bool)
            ratio_depth = mask_depth.sum() / n_2h
            print(f"      percent03 水深 |z| > {depth_min:.0f}m: "
                  f"{mask_depth.sum()}/{n_2h} = {ratio_depth:.4f}")

            # ────────────────────────────────────────────────────────────────
            # 条件4：参数值范围  param_min <= param_value <= param_max
            #   sigma0: [5, 30] dB
            #   swh:    [0, 15] m
            #   wind:   [2, 40] m/s
            # ────────────────────────────────────────────────────────────────
            pval_sub = _sub(param_values_arr)
            if pval_sub is not None and len(pval_sub) == n_2h:
                mask_param = (pval_sub >= param_min) & (pval_sub <= param_max)
            else:
                mask_param = np.ones(n_2h, dtype=bool)
            ratio_param = mask_param.sum() / n_2h
            print(f"      percent04 {param_type} [{param_min}, {param_max}]: "
                  f"{mask_param.sum()}/{n_2h} = {ratio_param:.4f}")

            # ────────────────────────────────────────────────────────────────
            # 条件5：粗大误差  |diff - mean(diff)| < gross_error_threshold
            # ────────────────────────────────────────────────────────────────
            diff_sub = _sub(ssh_diff_arr)
            if diff_sub is not None and len(diff_sub) == n_2h:
                valid_diffs = diff_sub[np.isfinite(diff_sub)]
                if len(valid_diffs) > 0:
                    diff_mean = np.nanmean(valid_diffs)
                    mask_gross = np.abs(diff_sub - diff_mean) < gross_error_threshold
                else:
                    mask_gross = np.ones(n_2h, dtype=bool)
            else:
                mask_gross = np.ones(n_2h, dtype=bool)
            ratio_gross = mask_gross.sum() / n_2h
            print(f"      percent05 粗大误差 |diff-mean| < {gross_error_threshold}: "
                  f"{mask_gross.sum()}/{n_2h} = {ratio_gross:.4f}")

            # ────────────────────────────────────────────────────────────────
            # 条件6：全部条件联合（交集）
            # ────────────────────────────────────────────────────────────────
            mask_all = mask_lat & mask_dist & mask_depth & mask_param & mask_gross
            ratio_all = mask_all.sum() / n_2h
            print(f"      percent06 全部联合通过: "
                  f"{mask_all.sum()}/{n_2h} = {ratio_all:.4f}")

            # ================================================================
            # 第五步：返回结果
            # ================================================================
            return {
                'percent01': float(ratio_lat),     # 纬度范围通过率
                'percent02': float(ratio_dist),    # 离岸距离通过率
                'percent03': float(ratio_depth),   # 水深范围通过率
                'percent04': float(ratio_param),   # 参数值范围通过率
                'percent05': float(ratio_gross),   # 粗大误差通过率
                'percent06': float(ratio_all),     # 全部条件联合通过率
                'n_total':   n_total,              # 原始数据总点数
                'n_2h':      n_2h,                 # 2h 时间窗口内点数
            }

        def _get_param_stats(stats_df, variable_name):
            """从统计 DataFrame 中提取 0-2h 窗口的指标"""
            if stats_df is None or stats_df.empty or 'Variable' not in stats_df.columns:
                return {'count': 0, 'bias': np.nan, 'std': np.nan, 'rmse': np.nan, 'corr': np.nan}
            row = stats_df[(stats_df['Variable'] == variable_name) & (stats_df['Time_Window'] == '0-2h')]
            if row.empty:
                return {'count': 0, 'bias': np.nan, 'std': np.nan, 'rmse': np.nan, 'corr': np.nan}
            r = row.iloc[0]
            return {'count': int(r['Count']), 'bias': r['Bias'], 'std': r['STD'],
                    'rmse': r['RMSE'], 'corr': r['Corr']}

        # =============================================================
        # 统一长度和数据准备
        # =============================================================
        if not _exist_col(df1, lat_col1) or not _exist_col(df1, lon_col1):
            print(f"⚠️ 缺少位置列：lat={lat_col1}, lon={lon_col1}")
            return
        if not _exist_col(df1, time_col1) or not _exist_col(df2, time_col2):
            print(f"⚠️ 缺少时间列：sat1={time_col1}, sat2={time_col2}")
            return

        n = min(len(df1), len(df2))
        df1 = df1.iloc[:n].copy()
        df2 = df2.iloc[:n].copy()

        lat_all = pd.to_numeric(df1[lat_col1], errors='coerce').to_numpy()
        lon_all = pd.to_numeric(df1[lon_col1], errors='coerce').to_numpy()
        lon_all = np.where(lon_all > 180, lon_all - 360, lon_all)

        time1_all = pd.to_numeric(df1[time_col1], errors='coerce').to_numpy()
        time2_all = pd.to_numeric(df2[time_col2], errors='coerce').to_numpy()
        dt_hours_all = np.abs(time2_all - time1_all) / 3600.0

        # =============================================================
        # 统计分析报表头
        # =============================================================
        print("\n" + "=" * 100)
        print(f"{'海洋气象参数差异分析':^100}")
        print(f"{'卫星对比':^50} {sat2_name} vs {sat1_name}")
        print("=" * 100)
        print(f"{'参数':<20} {'时间窗口':<12} {'有效点数':>10} {'Bias':>12} {'STD':>12} {'RMSE':>12} {'Corr':>10}")
        print("-" * 100)

        stats_results = []
        diff_data_all = []
        qc_data = {}  # 质量控制数据收集

        # 时间窗口配置
        cum_windows = [2, 3, 6, 12]
        cum_labels = [f'0-{h}h' for h in cum_windows]
        extra_windows = [2, 3, 6]

        # 绘图顺序配置
        plot_order = ['0-12h', '0-6h', '0-3h', '0-2h']

        # 颜色配置
        color_map_cum = {
            '0-12h': '#4C78A8',
            '0-6h': '#F58518',
            '0-3h': '#54A24B',
            '0-2h': '#E45756'
        }

        # =============================================================
        # 逐参数分析
        # =============================================================
        for var_name, config in targets.items():
            # 确定变量列名
            if var_name == 'Wind Speed':
                col1, col2 = wind_col1, wind_col2
            elif var_name == 'SWH':
                col1, col2 = swh_col1, swh_col2
            elif var_name == 'Sigma0':
                col1, col2 = sig0_col1, sig0_col2
            else:
                continue

            if not _exist_col(df1, col1) or not _exist_col(df2, col2):
                print(f"[{var_name}] ⚠️ 列不存在，跳过。sat1={col1}, sat2={col2}")
                continue

            v_min, v_max = config['range']
            diff_name = config['diff_name']
            fig_name = config['fig_name']

            # 读取变量数据
            v1_all = pd.to_numeric(df1[col1], errors='coerce').to_numpy()
            v2_all = pd.to_numeric(df2[col2], errors='coerce').to_numpy()

            # 有效数据筛选
            valid_idx = (
                    np.isfinite(v1_all) &
                    np.isfinite(v2_all) &
                    np.isfinite(lat_all) &
                    np.isfinite(lon_all) &
                    np.isfinite(dt_hours_all) &
                    (v1_all >= v_min) & (v1_all <= v_max) &
                    (v2_all >= v_min) & (v2_all <= v_max) &
                    (dt_hours_all <= 12)
            )

            v1 = v1_all[valid_idx]
            v2 = v2_all[valid_idx]
            lat = lat_all[valid_idx]
            lon = lon_all[valid_idx]
            dt = dt_hours_all[valid_idx]
            bias = v2 - v1

            if len(bias) < 10:
                print(f"[{var_name}] ⚠️ 12h内有效点过少 ({len(bias)}), 跳过。")
                continue

            # 收集质量控制所需数据
            qc_data[var_name] = {
                'diff': bias.copy(),
                'lat': lat.copy(),
                'lon': lon.copy(),
                'dt': dt.copy(),
                'v1': v1.copy(),  # 当前参数的 compareALT 原始值
                'v2': v2.copy(),  # 当前参数的 referenceALT 原始值
                'depth': pd.to_numeric(
                    df1.loc[df1.index[valid_idx], depth_col1], errors='coerce'
                ).to_numpy() if _exist_col(df1, depth_col1) else None,
                'distance': pd.to_numeric(
                    df1.loc[df1.index[valid_idx], dist_col1], errors='coerce'
                ).to_numpy() if _exist_col(df1, dist_col1) else (
                    pd.to_numeric(df2.loc[df2.index[valid_idx], dist_col2], errors='coerce').to_numpy()
                    if _exist_col(df2, dist_col2) else None
                ),
                'wind_speed': pd.to_numeric(
                    df1.loc[df1.index[valid_idx], wind_col1], errors='coerce'
                ).to_numpy() if _exist_col(df1, wind_col1) else None,
                'swh': pd.to_numeric(
                    df1.loc[df1.index[valid_idx], swh_col1], errors='coerce'
                ).to_numpy() if _exist_col(df1, swh_col1) else None,
            }

            # 保存所有差异数据
            for i in range(len(bias)):
                diff_data_all.append({
                    'Variable': var_name,
                    'latitude': lat[i],
                    'longitude': lon[i],
                    'time_diff_hours': dt[i],
                    f'{var_name.replace(" ", "_")}_{sat1_name}': v1[i],
                    f'{var_name.replace(" ", "_")}_{sat2_name}': v2[i],
                    diff_name: bias[i]
                })

            # =====================================================
            # 累积时间窗口分析
            # =====================================================
            plot_data_list = []
            stats_summary_for_plot = []

            for limit, label in zip(cum_windows, cum_labels):
                mask = dt <= limit
                if np.sum(mask) > 5:
                    v1_sub = v1[mask]
                    v2_sub = v2[mask]
                    lat_sub = lat[mask]
                    dt_sub = dt[mask]
                    bias_val, std_val, rmse_val, corr_val, bias_sub = _calc_stats(v1_sub, v2_sub)

                    stats_results.append({
                        'Variable': var_name,
                        'Time_Window': label,
                        'Count': len(v1_sub),
                        'Bias': bias_val,
                        'STD': std_val,
                        'RMSE': rmse_val,
                        'Corr': corr_val
                    })

                    print(f"{var_name:<20} {label:<12} {len(v1_sub):>10d} {bias_val:>12.4f} "
                          f"{std_val:>12.4f} {rmse_val:>12.4f} {corr_val:>10.4f}")

                    plot_data_list.append(pd.DataFrame({
                        'v1': v1_sub, 'v2': v2_sub, 'lat': lat_sub,
                        'dt': dt_sub, 'bias': bias_sub, 'window': label
                    }))
                    stats_summary_for_plot.append((label, len(v1_sub), bias_val, std_val, rmse_val, corr_val))

            # =====================================================
            # 绘制累积时间窗口图
            # =====================================================
            if len(plot_data_list) > 0:
                plot_df = pd.concat(plot_data_list, ignore_index=True)
                fig, axes = plt.subplots(2, 2, figsize=(18, 12))
                ax_scatter, ax_hist, ax_lat, ax_time = axes.flatten()

                # 散点图（按时间窗口着色）
                for label in plot_order:
                    sub = plot_df[plot_df['window'] == label]
                    if len(sub) == 0:
                        continue

                    # 窗口越小，点越大、越不透明
                    if label == '0-12h':
                        s_val, a_val = 8, 0.30
                    elif label == '0-6h':
                        s_val, a_val = 12, 0.45
                    elif label == '0-3h':
                        s_val, a_val = 16, 0.60
                    else:
                        s_val, a_val = 20, 0.80

                    ax_scatter.scatter(sub['v1'], sub['v2'], s=s_val, alpha=a_val,
                                      color=color_map_cum[label], label=label, edgecolors='none')

                vmin_sc = np.nanmin([plot_df['v1'].min(), plot_df['v2'].min()])
                vmax_sc = np.nanmax([plot_df['v1'].max(), plot_df['v2'].max()])
                if np.isfinite(vmin_sc) and np.isfinite(vmax_sc):
                    ax_scatter.plot([vmin_sc, vmax_sc], [vmin_sc, vmax_sc], 'k--', lw=1.5, label='1:1 line')

                ax_scatter.set_xlabel(f'{sat1_name}')
                ax_scatter.set_ylabel(f'{sat2_name}')
                ax_scatter.set_title(f'{var_name}: Scatter by Cumulative Time Window')
                ax_scatter.grid(True, linestyle='--', alpha=0.35)
                ax_scatter.legend(loc='best')

                # KDE图
                for label in plot_order:
                    sub = plot_df[plot_df['window'] == label]
                    if len(sub) == 0:
                        continue
                    sns.kdeplot(sub['bias'], ax=ax_hist, label=label, lw=2.2,
                              color=color_map_cum[label], fill=False)

                ax_hist.axvline(0, color='black', ls='--', lw=1.2)
                ax_hist.set_title(f'{var_name}: Difference KDE ({sat2_name} - {sat1_name})')
                ax_hist.set_xlabel('Difference')
                ax_hist.grid(True, linestyle='--', alpha=0.35)
                ax_hist.legend(loc='best')

                # 纬度依赖性
                for label in plot_order:
                    sub = plot_df[plot_df['window'] == label]
                    if len(sub) == 0:
                        continue

                    if label == '0-12h':
                        s_val, a_val = 12, 0.25
                    elif label == '0-6h':
                        s_val, a_val = 16, 0.40
                    elif label == '0-3h':
                        s_val, a_val = 20, 0.55
                    else:
                        s_val, a_val = 24, 0.75

                    ax_lat.scatter(sub['lat'], sub['bias'], s=s_val, alpha=a_val,
                                  color=color_map_cum[label], label=label, edgecolors='none')

                ax_lat.axhline(0, color='black', ls='--', lw=1.2)
                ax_lat.set_title('Latitude Dependence of Bias')
                ax_lat.set_xlabel('Latitude')
                ax_lat.set_ylabel('Bias')
                ax_lat.grid(True, linestyle='--', alpha=0.35)
                ax_lat.legend(loc='best')

                # 时间窗口影响曲线
                stats_summary_for_plot_sorted = sorted(stats_summary_for_plot,
                                                       key=lambda x: ['0-2h', '0-3h', '0-6h', '0-12h'].index(x[0]))

                x = np.arange(len(stats_summary_for_plot_sorted))
                labels = [s[0] for s in stats_summary_for_plot_sorted]
                bias_vals = [s[2] for s in stats_summary_for_plot_sorted]
                std_vals = [s[3] for s in stats_summary_for_plot_sorted]
                rmse_vals = [s[4] for s in stats_summary_for_plot_sorted]

                ax_time.plot(x, bias_vals, marker='o', lw=2.2, label='Bias', color='royalblue')
                ax_time.plot(x, std_vals, marker='s', lw=2.2, label='STD', color='darkorange')
                ax_time.plot(x, rmse_vals, marker='^', lw=2.2, label='RMSE', color='seagreen')

                for xi, item in enumerate(stats_summary_for_plot_sorted):
                    label_i, count_i, bias_i, std_i, rmse_i, corr_i = item
                    ax_time.text(xi, bias_i, f'N={count_i}\nR={corr_i:.3f}',
                                ha='center', va='bottom', color='navy', fontweight='bold', fontsize=10)

                ax_time.axhline(0, color='black', ls='--', lw=1.4)
                ax_time.set_xticks(x)
                ax_time.set_xticklabels(labels)
                ax_time.set_title('Impact of Time Window Selection')
                ax_time.set_xlabel('Time Window Configuration')
                ax_time.set_ylabel('Metric Value')
                ax_time.grid(True, linestyle='--', alpha=0.35)
                ax_time.legend(loc='best')

                plt.suptitle(f'{sat1_name} vs {sat2_name} - {var_name}', fontsize=16, fontweight='bold')
                plt.tight_layout(rect=[0, 0, 1, 0.96])

                fig_path = os.path.join(fig_dir, f'Analysis_{sat1_name}_vs_{sat2_name}_{fig_name}.png')
                plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                plt.close()
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 成功导出分析图：{fig_path}")

            # =====================================================
            # 单独时间窗口图（2h, 3h, 6h）
            # =====================================================
            for wh in extra_windows:
                mask_single = dt <= wh
                if np.sum(mask_single) <= 5:
                    print(f"[{var_name}-{wh}h] ⚠️ 有效点过少({np.sum(mask_single)}), 跳过单独时间窗图。")
                    continue

                df_single = pd.DataFrame({
                    'v1': v1[mask_single],
                    'v2': v2[mask_single],
                    'latitude': lat[mask_single],
                    'longitude': lon[mask_single],
                    'time_diff_hours': dt[mask_single],
                    'bias': bias[mask_single]
                })

                _save_single_window_plot(
                    df_plot=df_single,
                    var_name=var_name,
                    fig_name=fig_name,
                    label_window=f'{wh}h'
                )

        # =============================================================
        # 统计分析结束
        # =============================================================
        print("-" * 100)
        print(f"{'分析完成':^100}")
        print("=" * 100 + "\n")

        # =============================================================
        # 结果导出
        # =============================================================
        if stats_results:
            df_stats = pd.DataFrame(stats_results)
            self.stats_df = df_stats  # 保存到实例属性，供外部调用方获取统计结果

            # CSV导出
            csv_file = os.path.join(csv_dir, f'Stats_{sat1_name}_vs_{sat2_name}_Cumulative_Time.csv')
            df_stats.to_csv(csv_file, index=False)

            # Excel导出（多工作表）
            excel_file = os.path.join(csv_dir, f'Stats_{sat1_name}_vs_{sat2_name}_Cumulative_Time.xlsx')
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                df_stats.to_excel(writer, sheet_name='Statistics', index=False)
                if diff_data_all:
                    df_diff = pd.DataFrame(diff_data_all)
                    df_diff.to_excel(writer, sheet_name='All_Differences', index=False)

            print(f"✅ Excel文件已保存至：{excel_file}")

            # 差异数据CSV导出
            if diff_data_all:
                df_diff = pd.DataFrame(diff_data_all)
                diff_csv = os.path.join(csv_dir,
                                        f'Crossover_Diff_AllParams_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv')
                df_diff.to_csv(diff_csv, index=False)
                print(f"✅ 差异数据已导出（CSV）：{diff_csv}")

            # 打印统计报表
            print("\n" + "=" * 100)
            print("海洋气象累积时间窗口统计报表")
            print("=" * 100)
            try:
                print(df_stats[['Variable', 'Time_Window', 'Count', 'Bias', 'STD', 'RMSE', 'Corr']].to_markdown(
                    index=False))
            except Exception:
                print(df_stats[['Variable', 'Time_Window', 'Count', 'Bias', 'STD', 'RMSE', 'Corr']])
            print("=" * 100 + "\n")
            print(f"📊 统计表格已保存至：{csv_file}")
            print(f"📊 Excel表格已保存至：{excel_file}")
        else:
            self.stats_df = pd.DataFrame()

        # =============================================================
        # 计算质量控制剔除率与报告模板参数
        # =============================================================
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 计算质量控制剔除率与报告模板参数...")

        sat_ref = json_data.get('referenceALT', 'REF')
        report_params = {}

        # 参数名到 qc_data key 和 quality_control 配置键的映射
        param_qc_map = {
            'Sigma0': ('Sigma0', 'sigma0'),
            'SWH': ('SWH', 'swh'),
            'Wind Speed': ('Wind Speed', 'wind')
        }

        for param_label, (qc_key, ptype) in param_qc_map.items():
            stats = _get_param_stats(self.stats_df, param_label)

            if qc_key in qc_data:
                qd = qc_data[qc_key]

                # 计算参数自身原始值（取两颗卫星均值）用于 percent04 范围筛选
                v1_vals = qd.get('v1')
                v2_vals = qd.get('v2')
                if v1_vals is not None and v2_vals is not None:
                    valid_pv = np.isfinite(v1_vals) & np.isfinite(v2_vals)
                    param_values = np.where(valid_pv, (v1_vals + v2_vals) / 2.0, v1_vals)
                elif v1_vals is not None:
                    param_values = v1_vals
                else:
                    param_values = None

                qc = _compute_quality_control_stats(
                    qd['diff'], qd['lat'], qd['depth'], qd['dt'],
                    distance_arr=qd['distance'],
                    param_values_arr=param_values,
                    config=self.config,
                    param_type=ptype
                )
            else:
                qc = {'percent01': 0.0, 'percent02': 0.0, 'percent03': 0.0,
                      'percent04': 0.0, 'percent05': 0.0, 'percent06': 0.0,
                      'n_total': 0, 'n_2h': 0}

            report_params[param_label] = {
                'aft_num': stats['count'],
                'aft_bias': stats['bias'],
                'aft_std': stats['std'],
                'coef': stats['corr'],
                'percent01': qc['percent01'],
                'percent02': qc['percent02'],
                'percent03': qc['percent03'],
                'percent04': qc['percent04'],
                'percent05': qc['percent05'],
                'percent06': qc['percent06'],
                'n_total': qc.get('n_total', 0),
                'n_2h': qc.get('n_2h', 0),
            }

            print(f"  [{param_label}] N={stats['count']}, Bias={stats['bias']:.4f}, "
                  f"STD={stats['std']:.4f}, Corr={stats['corr']:.4f}")
            print(f"    QC(基于{qc.get('n_2h', 0)}个2h窗口点/共{qc.get('n_total', 0)}个原始点): "
                  f"p01={qc['percent01']:.3f}, p02={qc['percent02']:.3f}, "
                  f"p03={qc['percent03']:.3f}, p04={qc['percent04']:.3f}, "
                  f"p05={qc['percent05']:.3f}, p06={qc['percent06']:.3f}")

        self.report_params = report_params
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 质量控制与报告参数计算完毕。")


# =============================================================================
# 模块使用说明
# =============================================================================

"""
【快速开始】

1. 准备配置文件（config.json）：
   - 定义compareALT和referenceALT的变量映射
   - 设置质量筛选参数
   - 配置数据路径和处理参数

2. 运行分析流程：
   >>> from CrossOverCalibration import CrossOverCalibration
   >>> T = CrossOverCalibration(path1, path2, var1, var2, ...)
   >>> T.readdata_parallel()
   >>> T.matchdata(timespan=10)
   >>> T.crossoverpoint()
   >>> T.accuracy()
   >>> T.analyze_metocean_spatial_temporal(json_data)
   >>> T.save_XOverPoint()
   >>> T.cross_plot()

【输出文件】

- HDF5数据文件：*.h5（交叉点原始数据和筛选后数据）
- CSV统计文件：bias_*.csv（偏差随时间变化）
- Excel报告：Stats_*.xlsx（海洋气象参数统计分析）
- PNG图表：SSH差异地理分布图、直方图等

【注意事项】

- 数据路径必须包含有效的NetCDF文件
- 变量配置必须与数据文件中的实际变量名匹配
- 并行worker数量应根据CPU核心数合理设置
- 时间跨度参数影响匹配结果数量和质量
"""