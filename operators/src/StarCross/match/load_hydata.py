# -*- coding: utf-8 -*-
"""
Created on Wed Dec  1 10:44:06 2021

@author: vr
"""
import pickle
import pickle as pkl
import os
import traceback
from collections import defaultdict
import json
import pickle as pkl
import numpy as np
from huatu import huatu
from tqdm import trange, tqdm
import time
import  torch
from authenticity_utils import is_on_interval, isIntersected, get_cross_point, CrossPoint, abbreviation_features, line, point, degree2distance, Unit_Dist
def select_satellites(satellite):
    '''
    不同卫星数据中的属性
    :param satellite: 卫星名
    :return: 卫星星下点需要被关注的信息
    '''
    satellites = {
        'HY-2B': ["lat", "lon", "time", "alt", "range_ku", "model_dry_tropo_corr", "rad_wet_tropo_corr",
                  "iono_corr_alt_ku", "sea_state_bias_ku", "ocean_tide_sol1", "solid_earth_tide",
                  "pole_tide", "inv_bar_corr", "hf_fluctuations_corr", "sig0_c", "sig0_ku",
                  'wind_speed_alt', 'swh_ku', "mean_sea_surface"],
        'HY-2C': ["lat", "lon", "time", "alt", "range_ku", "model_dry_tropo_corr", "rad_wet_tropo_corr",
                  "iono_corr_alt_ku", "sea_state_bias_ku", "ocean_tide_sol1", "solid_earth_tide",
                  "pole_tide", "inv_bar_corr", "load_tide_sol1", "sig0_c", "sig0_ku",
                  'wind_speed_alt', 'swh_ku', "mean_sea_surface"],
        'JASON-3D': ["lat", "lon", "time", "alt", "range_ku", "model_dry_tropo_corr", "rad_wet_tropo_corr",
                    "iono_corr_alt_ku", "sea_state_bias_ku", "ocean_tide_sol1", "solid_earth_tide",
                    "pole_tide", "inv_bar_corr", "hf_fluctuations_corr", "sig0_c", "sig0_ku",
                    'wind_speed_alt', 'swh_ku', "mean_sea_surface"],
        'Jason2': ["lat", "lon", "time", "alt", "range_ku", "model_dry_tropo_corr", "rad_wet_tropo_corr",
                   "iono_corr_alt_ku", "sea_state_bias_ku", "ocean_tide_sol1", "solid_earth_tide",
                   "pole_tide", "inv_bar_corr", "load_tide_sol1", "sig0_c", "sig0_ku",
                   'wind_speed_alt', 'swh_ku', "mean_sea_surface"],
        'JASON-3F': ["latitude", "longitude", "time", "altitude", "range_ocean",
                   "model_dry_tropo_cor_zero_altitude", "rad_wet_tropo_cor",
                   "iono_cor_alt", "sea_state_bias", "ocean_tide_got", "solid_earth_tide",
                   "pole_tide", "dac", "load_tide_got", "sig0_ocean_c","sig0_ocean_ku",
                   "wind_speed_alt", "swh_ocean", "mean_sea_surface_cnescls"],
        'Saral': ["lat", "lon", "time", "alt", "range", "model_dry_tropo_corr", "rad_wet_tropo_corr",
                  "iono_corr_gim", "sea_state_bias", "ocean_tide_sol1", "solid_earth_tide",
                  "pole_tide", "inv_bar_corr", "load_tide_sol1", "sig0", "sig0",
                  'wind_speed_alt', 'swh', "mean_sea_surface_sol1"],
        'Sentinel-3A': ["lat_01", "lon_01", "time_01", "alt_01", "range_ocean_01_ku",
                        "mod_dry_tropo_cor_meas_altitude_01", "mod_wet_tropo_cor_meas_altitude_01",
                        "iono_cor_gim_01_ku", "sea_state_bias_01_ku", "ocean_tide_sol1_01",
                        "solid_earth_tide_01", "pole_tide_01", "inv_bar_cor_01", "load_tide_sol1_01",
                        "sig0_ocean_01_c", "sig0_ocean_01_ku", 'wind_speed_alt_01_ku',
                        'swh_ocean_01_ku', "mean_sea_surf_sol1_01"]
    }
    return satellites.get(satellite, None)

def iter_files(others_path):
    others_relative_path_dict = defaultdict(list)
    if 'Sentinel-3A' in others_path:
        flag2 = True
    else:
        flag2 = False
    for others_root, others_dirs, others_files in os.walk(others_path):
        if flag2:
            for others_dir in others_dirs:
                if others_dir.endswith('.SEN3'):
                    others_relative_path_dict[others_root].append(others_dir)
        else:
            for others_file in others_files:
                if others_file.endswith('.nc'):
                    others_relative_path_dict[others_root].append(others_file)
    # for others_root, others_dirs, others_files in os.walk(others_path):
    #     for others_file in others_files:
    #         if others_file.endswith('.nc'):
    #             others_relative_path_dict[others_root].append(others_file)
    return  others_relative_path_dict


def extract_data_month(conf_dict, features_h2b, features_others,input):
    '''
    按月份提取数据
    :param conf_dict: 配置信息
    :param features_h2b: h2b卫星属性
    :param features_others: 参考卫星属性
    :return: 返回一个月的HY2B和对应参考卫星的星下点数据矩阵
    '''
    h2b_matrix, JASON3_matrix = [], []
    inputdir_h2b = conf_dict['primaryFile']
    #inputdir_JASON3 = conf_dict['auxFile'][2]
    #inputdir_JASON3 = conf_dict['auxFile'][4]
    inputdir_JASON3 = input
    files_ = os.path.basename(inputdir_h2b)
    h2b_matrix_dict = com_dict(inputdir_h2b, features_h2b)
    h2b_time = time_extract(files_)
    h2b_matrix_dict['time_extract'] = h2b_time
    h2b_matrix.append(h2b_matrix_dict)

    others_relative_path_dict = iter_files(inputdir_JASON3)
    for key, values in others_relative_path_dict.items():
        for value in values:
            JASON3_matrix_dict = com_dict((key + value), features_others)
            others_time = time_extract(value)
            JASON3_matrix_dict['time_extract'] = others_time
            JASON3_matrix.append(JASON3_matrix_dict)
    #return h2b_matrix_dict, JASON3_matrix_dict
    return h2b_matrix, JASON3_matrix


