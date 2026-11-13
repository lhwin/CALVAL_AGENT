# -*- coding: utf-8 -*-
"""
XOver.py
========

本模块提供高度计星下点轨道“交叉点匹配”和“交叉点插值”所需的基础函数，
主要用于双星交叉定标（Cross-Over Calibration）中的几何匹配部分。

核心思想
--------
1. XOverMatch:
   对两条轨道（通常分别来自两颗卫星或同一卫星不同轨次）进行粗匹配，
   判断它们是否存在一个可能的交叉点，并截取交叉点附近的局部轨道片段（8个点）。

2. XOverPoint:
   对 XOverMatch 提取出来的局部片段做线性拟合，求两段轨迹的几何交点，
   然后用三次插值在交点纬度上反演出两条轨道各变量在交叉点处的值。

3. smooth / movingaverage / rollavg_pandas:
   提供若干常用平滑函数，主要用于电离层改正或其他沿轨参数平滑处理。

作者原始信息
------------
Created on Sun Jan  6 16:54:43 2019
@author: DELL
"""

import sys
import os
import operator

from numpy import nanmin, nanmax, convolve
from pylab import zeros, nan, linspace, where, arange, ones, inv, hstack, dot, isnan, size
from numpy.linalg import solve
from scipy.interpolate import interp1d
from scipy.signal import lfilter
import numpy
import pandas as pd


def XOverMatch(array1, array1_len, array2, array2_len):
    """
    对两条轨道做粗交叉匹配，截取交叉点附近的局部窗口数据。

    参数
    ----
    array1 : ndarray
        第一条轨道数据，二维数组，要求：
        - 第0列是纬度 lat
        - 第1列是经度 lon
        - 后续列可以是高度计相关参数
    array1_len : int
        第一条轨道的样本点数
    array2 : ndarray
        第二条轨道数据，格式同 array1
    array2_len : int
        第二条轨道的样本点数

    返回
    ----
    Data1 : ndarray, shape=(8, para_num)
        第一条轨道在交叉点附近截取的 8 个点窗口。
        若未找到有效交叉，则返回全 NaN 数组。
    Data2 : ndarray, shape=(8, para_num)
        第二条轨道在交叉点附近截取的 8 个点窗口。
        若未找到有效交叉，则返回全 NaN 数组。

    算法说明
    --------
    1. 将两条轨道按纬度插值到统一纬度网格 lat_interp 上；
    2. 计算同纬度下两条轨道的经度差 lon_distance；
    3. 若最小经度差足够小（< 0.05°），认为存在潜在交叉；
    4. 在原轨道中找到与该纬度最接近的位置；
    5. 分别从两条轨道上各截取前后共 8 个点；
    6. 再通过轨道斜率差和局部跨度条件判断，排除近似平行或几何条件较差的情况。

    注意
    ----
    - para_num 被写死为 33，意味着输入 array1/array2 默认应有 33 列。
      如果你的数据列数不是 33，这里需要同步修改。
    - 这里的“交叉”是粗筛选，不是最终精确交点。
    """
    para_num = array1.shape[1]

    # 读取两条轨道的纬度、经度
    lat1 = array1[:, 0]
    lon1 = array1[:, 1]
    lat2 = array2[:, 0]
    lon2 = array2[:, 1]

    # 初始化输出：若匹配失败则返回全 NaN
    Data1 = zeros((8, para_num)) * nan
    Data2 = zeros((8, para_num)) * nan

    # 构建统一纬度插值网格
    # 范围约为 -66.15 ~ 66.15，共13231个点，间隔约0.01度
    lat_interp = linspace(-66.15, 66.15, 13231, endpoint=True)

    # 将两条轨道的经度插值到统一纬度网格上
    lon1_interp = interp1d(lat1, lon1, bounds_error=False)(lat_interp)
    lon2_interp = interp1d(lat2, lon2, bounds_error=False)(lat_interp)

    # 计算相同纬度下两轨道经度差
    lon_distance = lon2_interp - lon1_interp

    # 找经度差绝对值最小处，作为潜在交叉位置
    min_lon_distace = nanmin(abs(lon_distance))
    index_0 = where(abs(lon_distance) == min_lon_distace)

    # 初始化原轨道中的索引位置
    index1 = 0
    index2 = 0

    # 如果最小经度差足够小，则认为存在交叉可能
    if min_lon_distace < 0.05:
        # 在 array1 中寻找对应 lat_interp[index_0] 的位置
        for i in arange(array1_len):
            # 若轨道纬度递减
            if lat1[0] > lat1[array1_len - 1]:
                if lat1[i] < lat_interp[index_0[0]]:
                    index1 = i
                    break
            # 若轨道纬度递增
            else:
                if lat1[i] > lat_interp[index_0[0]]:
                    index1 = i
                    break

        # 在 array2 中寻找对应 lat_interp[index_0] 的位置
        for i in arange(array2_len):
            if lat2[0] > lat2[array2_len - 1]:
                if lat2[i] < lat_interp[index_0[0]]:
                    index2 = i
                    break
            else:
                if lat2[i] > lat_interp[index_0[0]]:
                    index2 = i
                    break

    # 进一步检查截窗是否有效：
    # 1) index 不能太靠边，需保证前后各能取4个点
    # 2) 局部纬度跨度不能太大
    # 3) 局部经度差不能太离谱
    if index1 >= 4 and index1 <= array1_len - 5 and \
       index2 >= 4 and index2 <= array2_len - 5 and \
       abs(lat1[index1 - 4] - lat1[index1 + 3]) < 0.8 and \
       abs(lat2[index2 - 4] - lat2[index2 + 3]) < 0.8 and \
       abs(lon1[index1 - 4] - lon2[index2 + 3]) < 0.8:

        # 估算两段局部轨迹在经纬平面上的斜率
        slope1 = (lon1[index1 + 3] - lon1[index1 - 4]) / (lat1[index1 + 3] - lat1[index1 - 4])
        slope2 = (lon2[index2 + 3] - lon2[index2 - 4]) / (lat2[index2 + 3] - lat2[index2 - 4])

        # 若两条轨迹斜率差足够大，说明不是几乎平行，保留该交叉候选
        if abs(slope1 - slope2) > 0.02:
            Data1 = array1[index1 - 4:index1 + 4, :]
            Data2 = array2[index2 - 4:index2 + 4, :]

    return Data1, Data2