def com_dict(inputDir, features):
    '''
    提取数据，以字典形式返回
    :param key: 星下点数据所处文件夹路径
    :param value: 星下点数据名称
    :param features: 星下点数据需要被关注的属性
    :param conf_dict: 配置信息
    :return: 提取的特征数据
    '''
    com_dict_ = {}
    flag = True
    files_ = os.path.basename(inputDir)
    if files_.startswith('JA3_GPN_2Pf'):
        datas = nc.Dataset(inputDir)
        lat_list = datas.groups["data_01"].variables[features[0]][:]
        depth_or_elevation = datas.groups["data_01"].variables["depth_or_elevation"][:]
        lat_index = np.argwhere(np.absolute(lat_list) < 50).flatten()
        depth_or_elevation_index = np.argwhere(np.absolute(depth_or_elevation) < 1000).flatten()
        index = np.setdiff1d(lat_index, depth_or_elevation_index)
        com_dict_[features[0]] = lat_list[index]
        for key_, value_ in datas.groups["data_01"].groups["c"].variables.items():
            if key_ in features[1:] or key_ == "sig0_ocean":
                # 其他属性

                if key_ == "sig0_ocean":
                    key_ = "sig0_ocean_c"
                if hasattr(value_, '_FillValue'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_._FillValue).flatten()
                # 时间
                elif hasattr(value_[0], 'fill_value'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_[0].fill_value).flatten()
                # 经纬度(不存在掩码操作)
                else:
                    com_dict_[key_] = (value_[:].data)[index]
                # 记录掩码位置
                if isinstance(arg_index, np.ndarray) and len(arg_index) > 0:
                    if flag:
                        mask_index = arg_index
                        flag = False
                        continue
                    # 记录被掩码的索引位置
                    mask_index = np.append(mask_index, arg_index)
            if not flag:
                # 剔除重复掩码索引
                mask_index = np.unique(mask_index)
                com_dict_['masked_index'] = mask_index
            else:
                com_dict_['masked_index'] = 0
        for key_, value_ in datas.groups["data_01"].groups["ku"].variables.items():
            if key_ in features[1:] or key_ == "sig0_ocean":
                # 其他属性
                if key_ == "sig0_ocean":
                    key_ = "sig0_ocean_ku"
                if hasattr(value_, '_FillValue'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_._FillValue).flatten()
                # 时间
                elif hasattr(value_[0], 'fill_value'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_[0].fill_value).flatten()
                # 经纬度(不存在掩码操作)
                else:
                    com_dict_[key_] = (value_[:].data)[index]
                # 记录掩码位置
                if isinstance(arg_index, np.ndarray) and len(arg_index) > 0:
                    if flag:
                        mask_index = arg_index
                        flag = False
                        continue
                    # 记录被掩码的索引位置
                    mask_index = np.append(mask_index, arg_index)
            if not flag:
                # 剔除重复掩码索引
                mask_index = np.unique(mask_index)
                com_dict_['masked_index'] = mask_index
            else:
                com_dict_['masked_index'] = 0
        for key_, value_ in datas.groups["data_01"].variables.items():
            if key_ in features[1:]:
                # 其他属性
                if hasattr(value_, '_FillValue'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_._FillValue).flatten()
                # 时间
                elif hasattr(value_[0], 'fill_value'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_[0].fill_value).flatten()
                # 经纬度(不存在掩码操作)
                else:
                    com_dict_[key_] = (value_[:].data)[index]
                # 记录掩码位置
                if isinstance(arg_index, np.ndarray) and len(arg_index) > 0:
                    if flag:
                        mask_index = arg_index
                        flag = False
                        continue
                    # 记录被掩码的索引位置
                    mask_index = np.append(mask_index, arg_index)
            if not flag:
                # 剔除重复掩码索引
                mask_index = np.unique(mask_index)
                com_dict_['masked_index'] = mask_index
            else:
                com_dict_['masked_index'] = 0
        return com_dict_

    elif files_.endswith('.SEN3'):
        datas = nc.Dataset(inputDir + '\\' + 'enhanced_measurement.nc').variables
        lat_list = datas['lat_01'][:].data
        bathymetry = datas['odle_01'][:].data
        lat_index = np.argwhere(np.absolute(lat_list) < 50).flatten()
        bathymetry_index = np.argwhere(np.absolute(bathymetry) < 1000).flatten()
        # lat_list = datas.groups["data_01"].variables[features[0]][:]
        # lat_list = datas[features[0]][:].data
        # bathymetry = datas['bathymetry'][:].data
        # lat_index = np.argwhere(np.absolute(lat_list) < conf_dict['other_lat_interval']).flatten()  # 限制纬度范围
        # bathymetry_index = np.argwhere(np.absolute(bathymetry) < conf_dict['bathymetry']).flatten()  # 水深限制
        index = np.setdiff1d(lat_index, bathymetry_index)
        com_dict_[features[0]] = lat_list[index]
        # 对多个属性取值，同时记录被掩码的索引
        for key_, value_ in datas.items():
            if key_ in features[1:]:
                # 其他属性
                if hasattr(value_, '_FillValue'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_._FillValue).flatten()
                # 时间
                elif hasattr(value_[0], 'fill_value'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_[0].fill_value).flatten()
                # 经纬度(不存在掩码操作)
                else:
                    com_dict_[key_] = (value_[:].data)[index]
                # 记录掩码位置
                if isinstance(arg_index, np.ndarray) and len(arg_index) > 0:
                    if flag:
                        mask_index = arg_index
                        flag = False
                        continue
                    # 记录被掩码的索引位置
                    mask_index = np.append(mask_index, arg_index)
        if not flag:
            # 剔除重复掩码索引
            mask_index = np.unique(mask_index)
            com_dict_['masked_index'] = mask_index
        else:
            com_dict_['masked_index'] = 0
        return com_dict_

    else:
        datas = nc.Dataset(inputDir).variables
        lat_list = datas[features[0]][:].data
        bathymetry = datas['bathymetry'][:].data
        lat_index = np.argwhere(np.absolute(lat_list) < 50).flatten()
        bathymetry_index = np.argwhere(np.absolute(bathymetry) < 1000).flatten()
        # lat_list = datas.groups["data_01"].variables[features[0]][:]
        # lat_list = datas[features[0]][:].data
        # bathymetry = datas['bathymetry'][:].data
        # lat_index = np.argwhere(np.absolute(lat_list) < conf_dict['other_lat_interval']).flatten()  # 限制纬度范围
        # bathymetry_index = np.argwhere(np.absolute(bathymetry) < conf_dict['bathymetry']).flatten()  # 水深限制
        index = np.setdiff1d(lat_index, bathymetry_index)  # 在ar1中但不在ar2中的已排序的唯一值。返回的值从小到大排序，并且唯一
        com_dict_[features[0]] = lat_list[index]
        # 对多个属性取值，同时记录被掩码的索引
        for key_, value_ in datas.items():
            if key_ in features[1:]:
                # 其他属性
                if hasattr(value_, '_FillValue'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_._FillValue).flatten()
                # 时间
                elif hasattr(value_[0], 'fill_value'):
                    value_dict = (value_[:].data)[index]
                    com_dict_[key_] = value_dict
                    # 记录掩码索引
                    arg_index = np.argwhere(value_dict == value_[0].fill_value).flatten()
                # 经纬度(不存在掩码操作)
                else:
                    com_dict_[key_] = (value_[:].data)[index]
                # 记录掩码位置
                if isinstance(arg_index, np.ndarray) and len(arg_index) > 0:
                    if flag:
                        mask_index = arg_index
                        flag = False
                        continue
                    # 记录被掩码的索引位置
                    mask_index = np.append(mask_index, arg_index)
        if not flag:
            # 剔除重复掩码索引
            mask_index = np.unique(mask_index)
            com_dict_['masked_index'] = mask_index
        else:
            com_dict_['masked_index'] = 0
        return com_dict_

def h2b_other_orbit_intersect(h2b_matrix, others_matrix, features_h2b, features_others):
    '''
    计算HY-2B和参考卫星相同时期内(时间尺度相同)的星星交叉相关信息
    :param h2b_matrix: HY2B卫星的数据矩阵
    :param others_matrix: 参考卫星的数据矩阵
    :param conf_dict: 配置信息
    :return: 所有星星交叉信息
    '''
    crosspoints = []
    h2b_matrix_len = len(h2b_matrix)
    others_matrix_len = len(others_matrix)
    # 遍历内存中的数据
    for i in trange(h2b_matrix_len):
        for j in range(others_matrix_len):
            if not is_on_interval(h2b_matrix[i]['time_extract'], others_matrix[j]['time_extract'], 259200):
                continue
            # 计算交叉点
            crosspoint = h2b_others_cross(h2b_matrix[i], others_matrix[j], features_h2b, features_others)
            if crosspoint != None:
                # 记录交叉点
                crosspoints.append(crosspoint)
            else:
                continue
    if crosspoints != []:
        return crosspoints
    return None


# def h2b_other_day_intersect(h2b_matrix, others_matrix, features_h2b, features_others):
#     """
#     计算HY2B和参考卫星相同时期内(时间尺度相同)每天的星星交叉相关信息
#     :param h2b_matrix: HY2B卫星的数据矩阵
#     :param others_matrix: 参考卫星的数据矩阵
#     :param conf_dict: 配置信息
#     :return: 所有星星交叉信息
#     """
#     crosspoints = defaultdict(list)
#     flag = True
#     for h2b_item in tqdm(h2b_matrix):
#         if flag:
#             h2b_time = h2b_item['time_extract'][1][:8]
#             flag = False
#         crosspoint_ = None
#         for others_item in others_matrix:
#             if not is_on_interval(h2b_item['time_extract'], others_item['time_extract'], 259200):
#                 continue
#             # 计算交叉点
#             crosspoint = h2b_others_cross(h2b_item, others_item,  features_h2b, features_others)
#             if crosspoint != None:
#                 # 记录交叉点
#                 crosspoints[h2b_time].append(crosspoint)
#                 crosspoint_ = crosspoint
#             else:
#                 continue
#         if int(h2b_item['time_extract'][1][:6]) == int(h2b_time[:6]) and int(h2b_item['time_extract'][1][:8]) > int(h2b_time):
#             if crosspoint_ != None:
#                 crosspoints[h2b_item['time_extract'][1][:8]].append(crosspoint_)
#             flag = True
#     if len(crosspoints) != 0:
#         return crosspoints
#     return None

from scipy.interpolate import Rbf
def h2b_others_cross(h2b_orbit_matrix, others_orbit_matrix, features_h2b, features_others):
    """
    计算单刈幅HY2B和参考卫星星下点交点
    :param h2b_orbit_matrix: 单刈幅HY2B星下点
    :param others_orbit_matrix: 单刈幅参考卫星星下点
    :param conf_dict: 配置信息
    :param features_h2b: h2b卫星属性
    :param features_others: 参考卫星属性
    :return: 交叉点信息
    """
    lon_h2b, lat_h2b, lon_others, lat_others = h2b_orbit_matrix[features_h2b[1]], h2b_orbit_matrix[features_h2b[0]], \
                                               others_orbit_matrix[features_others[1]], others_orbit_matrix[features_others[0]]
    # 校验
    if len(lon_h2b) == 0 or len(lat_h2b) == 0 or len(lon_others) == 0 or len(lat_others) == 0:
        return
    # 空间尺度初相关判断：初步判断刈幅是否存在交叉点
    if not isIntersected(lon_h2b, lat_h2b, lon_others, lat_others):
        return
    # 假设交叉点存在两组星下点轨迹最近点附近
    ## GPU加速
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    torch.set_default_tensor_type(torch.DoubleTensor)#san
    lon_h2b_tensor, lat_h2b_tensor = torch.Tensor(lon_h2b).to(device), torch.Tensor(lat_h2b).to(device)
    # b = torch.tensor(lon_h2b_tensor).dtype#san
    # if b == "torch.float64" :
    #     print("ha")
    lon_others_tensor, lat_others_tensor = torch.Tensor(lon_others).to(device), torch.Tensor(lat_others).to(device)
    # 经纬度转距离 n m = n*m
    distance_lon_lat_tensor = degree2distance(lon_h2b_tensor, lat_h2b_tensor, lon_others_tensor, lat_others_tensor, unit_dist=Unit_Dist.METERS)
    h2b_others_min_distance_relative_index = (distance_lon_lat_tensor == distance_lon_lat_tensor.min()).nonzero().flatten()
    # 若存在两对以上最近点，则取第一对
    [h2b_min_distance_index, others_min_distance_index] = h2b_others_min_distance_relative_index.tolist()[:2]

    if (h2b_min_distance_index == 1 or h2b_min_distance_index == len(lon_h2b) - 1
            or
        others_min_distance_index == 1 or others_min_distance_index == len(lon_others) - 1):
        return
    # 判断连续三点是否被masked
    if isinstance(h2b_orbit_matrix['masked_index'], np.ndarray) and np.absolute(
            h2b_orbit_matrix['masked_index'] - h2b_min_distance_index).min() <= 1:
        return
    if isinstance(others_orbit_matrix['masked_index'], np.ndarray) and np.absolute(
            others_orbit_matrix['masked_index'] - others_min_distance_index).min() <= 1:
        return
    # 计算相交点经纬度
    l_h2b = line(point(lon_h2b[h2b_min_distance_index - 1], lat_h2b[h2b_min_distance_index - 1]),
                 point(lon_h2b[h2b_min_distance_index + 1], lat_h2b[h2b_min_distance_index + 1]))
    l_others = line(point(lon_others[others_min_distance_index - 1], lat_others[others_min_distance_index - 1]),
                    point(lon_others[others_min_distance_index + 1], lat_others[others_min_distance_index + 1]))
    h2b_others_cross_point = get_cross_point(l_h2b, l_others)  # (lon, lat)
    # 重新确定交叉点的最近点各星星索引位置
    h2b_middle_index = np.argmin(np.absolute(lon_h2b - h2b_others_cross_point.x))
    others_middle_index = np.argmin(np.absolute(lon_others - h2b_others_cross_point.x))
    # 判断连续多点的索引是否正确
    continuous_point_before = 9 // 2
    continuous_point_after = continuous_point_before + 1
    if not (h2b_middle_index >= continuous_point_before and
            h2b_middle_index <= len(lon_h2b) - continuous_point_after and
            others_middle_index >= continuous_point_before and
            others_middle_index <= len(lon_others) - continuous_point_after):
        return
    # 判断连续点是否被masked, 即排除陆地的影响
    if isinstance(h2b_orbit_matrix['masked_index'], np.ndarray) and np.absolute(
            h2b_orbit_matrix['masked_index'] - h2b_middle_index).min() <= 9 // 2:
        return
    if isinstance(others_orbit_matrix['masked_index'], np.ndarray) and np.absolute(
            others_orbit_matrix['masked_index'] - others_middle_index).min() <= 9 // 2:
        return
    # 记录连续点时间等其他特征信息
    interp_lon_h2b = lon_h2b[h2b_middle_index - continuous_point_before: h2b_middle_index + continuous_point_after]
    interp_lat_h2b = lat_h2b[h2b_middle_index - continuous_point_before: h2b_middle_index + continuous_point_after]
    interp_h2b_features = {feature: h2b_orbit_matrix[feature][
                                    h2b_middle_index - continuous_point_before: h2b_middle_index + continuous_point_after]
                           for feature in features_h2b[2:]}
    interp_lon_others = lon_others[others_middle_index - continuous_point_before: others_middle_index + continuous_point_after]
    interp_lat_others = lat_others[others_middle_index - continuous_point_before: others_middle_index + continuous_point_after]
    interp_others_features = {feature: others_orbit_matrix[feature][
                                       others_middle_index - continuous_point_before: others_middle_index + continuous_point_after]
                              for feature in features_others[2:]}
    '''
        Rbf径向基函数插值工作原理: 
            https://desktop.arcgis.com/zh-cn/arcmap/latest/extensions/geostatistical-analyst/how-radial-basis-functions-work.htm
    '''
    # 根据径向基函数进行插值
    interp_h2b = {
        key: Rbf(interp_lon_h2b, interp_lat_h2b, value, function='linear')(h2b_others_cross_point.x, h2b_others_cross_point.y)
        for (key, value) in interp_h2b_features.items()}
    interp_others = {
        key: Rbf(interp_lon_others, interp_lat_others, value, function='linear')(h2b_others_cross_point.x, h2b_others_cross_point.y)
        for (key, value) in interp_others_features.items()}
    # 最后判断交叉点的时间尺度
    if np.abs(interp_h2b[features_h2b[2]] - interp_others[features_others[2]]) > 259200:
        return
    if np.abs(interp_h2b[features_h2b[2]] - interp_others[features_others[2]]) <= 1800:
        return CrossPoint(h2b_others_cross_point, interp_h2b, interp_others, False)
    return CrossPoint(h2b_others_cross_point, interp_h2b, interp_others, True)