def XOverPoint(sub1, sub2):
    """
    根据两段局部轨道（各8个点）精确求几何交点，并插值得到交叉点处的参数值。

    参数
    ----
    sub1 : ndarray
        第一条轨道在交叉附近的局部片段，通常是 shape=(8, N)
    sub2 : ndarray
        第二条轨道在交叉附近的局部片段，通常是 shape=(8, N)

    返回
    ----
    XoverSub1 : ndarray
        第一条轨道在几何交点处插值得到的一组变量值
    XoverSub2 : ndarray
        第二条轨道在几何交点处插值得到的一组变量值

    算法说明
    --------
    1. 用局部8个点分别拟合两条轨道在经纬平面上的直线：
         lat = a * lon + b
    2. 联立两条直线，求其交点 (lon, lat)
    3. 将 NaN 临时替换为一个极小值标记，以便 interp1d 能运行
    4. 用纬度作为自变量，对全部列做三次插值，求出交点纬度处的所有参数值
    5. 若经度大于 360，则回卷到 [0, 360)

    注意
    ----
    - 使用的是“纬度作为插值自变量”，因此 sub1[:,0] / sub2[:,0] 需单调且局部合理。
    - 三次插值要求局部点质量较好，否则会产生振荡。
    """
    # 构建线性拟合矩阵
    lat1 = ones((8, 2))
    lat2 = ones((8, 2))
    lon1 = ones((8, 2))
    lon2 = ones((8, 2))

    # 第1列存放纬度 / 经度，第2列为常数项1，用于线性拟合
    lat1[:, 0] = sub1[:, 0]
    lat2[:, 0] = sub2[:, 0]

    lon1_tmp = sub1[:, 1]
    lon2_tmp = sub2[:, 1]

    # 处理跨越 0/360 经线的情况，避免局部线性拟合失败
    if (lon1_tmp.max() - lon1_tmp.min()) > 300 or (lon2_tmp.max() - lon2_tmp.min()) > 300:
        lon1_tmp[lon1_tmp < 10] = lon1_tmp[lon1_tmp < 10] + 360
        lon2_tmp[lon2_tmp < 10] = lon2_tmp[lon2_tmp < 10] + 360

    lon1[:, 0] = lon1_tmp
    lon2[:, 0] = lon2_tmp

    # 线性拟合：lat = a * lon + b
    coef1 = dot(inv(dot(lon1.T, lon1)), (dot(lon1.T, lat1)))
    coef2 = dot(inv(dot(lon2.T, lon2)), (dot(lon2.T, lat2)))

    # 求两条拟合直线交点
    lon = (coef2[1, 0] - coef1[1, 0]) / (coef1[0, 0] - coef2[0, 0])
    lat = coef1[0, 0] * lon + coef1[1, 0]

    # 将 NaN 临时替换成哨兵值，避免插值函数报错
    sub1[isnan(sub1)] = -999999
    sub2[isnan(sub2)] = -999999

    # 以纬度为自变量，对所有列做三次插值，求交点纬度下的参数值
    XoverSub1 = interp1d(sub1[:, 0], sub1, kind='cubic', axis=0)(lat)
    XoverSub2 = interp1d(sub2[:, 0], sub2, kind='cubic', axis=0)(lat)

    # 经度回卷到 [0, 360)
    XoverSub1[1] = XoverSub1[1] if XoverSub1[1] < 360 else XoverSub1[1] - 360
    XoverSub2[1] = XoverSub2[1] if XoverSub2[1] < 360 else XoverSub2[1] - 360

    return XoverSub1, XoverSub2