def crosspoints_ssh(crosspoints, features_h2b, features_others):
    '''
    :param crosspoints: 星星交叉点
    :param conf_dict: 配置信息
    :param features_h2b: h2b卫星属性
    :param features_others: 参考卫星属性
    :return: HY2B和参考卫星SSH偏差, 符合阈值的索引和可视化保存路径
    '''
    diff_h2b = np.array([crosspoint.feature_h2b[features_h2b[3]] for crosspoint in crosspoints])
    diff_others = np.array([crosspoint.feature_others[features_others[3]] for crosspoint in crosspoints])

    Lat = np.array([crosspoint.lon_lat.y for crosspoint in crosspoints])
    Lat = np.radians(Lat)
    H = (6378136.3 - 6378137) * (np.cos(Lat)) ** 2 + (6356751.600563 - 6356752.31424518) * (np.sin(Lat)) ** 2
    if 'dac' in features_others:
        ssh_h2b = features_h2b[4:14]
        ssh_others = features_others[4:13]
        for feature_h2b in ssh_h2b:
            diff_h2b -= np.array([crosspoint.feature_h2b[feature_h2b] for crosspoint in crosspoints])
        for feature_others in ssh_others:
            diff_others -= np.array([crosspoint.feature_others[feature_others] for crosspoint in crosspoints])
        diff_h2b = diff_h2b + H

    else:
        ssh_h2b = features_h2b[4:14]
        ssh_others = features_others[4:14]
        for feature_h2b, feature_others in zip(ssh_h2b, ssh_others):
            '''误差参数统计'''
            diff_h2b -= np.array([crosspoint.feature_h2b[feature_h2b] for crosspoint in crosspoints])
            diff_others -= np.array([crosspoint.feature_others[feature_others] for crosspoint in crosspoints])


    # ssh_h2b = features_h2b[4:14]
    # ssh_others = features_others[4:13]
    # for feature_h2b in ssh_h2b:
    #     diff_h2b -= np.array([crosspoint.feature_h2b[feature_h2b] for crosspoint in crosspoints])
    # for feature_others in ssh_others:
    #     diff_others -= np.array([crosspoint.feature_others[feature_others] for crosspoint in crosspoints])
    # ssh_h2b = features_h2b[4:14]
    # ssh_others = features_others[4:14]
    # for feature_h2b, feature_others in zip(ssh_h2b, ssh_others):
    #     '''误差参数统计'''
    #     diff_h2b -= np.array([crosspoint.feature_h2b[feature_h2b] for crosspoint in crosspoints])
    #     diff_others -= np.array([crosspoint.feature_others[feature_others] for crosspoint in crosspoints])
    diff = diff_h2b - diff_others
        #todo
    index = np.argwhere(np.absolute(diff) < 0.20).flatten()
    diff_h2b = diff_h2b[index]
    diff_others = diff_others[index]
    return diff_h2b, diff_others, diff


def time_extract(file):
    # todo 正则表达替换
    '''
    根据星下点数据文件名，抽取刈幅开始和结束时间
    :param file: 星下点数据文件名名称
    :return:月检验周期的开始和结束时间
    '''
    if not isinstance(file, str):
        raise TypeError('文件名非字符串!!!')
    if 'H2B' in file:
        file_list = file.split('_')
        file_time_begin = file_list[-2].replace('T','')
        file_time_end = file_list[-1][:-3].replace('T','')
    elif 'JA3' in file:
        file_list = file.replace('_', '')
        file_time_begin = file_list[16:30]
        file_time_end = file_list[30:44]
    elif 'JA2' in file:
        file_list = file.replace('_', '')
        file_time_begin = file_list[16:30]
        file_time_end = file_list[30:44]
    elif 'SRL' in file:
        file_list = file.replace('_', '')
        file_time_begin = file_list[17:31]
        file_time_end = file_list[31:45]
    elif 'S3A' in file:
        file_list = file.split('_')
        file_time_begin = file_list[7].replace('T', '')
        file_time_end = file_list[8].replace('T', '')
    else:
        raise TypeError('文件名称不规范!!!')
    return (file_time_begin, file_time_end)

import netCDF4 as nc
import numpy as np
def Validation_match(conf_dict,input):
    '''
    匹配数据集，以pkl字典形式返回
    :param conf_dict: 配置信息
    :return: 重处理匹配数据集
    '''
    with open(conf_dict["resultFlowFile"],"r") as matchFlow:
        matchFlowConfig = json.load(matchFlow)
    '''Step4'''
    print('step' + matchFlowConfig['step'][3]['stepNo'] + ': ' + matchFlowConfig['step'][3]['stepName'])
    #input = conf_dict['auxFile'][3]#2/Saral     #3/saob      #4/jason
    directory, module_name = os.path.split(input)
    files = os.path.basename(directory)
    features_h2b, features_others = select_satellites('HY-2B'), select_satellites(files)
    #features_h2b, features_others = select_satellites('HY-2B'), select_satellites('jason')
    h2b_matrix1, JASON3_matrix1 = extract_data_month(conf_dict, features_h2b, features_others,input)
    crosspoints = h2b_other_orbit_intersect(h2b_matrix1, JASON3_matrix1, features_h2b, features_others)
    h2b_ssh, others_ssh, diff = crosspoints_ssh(crosspoints, features_h2b, features_others)
    LON = np.array([crosspoint.lon_lat.x for crosspoint in crosspoints])
    LAT = np.array([crosspoint.lon_lat.y for crosspoint in crosspoints])
    TIME = np.array([crosspoint.feature_h2b['time'] for crosspoint in crosspoints])
    if files == 'Sentinel-3A':
        TIME1 = np.array([crosspoint.feature_others['time_01'] for crosspoint in crosspoints])
    else:
        TIME1 = np.array([crosspoint.feature_others['time'] for crosspoint in crosspoints])
    ALT = np.array([crosspoint.feature_h2b['alt'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        ALT1 = np.array([crosspoint.feature_others['altitude'] for crosspoint in crosspoints])
    elif files == 'Saral':
        ALT1 = np.array([crosspoint.feature_others['alt'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        ALT1 = np.array([crosspoint.feature_others['alt_01'] for crosspoint in crosspoints])
    RANGE = np.array([crosspoint.feature_h2b['range_ku'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        RANGE1 = np.array([crosspoint.feature_others['range_ocean'] for crosspoint in crosspoints])
    elif files == 'Saral':
        RANGE1 = np.array([crosspoint.feature_others['range'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        RANGE1 = np.array([crosspoint.feature_others['range_ocean_01_ku'] for crosspoint in crosspoints])
    DRY = np.array([crosspoint.feature_h2b['model_dry_tropo_corr'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        DRY1 = np.array([crosspoint.feature_others['model_dry_tropo_cor_zero_altitude'] for crosspoint in crosspoints])
    elif files == 'Saral':
        DRY1 = np.array([crosspoint.feature_others['model_dry_tropo_corr'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        DRY1 = np.array([crosspoint.feature_others['mod_dry_tropo_cor_meas_altitude_01'] for crosspoint in crosspoints])
    WET = np.array([crosspoint.feature_h2b['rad_wet_tropo_corr'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        WET1 = np.array([crosspoint.feature_others['rad_wet_tropo_cor'] for crosspoint in crosspoints])
    elif files == 'Saral':
        WET1 = np.array([crosspoint.feature_others['rad_wet_tropo_corr'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        WET1 = np.array([crosspoint.feature_others['mod_wet_tropo_cor_meas_altitude_01'] for crosspoint in crosspoints])
    IONO = np.array([crosspoint.feature_h2b['iono_corr_alt_ku'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        IONO1 = np.array([crosspoint.feature_others['iono_cor_alt'] for crosspoint in crosspoints])
    elif files == 'Saral':
        IONO1 = np.array([crosspoint.feature_others['iono_corr_gim'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        IONO1 = np.array([crosspoint.feature_others['iono_cor_gim_01_ku'] for crosspoint in crosspoints])
    SSB = np.array([crosspoint.feature_h2b['sea_state_bias_ku'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        SSB1 = np.array([crosspoint.feature_others['sea_state_bias'] for crosspoint in crosspoints])
    elif files == 'Saral':
        SSB1 = np.array([crosspoint.feature_others['sea_state_bias'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        SSB1 = np.array([crosspoint.feature_others['sea_state_bias_01_ku'] for crosspoint in crosspoints])
    WS = np.array([crosspoint.feature_h2b['wind_speed_alt'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        WS1 = np.array([crosspoint.feature_others['wind_speed_alt'] for crosspoint in crosspoints])
    elif files == 'Saral':
        WS1 = np.array([crosspoint.feature_others['wind_speed_alt'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        WS1 = np.array([crosspoint.feature_others['wind_speed_alt_01_ku'] for crosspoint in crosspoints])
    SWH = np.array([crosspoint.feature_h2b['swh_ku'] for crosspoint in crosspoints])
    if files == 'JASON-3':
        SWH1 = np.array([crosspoint.feature_others['swh_ocean'] for crosspoint in crosspoints])
    elif files == 'Saral':
        SWH1 = np.array([crosspoint.feature_others['swh'] for crosspoint in crosspoints])
    elif files == 'Sentinel-3A':
        SWH1 = np.array([crosspoint.feature_others['swh_ocean_01_ku'] for crosspoint in crosspoints])
    SSH = h2b_ssh
    SSH1 = others_ssh
    # hy2b_inputDir = conf_dict['primaryFile']
    # hy2b_data = nc.Dataset(hy2b_inputDir)
    # hy2b_lat = hy2b_data.variables['lat'][:]
    # hy2b_lon = hy2b_data.variables['lon'][:]
    # hy2b_time = hy2b_data.variables['time'][:]/3600 + 36524*24
    # range_ku = hy2b_data.variables['range_ku'][:]
    # depth = hy2b_data.variables['bathymetry'][:]
    #
    # hy2b_dry_correction = hy2b_data.variables['model_dry_tropo_corr'][:]
    # hy2b_wet_correction = hy2b_data.variables['rad_wet_tropo_corr'][:]
    # hy2b_iono_correction = hy2b_data.variables['iono_corr_gim_ku'][:]
    # hy2b_ssb_correction = hy2b_data.variables['sea_state_bias_ku'][:]
    # hy2b_altuv_correction = hy2b_data.variables['wind_speed_alt'][:]
    # hy2b_raduv_correction = hy2b_data.variables['wind_speed_rad'][:]
    # hy2b_swhku_correction = hy2b_data.variables['swh_ku'][:]
    # hy2b_oceantide_correction = hy2b_data.variables['ocean_tide_sol1'][:]
    # hy2b_loadtide_correction = hy2b_data.variables['load_tide_sol1'][:]
    # hy2b_solidtide_correction = hy2b_data.variables['solid_earth_tide'][:]
    # hy2b_poletide_correction = hy2b_data.variables['pole_tide'][:]
    # hy2b_inv_correction = hy2b_data.variables['inv_bar_corr'][:]
    # hy2b_alt = hy2b_data.variables['alt'][:]
    #
    # hy2b_time_con,hy2b_lat_con,hy2b_lon_con,hy2b_rangeku_con,hy2b_depth_con = [],[],[],[],[]
    # hy2b_dry_correction_con,hy2b_wet_correction_con,hy2b_iono_correction_con,hy2b_ssb_correction_con = [],[],[],[]
    # hy2b_altuv_correction_con,hy2b_raduv_correction_con,hy2b_swhku_correction_con,hy2b_oceantide_correction_con = [],[],[],[]
    # hy2b_loadtide_correction_con,hy2b_solidtide_correction_con,hy2b_poletide_correction_con,hy2b_inv_correction_con = [],[],[],[]
    # hy2b_alt_con = []
    #
    # for i in range(len(hy2b_time)):
    #     if hy2b_lat[i] <= 60 and hy2b_lat[i] >= -60 and hy2b_lon[i] < 359.75:
    #         hy2b_time_con.append(hy2b_time[i])
    #         hy2b_lat_con.append(hy2b_lat[i])
    #         hy2b_lon_con.append(hy2b_lon[i])
    #         hy2b_rangeku_con.append(range_ku[i])
    #         hy2b_depth_con.append(depth[i])
    #         hy2b_dry_correction_con.append(hy2b_dry_correction[i])
    #         hy2b_wet_correction_con.append(hy2b_wet_correction[i])
    #         hy2b_iono_correction_con.append(hy2b_iono_correction[i])
    #         hy2b_ssb_correction_con.append(hy2b_ssb_correction[i])
    #         hy2b_altuv_correction_con.append(hy2b_altuv_correction[i])
    #         hy2b_raduv_correction_con.append(hy2b_raduv_correction[i])
    #         hy2b_swhku_correction_con.append(hy2b_swhku_correction[i])
    #         hy2b_oceantide_correction_con.append(hy2b_oceantide_correction[i])
    #         hy2b_loadtide_correction_con.append(hy2b_loadtide_correction[i])
    #         hy2b_solidtide_correction_con.append(hy2b_solidtide_correction[i])
    #         hy2b_poletide_correction_con.append(hy2b_poletide_correction[i])
    #         hy2b_inv_correction_con.append(hy2b_inv_correction[i])
    #         hy2b_alt_con.append(hy2b_alt[i])
    
    '''Step5'''
    print('step' + matchFlowConfig['step'][4]['stepNo'] + ': ' + matchFlowConfig['step'][4]['stepName'])
    '''模式数据读取'''
    '''干大气重处理'''
    #ecmwf_dry_correction = dryreprocessed_correction(hy2b_time_con,hy2b_lon_con,hy2b_lat_con,conf_dict)
    '''湿大气重处理'''
    
    '''电离层重处理'''
    
    '''海况偏差重处理'''
    
    '''海面高度'''
  
            
    '''写Pkl文件'''
    # correction = {
    #       "satId": "HY-2B",
    #       "sensorId": "ALT",
    #       "Level": "L2P",
    #       "algo_name": " H2B_OPER_GDR_2PC",
    #       "algo_version": " GDR_2PC",
    #       "message": "SUCCESS",
    #       "organization": "ht",
    #       "programmer": "郑广东",
    #       "responsibler": "马纯永",
    #        "result" : [
    #           {
    #               "filePath":"..\..\outPath\ResultOut\HY-2B_{}_Saved.pkl".format(files),
    #               "meta":{
    #                   "aux":"",
    #                   "Time_range":"",
    #                   "endTime":"",
    #                   "extent":"",
    #                   "main":"",
    #                   "parameter":"",
    #                   "productionTime":"",
    #                   "size" : 233,
    #                   "startTime" : "201811250T003929",
    #                   },
    #               "typeid" : "HY2_ALT_GDR " 
                      
    #           }
    #        ]

    #     } 
    # with open(conf_dict["resultJsonFile"],"w") as f:
    #     f.write(json.dumps(correction,indent=4))
    '''模式数据检验结果存储'''
    # matchResult = {
    #     "LON": LON,
    #     "LAT": LAT,
    #     "TIME": {"HY2B":TIME,"JASON-3":TIME1},
    #     "ALT":{"HY2B":ALT,"JASON-3":ALT1},
    #     "Range_ku":{"HY2B":RANGE,"JASON-3":RANGE1},
    #     "DRY":{"HY2B":DRY,"JASON-3":DRY1},
    #     "WET":{"HY2B":WET,"JASON-3":WET1},
    #     "IONO":{"HY2B":IONO,"JASON-3":IONO1},
    #     "SSB":{"HY2B":SSB,"JASON-3":SSB1},
    #     "WS":{"HY2B":WS,"JASON-3":WS1},
    #     "SWH":{"HY2B":SWH,"JASON-3":SWH1},
    #     "SSH":{"HY2B":SWH,"JASON-3":SWH1}
    # }
    matchResult = {
        "LON": LON,
        "LAT": LAT,
        "TIME": {"HY2B": TIME, files: TIME1},
        "ALT": {"HY2B": ALT, files: ALT1},
        "Range_ku": {"HY2B": RANGE, files: RANGE1},
        "DRY": {"HY2B": DRY, files: DRY1},
        "WET": {"HY2B": WET, files: WET1},
        "IONO": {"HY2B": IONO, files: IONO1},
        "SSB": {"HY2B": SSB, files: SSB1},
        "WS": {"HY2B": WS, files: WS1},
        "SWH": {"HY2B": SWH, files: SWH1},
        "SSH": {"HY2B": SSH, files: SSH1}
    }
    # matchResult = {
    #     "Lon":,
    #     "Lat":,
    #     "Time":{"HY2B":TIME ,"JASON-3":TIME1},
    #     "Alt":{"HY2B":ALT,"JASON-3":ALT1},
    #     "Range_ku":{"HY2B":RANGE,"JASON-3":RANGE1},
    #     "Dry":{"HY2B":,"JASON-3":},
    #     "Wet":{"HY2B":"","ECMWF":""},
    #     "Iono":{"HY2B":"","ECMWF":""},
    #     "SSB":{"HY2B":"","ECMWF":""},
    #     "WS":{"HY2B":"","ECMWF":""},
    #     "SWH":{"HY2B":"","ECMWF":""},
    #     "SSH":{"HY2B":"","ECMWF":""}
    #     }
    # with open(conf_dict["resultFolder"] + "HY-2B_JASON-3_Saved.pkl","wb") as f1:
    #     pkl.dump(matchResult,f1)
    # with open(conf_dict["resultFolder"] +"\\"+"HY-2B_Saral"+"\\"+ "HY-2B_{}_{}_Saved.pkl".format(files,h2b_matrix1[0]['time_extract'][0]),"wb") as f1:
    #     pkl.dump(matchResult,f1)
    # with open(conf_dict["resultFolder"] +"\\"+"HY-2B_JASON-3"+"\\"+ "HY-2B_{}_{}_Saved.pkl".format(files,h2b_matrix1[0]['time_extract'][0]),"wb") as f1:
    #     pkl.dump(matchResult,f1)
    with open(conf_dict["resultFolder"] +"\\"+"HY-2B_{}".format(files)+"\\"+ "HY-2B_{}_{}_Saved.pkl".format(files,h2b_matrix1[0]['time_extract'][0]),"wb") as f1:
        pkl.dump(matchResult,f1)




    filePath = r'\HY2BV0\Validation\SatelliteCross\HY2B\outPath\ResultOut\HY-2B_{}'.format(files)
    filename = os.listdir(filePath)
    DRY = []
    DRY1 = []
    SSH = []
    SSH1 = []
    WET = []
    WET1 = []
    IONO = []
    IONO1 = []
    SSB = []
    SSB1 = []
    WS = []
    WS1 = []
    SWH = []
    SWH1 = []
    if files == 'Saral':
        for i in range(0,len(filename)):
            flag = True
            if '20190501'<= filename[i][12:20] <='20190507':
                zzfile = filePath + '\\' + filename[i]
                inf = pickle.load(open(zzfile, 'rb'))
                a = (inf['DRY']['HY2B'])
                b = (inf['DRY']['Saral'])
                c = (inf['SSH']['HY2B'])
                d = (inf['SSH']['Saral'])
                w = (inf['WET']['HY2B'])
                w1 = (inf['WET']['Saral'])
                I = (inf['IONO']['HY2B'])
                I1 = (inf['IONO']['Saral'])
                e = (inf['SSB']['HY2B'])
                e1 = (inf['SSB']['Saral'])
                f = (inf['WS']['HY2B'])
                f1 = (inf['WS']['Saral'])
                g = (inf['SWH']['HY2B'])
                g1 = (inf['SWH']['Saral'])
                flag = False
            if flag == False:
                DRY.extend(a)
                DRY1.extend(b)
                SSH.extend(c)
                SSH1.extend(d)
                WET.extend(w)
                WET1.extend(w1)
                IONO.extend(I)
                IONO1.extend(I1)
                SSB.extend(e)
                SSB1.extend(e1)
                WS.extend(f)
                WS1.extend(f1)
                SWH.extend(g)
                SWH1.extend(g1)
        M = np.array(DRY)
        N = np.array(DRY1)
        O = np.array(SSH)
        P = np.array(SSH1)
        W = np.array(WET)
        W1 = np.array(WET1)
        R = np.array(IONO)
        S = np.array(IONO1)
        B = np.array(SSB)
        B1 = np.array(SSB1)
        C = np.array(WS)
        C1 = np.array(WS1)
        D = np.array(SWH)
        D1 = np.array(SWH1)
        result = {
                "DRY":{"HY2B":M ,"Saral":N},
                "SSH":{"HY2B":O,"Saral":P},
                "WET":{"HY2B":W,"Saral":W1},
                "IONO":{"HY2B":R,"Saral":S},
                "SSB":{"HY2B":B,"Saral":B1},
                "WS":{"HY2B":C,"Saral":C1},
                "SWH":{"HY2B":D,"Saral":D1}
                }
        with open(r'\HY2BV0\Validation\SatelliteCross\HY2B\outPath\ResultOut\HY-2B_{}\{}_Saved.pkl'.format(files,filename[-1][12:20]),"wb") as f1:
            pkl.dump(result, f1)

    elif files == 'JASON-3':
        for i in range(0,len(filename)):
            flag = True
            if '20190501'<= filename[i][14:22] <='20190507':
                zzfile = filePath + '\\' + filename[i]
                inf = pickle.load(open(zzfile, 'rb'))
                a = (inf['DRY']['HY2B'])
                b = (inf['DRY']['JASON-3'])
                c = (inf['SSH']['HY2B'])
                d = (inf['SSH']['JASON-3'])
                w = (inf['WET']['HY2B'])
                w1 = (inf['WET']['JASON-3'])
                I = (inf['IONO']['HY2B'])
                I1 = (inf['IONO']['JASON-3'])
                e = (inf['SSB']['HY2B'])
                e1 = (inf['SSB']['JASON-3'])
                f = (inf['WS']['HY2B'])
                f1 = (inf['WS']['JASON-3'])
                g = (inf['SWH']['HY2B'])
                g1 = (inf['SWH']['JASON-3'])
                flag = False
            if flag == False:
                DRY.extend(a)
                DRY1.extend(b)
                SSH.extend(c)
                SSH1.extend(d)
                WET.extend(w)
                WET1.extend(w1)
                IONO.extend(I)
                IONO1.extend(I1)
                SSB.extend(e)
                SSB1.extend(e1)
                WS.extend(f)
                WS1.extend(f1)
                SWH.extend(g)
                SWH1.extend(g1)
        M = np.array(DRY)
        N = np.array(DRY1)
        O = np.array(SSH)
        P = np.array(SSH1)
        W = np.array(WET)
        W1 = np.array(WET1)
        R = np.array(IONO)
        S = np.array(IONO1)
        B = np.array(SSB)
        B1 = np.array(SSB1)
        C = np.array(WS)
        C1 = np.array(WS1)
        D = np.array(SWH)
        D1 = np.array(SWH1)
        result = {
                "DRY":{"HY2B":M ,"JASON-3":N},
                "SSH":{"HY2B":O,"JASON-3":P},
                "WET":{"HY2B":W,"JASON-3":W1},
                "IONO":{"HY2B":R,"JASON-3":S},
                "SSB": {"HY2B": B, "Saral": B1},
                "WS": {"HY2B": C, "Saral": C1},
                "SWH": {"HY2B": D, "Saral": D1}
                }
        # with open(r'E:\pythonProject\HY2B\HY2B\outPath\ResultOut\HY-2B_{}\jianyan\{}_Saved.pkl'.format(files,max(filename[i][14:22])),"wb") as f1:
        #     pkl.dump(result, f1)
        with open(r'\HY2BV0\Validation\SatelliteCross\HY2B\outPath\ResultOut\HY-2B_{}\{}_Saved.pkl'.format(files,filename[-1][14:22]),"wb") as f1:
            pkl.dump(result, f1)

    elif files == 'Sentinel-3A':
        for i in range(0,len(filename)):
            flag = True
            if  '20190501' <= filename[i][18:26] <= '20190507':
                zzfile = filePath + '\\' + filename[i]
                inf = pickle.load(open(zzfile, 'rb'))
                a = (inf['DRY']['HY2B'])
                b = (inf['DRY']['Sentinel-3A'])
                c = (inf['SSH']['HY2B'])
                d = (inf['SSH']['Sentinel-3A'])
                w = (inf['WET']['HY2B'])
                w1 = (inf['WET']['Sentinel-3A'])
                I = (inf['IONO']['HY2B'])
                I1 = (inf['IONO']['Sentinel-3A'])
                e = (inf['SSB']['HY2B'])
                e1 = (inf['SSB']['Sentinel-3A'])
                f = (inf['WS']['HY2B'])
                f1 = (inf['WS']['Sentinel-3A'])
                g = (inf['SWH']['HY2B'])
                g1 = (inf['SWH']['Sentinel-3A'])
                flag = False
            if flag == False:
                DRY.extend(a)
                DRY1.extend(b)
                SSH.extend(c)
                SSH1.extend(d)
                WET.extend(w)
                WET1.extend(w1)
                IONO.extend(I)
                IONO1.extend(I1)
                SSB.extend(e)
                SSB1.extend(e1)
                WS.extend(f)
                WS1.extend(f1)
                SWH.extend(g)
                SWH1.extend(g1)
        M = np.array(DRY)
        N = np.array(DRY1)
        O = np.array(SSH)
        P = np.array(SSH1)
        W = np.array(WET)
        W1 = np.array(WET1)
        R = np.array(IONO)
        S = np.array(IONO1)
        B = np.array(SSB)
        B1 = np.array(SSB1)
        C = np.array(WS)
        C1 = np.array(WS1)
        D = np.array(SWH)
        D1 = np.array(SWH1)
        result = {
            "DRY": {"HY2B": M, "Sentinel-3A": N},
            "SSH": {"HY2B": O, "Sentinel-3A": P},
            "WET": {"HY2B": W, "Sentinel-3A": W1},
            "IONO": {"HY2B": R, "Sentinel-3A": S},
            "SSB": {"HY2B": B, "Saral": B1},
            "WS": {"HY2B": C, "Saral": C1},
            "SWH": {"HY2B": D, "Saral": D1}
        }
        with open(r'\HY2BV0\Validation\SatelliteCross\HY2B\outPath\ResultOut\HY-2B_{}\{}_Saved.pkl'.format(files,filename[-1][18:26]),"wb") as f1:
            pkl.dump(result, f1)

    #     #'20190501' <= filename[i][12:20] <= '20190507'
    #     #if filename[i][6:11] == 'Saral' and len(filename[i]) == 36 and '20190501'<= filename[i][12:20] <='20190507':
    #     #if filename[i][6:13] == 'JASON-3' and '20190501' <= filename[i][14:22] <= '20190507':
    #     if filename[i][6:17] == 'Sentinel-3A' and '20190501' <= filename[i][18:26] <= '20190507':
    #         zzfile = filePath + '\\'+ filename[i]
    #         inf=pickle.load(open(zzfile,'rb'))
    #         a = (inf['DRY']['HY2B'])
    #         #b = (inf['DRY']['Saral'])
    #         #b = (inf['DRY']['JASON-3'])
    #         b = (inf['DRY']['Sentinel-3A'])
    #         c = (inf['SSH']['HY2B'])
    #         #d = (inf['SSH']['Saral'])
    #         #d = (inf['SSH']['JASON-3'])
    #         d = (inf['SSH']['Sentinel-3A'])
    #         w = (inf['WET']['HY2B'])
    #         #w1 = (inf['WET']['Saral'])
    #         #w1 = (inf['WET']['JASON-3'])
    #         w1 = (inf['WET']['Sentinel-3A'])
    #         I = (inf['IONO']['HY2B'])
    #         #I1 = (inf['IONO']['Saral'])
    #         #I1 = (inf['IONO']['JASON-3'])
    #         I1 = (inf['IONO']['Sentinel-3A'])
    #         # a1 = [str(i) for i in a]  # 使用列表推导式把列表中的单个元素全部转化为str类型
    #         # b1 = [str(i) for i in b]  # 使用列表推导式把列表中的单个元素全部转化为str类型
    #         flag = False
    #     if flag ==False:
    #         DRY.extend(a)
    #         DRY1.extend(b)
    #         SSH.extend(c)
    #         SSH1.extend(d)
    #         WET.extend(w)
    #         WET1.extend(w1)
    #         IONO.extend(I)
    #         IONO1.extend(I1)
    # M = np.array(DRY)
    # N = np.array(DRY1)
    # O = np.array(SSH)
    # P = np.array(SSH1)
    # W = np.array(WET)
    # W1 = np.array(WET1)
    # R = np.array(IONO)
    # S = np.array(IONO1)
    # # result = {
    # #     "DRY":{"HY2B":M ,"Saral":N},
    # #     "SSH":{"HY2B":O,"Saral":P},
    # #     "WET":{"HY2B":W,"Saral":W1},
    # #     "IONO":{"HY2B":R,"Saral":S}
    # #     }
    # # result = {
    # #     "DRY": {"HY2B": M, "JASON-3": N},
    # #     "SSH": {"HY2B": O, "JASON-3": P},
    # #     "WET": {"HY2B": W, "JASON-3": W1},
    # #     "IONO": {"HY2B": R, "JASON-3": S}
    # # }
    # result = {
    #     "DRY": {"HY2B": M, "Sentinel-3A": N},
    #     "SSH": {"HY2B": O, "Sentinel-3A": P},
    #     "WET": {"HY2B": W, "Sentinel-3A": W1},
    #     "IONO": {"HY2B": R, "Sentinel-3A": S}
    # }
    # with open(r'E:\pythonProject\HY2B\HY2B\outPath\ResultOut\HY-2B_Sentinel-3A\jianyan\{}_Saved.pkl'.format(filename[-1][18:26]),
    #           "wb") as f1:
    # # with open(r'C:\pythonProject1\HY2B\HY2B\outPath\ResultOut\{}_Saved.pkl'.format(filename[i][12:20]),
    # #           "wb") as f1:
    #     pkl.dump(result, f1)




    ResultInputFile = {
        "resultLogFile": "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\outPath\\Log\\u01028fa817be26547017be26daf320054.log",
        "resultJsonFile": "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\json\\Calculation\\CalculationResultInformation1\\",
        "taskType": "H2B_OPER_GDR_2PC",
        "resultFlowFile": "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\json\\Calculation\\CalculationFlowFile\\HY2B_ALT_GDRL2Flow.json",
        "mdss": [
            {
                "mds_type": "H2B_OPER_GDR_2PC-Saral",
                "files": [
                    "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\outPath\\ResultOut\\HY-2B_JASON-3\\{}_Saved.pkl".format(filename[-1][14:22]),
                    "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\outPath\\ResultOut\\HY-2B_Saral\\{}_Saved.pkl".format(filename[-1][12:20]),
                    "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\outPath\\ResultOut\\HY-2B_Sentinel-3A\\{}_Saved.pkl".format(filename[-1][18:26])
                ]
            }
        ],
        "resultFolder": "\\HY2BV0\\Validation\\SatelliteCross\\HY2B\\outPath\\ResultOut\\"
    }
    with open(r'\HY2BV0\Validation\SatelliteCross\HY2B\json\Calculation\jsonCalculationInputFile\ResultInputFile.json',"w") as f:
        f.write(json.dumps(ResultInputFile,indent=4))


#电离层数据读取
# def Tec_read(conf_dict):
#     '''
#     匹配数据集，以字典形式返回
#     :param key: TEC数据所处文件夹路径
#     :param value: TEC时间
#     :param conf_dict: 配置信息
#     :return: TEC数据集
#     '''
#     import re
#     import datetime
#     inputdir_iono = conf_dict['inputdir_iono']
#     files_jason3_txt = os.listdir(os.path.join(inputdir_iono))
#
#     tec_array = np.zeros((71, 73, 12*len(files_jason3_txt)), dtype=int)
#     #    print(tec_array.shape)
#     time_miao = []
#     j = 0
#     for files in files_jason3_txt:
#
#         f = open(inputdir_iono + files)
#         sfile = f.read()
#
#         # tec_day match iono duaring single day
#         tec_day = re.split(r'(?m)^\s*\d{1,2}\s*START OF TEC MAP\s*$', sfile)
#     #        tec_day_0 = tec_day[1:-1]
#         time_day = []
#         if j < len(files_jason3_txt):
#             for i,item in enumerate(tec_day[1:-1]):
#         #        print(i)
# #                if tec_array[i + 12*j,i + 12*j,i + 12*j] == 0:
#                 tec_2hour_split = re.split(r'\s*[\d\-\.]+-180.0 180.0   5.0 450.0                            LAT/LON1/LON2/DLON/H', item)
#
#                 for n,item_lat in enumerate(tec_2hour_split[1:]):
#                     lat_split = re.sub(r'[\na-zA-Z]', '', item_lat)
#                     tec_array[n, :, i + 12*j] = list(map(int,lat_split.split()))[:73]
#         #            if tec_array[12,0,11]
#
#                 for n,item_lat in enumerate(tec_2hour_split[0:1]):
#                     lat_split = re.sub(r'[\na-zA-Z]', '', item_lat)
#                     time_day.append(lat_split.split())
#         j = j + 1
#
#         d1 = datetime.datetime(2000, 1, 1)
#         for i in range(len(time_day)):
#             year = int(time_day[i][0])
#             mouth = int(time_day[i][1])
#             day = int(time_day[i][2])
#             hour = int(time_day[i][3])
#         #    print(hour)
#             d2 = datetime.datetime(year,mouth,day)
#     #            chazhi = ((d2 - d1).days*24 + hour)*3600
#         #    print(((d2 - d1).days*24 + hour))
#             time_miao.append(((d2 - d1).days*24 + hour))
#     return time_miao,tec_array




def selectMatchResult(conf_dict,files):
    input1 = r'\HY2BV0\Validation\SatelliteCross\HY2B\json\Match\jsonMatchInputFile\matchInputFile.json'
    with open(input1) as input11:
        input111 = json.load(input11)
    # #input = input111['auxFile'][2] #Saral
    # input = input111['auxFile'][3]
    inputdir = input111['primaryFile']
    files_ = os.path.basename(inputdir)
    h2b_time = time_extract(files_)
    # directory, module_name = os.path.split(input)
    # files = os.path.basename(directory)
    if files == 'JASON-3':
        with open(conf_dict['mdss'][0]['files'][0], "rb") as f:
            matchData = pkl.load(f)
        # input = conf_dict['auxFile'][4]
        # directory, module_name = os.path.split(input)
        # files = os.path.basename(directory)
        # with open(r'C:\pythonProject1\HY2B\HY2B\outPath\ResultOut\HY-2B_JASON-3\20190504_Saved.pkl', "rb") as f:
        #     matchData = pkl.load(f)
        for key in matchData.keys():
            if key == 'LON' or key == 'LAT' or key == 'TIME' or key == 'ALT' or key == 'Range_ku':
                continue
            else:
                HY2BDRY = matchData[key]['HY2B']
                JASON3DRY = matchData[key][files]
                HY2BDryCorrection_con, JASON3DryCorrection_con = [], []
                diff = []
                for i in range(len(HY2BDRY)):
                    HY2BDryCorrection_con.append(HY2BDRY[i])
                    JASON3DryCorrection_con.append(JASON3DRY[i])
                    diff.append(HY2BDryCorrection_con[i] - JASON3DryCorrection_con[i])
                huatu(diff, HY2BDryCorrection_con, JASON3DryCorrection_con, conf_dict, key, files,h2b_time)

    elif files == 'Saral':
        with open(conf_dict['mdss'][0]['files'][1], "rb") as f:
            matchData = pkl.load(f)
        # with open(r'C:\pythonProject1\HY2B\HY2B\outPath\ResultOut\HY-2B_Saral\20190504_Saved.pkl', "rb") as f:
        #     matchData = pkl.load(f)
        # input1 = r'C:\pythonProject1\HY2B\HY2B\json\Match\jsonMatchInputFile\matchInputFile.json'
        # with open(input1) as input11:
        #     input111 = json.load(input11)
        # input = input111['auxFile'][2]  # Saral
        # directory, module_name = os.path.split(input)
        # files = os.path.basename(directory)
        for key in matchData.keys():
            if key == 'LON' or key == 'LAT' or key == 'TIME' or key == 'ALT' or key == 'Range_ku':
                continue
            else:
                HY2BDRY = matchData[key]['HY2B']
                JASON3DRY = matchData[key][files]
                HY2BDryCorrection_con, JASON3DryCorrection_con = [], []
                diff = []
                for i in range(len(HY2BDRY)):
                    HY2BDryCorrection_con.append(HY2BDRY[i])
                    JASON3DryCorrection_con.append(JASON3DRY[i])
                    diff.append(HY2BDryCorrection_con[i] - JASON3DryCorrection_con[i])
                huatu(diff, HY2BDryCorrection_con, JASON3DryCorrection_con, conf_dict, key,files,h2b_time)

    elif files == 'Sentinel-3A':
        with open(conf_dict['mdss'][0]['files'][2], "rb") as f:
            matchData = pkl.load(f)
        # input1 = r'C:\pythonProject1\HY2B\HY2B\json\Match\jsonMatchInputFile\matchInputFile.json'
        # with open(input1) as input11:
        #     input111 = json.load(input11)
        # input = input111['auxFile'][2]  # Saral
    # with open(conf_dict['mdss'][0]['files'][0],"rb") as f:
    #     matchData = pkl.load(f)
    # rangeKu = matchData['Range_ku']
    # rangeKu = list(np.nan_to_num(rangeKu))
    #depth = matchData['Depth']
        directory, module_name = os.path.split(input)
        files = os.path.basename(directory)
        for key in matchData.keys():
            if key == 'LON' or key == 'LAT' or key == 'TIME' or key == 'ALT' or key == 'Range_ku' :
                continue
            else:
                # fig_save_path = ('{}'.format(conf_dict['resultFolder'], key))
                # comshow(matchData[key], key, fig_save_path, conf_dict)
            # if key == 'Dry':
                HY2BDRY = matchData[key]['HY2B']
                #JASON3DRY = matchData[key]['JASON-3']
                JASON3DRY = matchData[key][files]
                HY2BDryCorrection_con, JASON3DryCorrection_con = [], []
                diff = []
                for i in range(len(HY2BDRY)):
                    HY2BDryCorrection_con.append(HY2BDRY[i])
                    JASON3DryCorrection_con.append(JASON3DRY[i])
                    diff.append(HY2BDryCorrection_con[i]-JASON3DryCorrection_con[i])
            #     print(1111)
            #     # range1 = 0.01
            #     # HY2BDryCorrection = matchData[key]['HY2B']
            #     # ECMWFDryCorrection = matchData[key]['ECMWF']
            #     # HY2BDryCorrection_con,ECMWFDryCorrection_con = [],[]
            #     # diff = []
            #     # for i in range(len(HY2BDryCorrection)):
            #     #     if rangeKu[i] != 0 and abs(HY2BDryCorrection[i] - ECMWFDryCorrection[i]) <= range1:
            #     #         HY2BDryCorrection_con.append(HY2BDryCorrection[i])
            #     #         ECMWFDryCorrection_con.append(ECMWFDryCorrection[i])
            #     #         diff.append(HY2BDryCorrection[i] - ECMWFDryCorrection[i])
            #     '''出图'''
                huatu(diff,HY2BDryCorrection_con,JASON3DryCorrection_con,conf_dict,key,files,h2b_time)
    
    
    
    