def smooth_iono(data, span=20):
    """
    使用简单滑动平均对数据进行平滑，常用于电离层改正项平滑。

    参数
    ----
    data : ndarray
        输入序列
    span : int, default=20
        平滑窗口长度

    返回
    ----
    ndarray
        平滑后的数据

    说明
    ----
    基于 scipy.signal.lfilter 实现的前向滑动平均。
    """
    return lfilter(ones(span) / span, 1, data)


def moving_average(x, span):
    """
    手写版滑动平均函数。

    参数
    ----
    x : ndarray
        输入序列
    span : int
        窗口长度

    返回
    ----
    ndarray
        平滑结果

    说明
    ----
    这是一个逐点累加实现，速度较慢，但逻辑直观。
    """
    f = zeros(size(x))
    for k in arange(span):
        for j in arange(k, len(x), 1):
            f[j] += 1.0 / span * x[j - k]
    return f


def movingaverage(x, window_size):
    """
    基于 numpy.convolve 的滑动平均。

    参数
    ----
    x : ndarray
        输入序列
    window_size : int
        窗口长度

    返回
    ----
    ndarray
        平滑结果，与输入长度相同（mode='same'）
    """
    window = ones(int(window_size)) / float(window_size)
    return convolve(x, window, 'same')


def smooth(x, window_len=20, window='hanning', circshift=0):
    """
    对 1 维序列进行窗口平滑。

    参数
    ----
    x : ndarray
        输入一维序列
    window_len : int, default=20
        平滑窗口长度
    window : str, default='hanning'
        窗函数类型，可选:
        ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']
    circshift : int, default=0
        对输出结果做循环移位

    返回
    ----
    ndarray
        平滑后的数据（长度与原始实现保持一致，不完全等于输入长度）

    说明
    ----
    - flat 相当于移动平均
    - 其他窗函数用于减小旁瓣和边缘效应
    - 通过镜像扩展序列两端，降低边界畸变

    注意
    ----
    原始实现返回长度可能与输入长度略有差异。
    """
    if x.ndim != 1:
        raise (ValueError, "smooth only accepts 1 dimension arrays.")

    if x.size < window_len:
        raise (ValueError, "Input vector needs to be bigger than window size.")

    if window_len < 3:
        return x

    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise (ValueError, "Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")

    # 两端镜像扩展
    s = numpy.r_[x[window_len - 1:0:-1], x, x[-2:-window_len - 1:-1]]

    if window == 'flat':
        w = numpy.ones(window_len, 'd')
    else:
        w = eval('numpy.' + window + '(window_len)')

    y = numpy.roll(numpy.convolve(w / w.sum(), s, mode='valid'), circshift)
    return y


def smooth_v2(x, window_len=20, window='hanning'):
    """
    平滑函数改进版，返回长度与输入更一致。

    参数
    ----
    x : ndarray
        输入一维序列
    window_len : int, default=20
        平滑窗口长度
    window : str, default='hanning'
        窗函数类型

    返回
    ----
    ndarray
        平滑后的序列，长度更接近输入长度
    """
    if x.ndim != 1:
        raise (ValueError, "smooth only accepts 1 dimension arrays.")

    if x.size < window_len:
        raise (ValueError, "Input vector needs to be bigger than window size.")

    if window_len < 3:
        return x

    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise (ValueError, "Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")

    s = numpy.r_[x[window_len - 1:0:-1], x, x[-2:-window_len - 1:-1]]

    if window == 'flat':
        w = numpy.ones(window_len, 'd')
    else:
        w = eval('numpy.' + window + '(window_len)')

    y = numpy.convolve(w / w.sum(), s, mode='valid')[(window_len - 1) // 2:-(window_len - 1) // 2]
    return y


def rollavg_pandas(a, n):
    """
    使用 pandas 实现居中滑动平均，效果等价于 MATLAB 的 movmean。

    参数
    ----
    a : ndarray
        输入序列
    n : int
        窗口长度

    返回
    ----
    ndarray
        平滑后的结果

    特点
    ----
    - center=True：窗口居中
    - min_periods=1：边界处允许不足窗口长度
    """
    return pd.DataFrame(a).rolling(n, center=True, min_periods=1).mean().to_numpy()