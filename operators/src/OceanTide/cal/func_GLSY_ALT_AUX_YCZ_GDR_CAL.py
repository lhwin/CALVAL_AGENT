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



def func_ycz_cal_pro(ipf_config):
    # 非打包情况下使用
    # current_dir = os.getcwd()
    # 打包时使用
    # current_dir = sys._MEIPASS
    current_dir = os.getcwd()  # 注释：覆盖MEIPASS路径，打包后找不到字体
    current_dir = os.path.abspath(current_dir)
    try:
        fontTTF = os.path.join(current_dir, "config", "simhei.ttf")
        font_prop = FontProperties(fname=fontTTF)
    except:
        fontTTF = os.path.join("../", "config", "simhei.ttf")
        font_prop = FontProperties(fname=fontTTF)
    font_prop = FontProperties(fname=fontTTF)
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
    Logger.info("Get file list in input directory within specified time range")
    # 根据关键字ipf_config.Sat_ID和起止时间ipf_config.Start_date和ipf_config.End_date获取输入目录下在这个时间范围的文件列表
    input_file_list = get_file_list(ipf_config.input, ipf_config.Match_Data_Type, ipf_config.Start_date,
                                    ipf_config.End_date)

    Logger.info("Start data reading")

    Logger.info("Start data calabrating")

    # ========================== 新增的工程化计算引擎代码开始 ==========================
    # --------- 1. 潮汐数学预报与椭球转换引擎 ---------
    def _t_astron(jdmid):
        d = jdmid - 693961.5
        D = d / 10000.0
        args = np.array([1.0, d, D * D, D ** 3])
        sc = np.array([270.434164, 13.1763965268, -0.0000850, 0.000000039])
        hc = np.array([279.696678, 0.9856473354, 0.00002267, 0.0])
        pc = np.array([334.329556, 0.1114040803, -0.0007739, -0.00000026])
        npc = np.array([-259.183275, 0.0529539222, -0.0001557, -0.00000005])
        ppc = np.array([281.220844, 0.0000470684, 0.0000339, 0.00000007])
        coeffs = np.vstack([sc, hc, pc, npc, ppc])
        astro_5 = np.mod(coeffs @ args / 360.0, 1.0)
        s_c, h_c, p_c, np_c, pp_c = astro_5
        tau_c = np.mod(jdmid % 1.0 + h_c - s_c, 1.0)
        return np.array([tau_c, s_c, h_c, p_c, np_c, pp_c])

    _SAT = {
        'M2': [{'dd': [-1, -1, 0], 'pc': 0.75, 'ar': 0.0001, 'lf': 2},
               {'dd': [-1, 0, 0], 'pc': 0.75, 'ar': 0.0004, 'lf': 2},
               {'dd': [0, -2, 0], 'pc': 0.00, 'ar': 0.0005, 'lf': 0},
               {'dd': [0, -1, 0], 'pc': 0.50, 'ar': 0.0373, 'lf': 0},
               {'dd': [1, -1, 0], 'pc': 0.25, 'ar': 0.0001, 'lf': 2},
               {'dd': [1, 0, 0], 'pc': 0.75, 'ar': 0.0009, 'lf': 2},
               {'dd': [1, 1, 0], 'pc': 0.75, 'ar': 0.0002, 'lf': 2},
               {'dd': [2, 0, 0], 'pc': 0.00, 'ar': 0.0006, 'lf': 0},
               {'dd': [2, 1, 0], 'pc': 0.00, 'ar': 0.0002, 'lf': 0}],
        'S2': [{'dd': [0, -1, 0], 'pc': 0.00, 'ar': 0.0022, 'lf': 0},
               {'dd': [1, 0, 0], 'pc': 0.75, 'ar': 0.0001, 'lf': 2},
               {'dd': [2, 0, 0], 'pc': 0.00, 'ar': 0.0001, 'lf': 0}],
        'N2': [{'dd': [-2, -2, 0], 'pc': 0.50, 'ar': 0.0039, 'lf': 0},
               {'dd': [-1, 0, 1], 'pc': 0.00, 'ar': 0.0008, 'lf': 0},
               {'dd': [0, -2, 0], 'pc': 0.00, 'ar': 0.0005, 'lf': 0},
               {'dd': [0, -1, 0], 'pc': 0.50, 'ar': 0.0373, 'lf': 0}],
        'K2': [{'dd': [-1, 0, 0], 'pc': 0.75, 'ar': 0.0024, 'lf': 2},
               {'dd': [-1, 1, 0], 'pc': 0.75, 'ar': 0.0004, 'lf': 2},
               {'dd': [0, -1, 0], 'pc': 0.50, 'ar': 0.0128, 'lf': 0},
               {'dd': [0, 1, 0], 'pc': 0.00, 'ar': 0.2980, 'lf': 0},
               {'dd': [0, 2, 0], 'pc': 0.00, 'ar': 0.0324, 'lf': 0}],
        'K1': [{'dd': [-2, -1, 0], 'pc': 0.00, 'ar': 0.0002, 'lf': 0},
               {'dd': [-1, -1, 0], 'pc': 0.75, 'ar': 0.0001, 'lf': 1},
               {'dd': [-1, 0, 0], 'pc': 0.25, 'ar': 0.0007, 'lf': 1},
               {'dd': [-1, 1, 0], 'pc': 0.75, 'ar': 0.0001, 'lf': 1},
               {'dd': [0, -2, 0], 'pc': 0.00, 'ar': 0.0001, 'lf': 0},
               {'dd': [0, -1, 0], 'pc': 0.50, 'ar': 0.0198, 'lf': 0},
               {'dd': [0, 1, 0], 'pc': 0.00, 'ar': 0.1356, 'lf': 0},
               {'dd': [0, 2, 0], 'pc': 0.50, 'ar': 0.0029, 'lf': 0},
               {'dd': [1, 0, 0], 'pc': 0.25, 'ar': 0.0002, 'lf': 1},
               {'dd': [1, 1, 0], 'pc': 0.25, 'ar': 0.0001, 'lf': 1}],
        'O1': [{'dd': [-1, 0, 0], 'pc': 0.25, 'ar': 0.0003, 'lf': 1},
               {'dd': [0, -2, 0], 'pc': 0.50, 'ar': 0.0058, 'lf': 0},
               {'dd': [0, -1, 0], 'pc': 0.00, 'ar': 0.1885, 'lf': 0},
               {'dd': [1, -1, 0], 'pc': 0.25, 'ar': 0.0004, 'lf': 1},
               {'dd': [1, 0, 0], 'pc': 0.75, 'ar': 0.0029, 'lf': 1},
               {'dd': [1, 1, 0], 'pc': 0.25, 'ar': 0.0004, 'lf': 1},
               {'dd': [2, 0, 0], 'pc': 0.50, 'ar': 0.0064, 'lf': 0},
               {'dd': [2, 1, 0], 'pc': 0.50, 'ar': 0.0010, 'lf': 0}],
        'P1': [{'dd': [0, -2, 0], 'pc': 0.00, 'ar': 0.0008, 'lf': 0},
               {'dd': [0, -1, 0], 'pc': 0.50, 'ar': 0.0112, 'lf': 0},
               {'dd': [0, 0, 2], 'pc': 0.50, 'ar': 0.0004, 'lf': 0},
               {'dd': [1, 0, 0], 'pc': 0.75, 'ar': 0.0004, 'lf': 1},
               {'dd': [2, 0, 0], 'pc': 0.50, 'ar': 0.0015, 'lf': 0},
               {'dd': [2, 1, 0], 'pc': 0.50, 'ar': 0.0003, 'lf': 0}],
        'Q1': [{'dd': [-2, -3, 0], 'pc': 0.50, 'ar': 0.0007, 'lf': 0},
               {'dd': [-2, -2, 0], 'pc': 0.50, 'ar': 0.0039, 'lf': 0},
               {'dd': [-1, -2, 0], 'pc': 0.75, 'ar': 0.0010, 'lf': 1},
               {'dd': [-1, -1, 0], 'pc': 0.75, 'ar': 0.0115, 'lf': 1},
               {'dd': [-1, 0, 0], 'pc': 0.75, 'ar': 0.0292, 'lf': 1},
               {'dd': [0, -2, 0], 'pc': 0.50, 'ar': 0.0057, 'lf': 0},
               {'dd': [-1, 0, 1], 'pc': 0.00, 'ar': 0.0008, 'lf': 0},
               {'dd': [0, -1, 0], 'pc': 0.00, 'ar': 0.1884, 'lf': 0},
               {'dd': [1, 0, 0], 'pc': 0.75, 'ar': 0.0018, 'lf': 1},
               {'dd': [2, 0, 0], 'pc': 0.50, 'ar': 0.0028, 'lf': 0}],
    }

    _DOODSON_SEMI = {
        'M2': (np.array([2, 0, 0, 0, 0, 0]), 0.0), 'S2': (np.array([2, 2, -2, 0, 0, 0]), 0.0),
        'N2': (np.array([2, -1, 0, 1, 0, 0]), 0.0), 'K2': (np.array([2, 2, 0, 0, 0, 0]), 0.0),
        'K1': (np.array([1, 1, 0, 0, 0, 0]), -0.75), 'O1': (np.array([1, -1, 0, 0, 0, 0]), -0.25),
        'P1': (np.array([1, 1, -2, 0, 0, 0]), -0.25), 'Q1': (np.array([1, -2, 0, 1, 0, 0]), -0.25),
    }

    def _fu_from_satellites(name, astro, lat):
        sats = _SAT.get(name, [])
        if not sats: return 0.0, 1.0
        slat = np.sin(np.pi * lat / 180) if lat is not None else None
        fsum = 1.0 + 0j
        for s in sats:
            rr = s['ar'];
            lf = s['lf']
            if slat is not None:
                if lf == 1:
                    rr *= 0.36309 * (1.0 - 5.0 * slat * slat) / slat
                elif lf == 2:
                    rr *= 2.59808 * slat
            elif lf > 0:
                rr = 0.0
            dd = np.array(s['dd'], dtype=float)
            uu = np.mod(dd @ astro[3:6] + s['pc'], 1.0)
            fsum += rr * np.exp(1j * 2 * np.pi * uu)
        return np.angle(fsum) / (2 * np.pi), abs(fsum)

    def get_tidal_constants():
        return {'name': ['M2 ', 'S2 ', 'N2 ', 'K2 ', 'K1 ', 'O1 ', 'P1 ', 'Q1 ', 'M4 ', 'M6 '],
                'doodson': [[2, 0, 0, 0, 0, 0], [2, 2, -2, 0, 0, 0], [2, -1, 0, 1, 0, 0], [2, 2, 0, 0, 0, 0],
                            [1, 1, 0, 0, 0, 0], [1, -1, 0, 0, 0, 0], [1, 1, -2, 0, 0, 0], [1, -2, 0, 1, 0, 0],
                            [4, 0, 0, 0, 0, 0], [6, 0, 0, 0, 0, 0]]}

    def t_vuf(jdmid, ju, lat=None):
        astro = _t_astron(jdmid)
        const = get_tidal_constants()
        v_arr, u_arr, f_arr = np.zeros(len(ju)), np.zeros(len(ju)), np.ones(len(ju))
        dood_m2, semi_m2 = _DOODSON_SEMI['M2']
        v_m2 = np.mod(dood_m2 @ astro + semi_m2, 1.0)
        u_m2, f_m2 = _fu_from_satellites('M2', astro, lat)
        for k, idx in enumerate(ju):
            if idx <= 0 or idx > len(const['name']): continue
            name = const['name'][idx - 1].strip().upper()
            if name == 'M4':
                v_arr[k] = np.mod(2 * v_m2, 1.0); u_arr[k] = 2 * u_m2; f_arr[k] = f_m2 ** 2
            elif name == 'M6':
                v_arr[k] = np.mod(3 * v_m2, 1.0); u_arr[k] = 3 * u_m2; f_arr[k] = f_m2 ** 3
            elif name in _DOODSON_SEMI:
                dood, semi = _DOODSON_SEMI[name]
                v_arr[k] = np.mod(dood @ astro + semi, 1.0)
                u_arr[k], f_arr[k] = _fu_from_satellites(name, astro, lat)
            else:
                v_arr[k] = 0.0; u_arr[k] = 0.0; f_arr[k] = 1.0
        return v_arr, u_arr, f_arr

    def t_predic(tim, name, freq, tidecon, latitude=None):
        tim = np.atleast_1d(np.array(tim, dtype=float).copy())
        jdmid = np.mean(tim)
        ap = (tidecon[:, 0] / 2.0) * np.exp(-1j * np.deg2rad(tidecon[:, 2]))
        am = np.conj(ap)
        const_names = [n.strip().upper() for n in get_tidal_constants()['name']]
        ju = [const_names.index(name.strip().upper()) + 1 if name.strip().upper() in const_names else 0]
        if latitude is not None and abs(jdmid) > 1:
            v, u, f = t_vuf(jdmid, ju, lat=latitude)
        elif abs(jdmid) > 1:
            v, u, f = t_vuf(jdmid, ju)
        else:
            v, u, f = np.zeros(1), np.zeros(1), np.ones(1)
        ap = ap * f * np.exp(1j * 2 * np.pi * (u + v))
        am = am * f * np.exp(-1j * 2 * np.pi * (u + v))
        tim_rel = tim - jdmid
        yout = np.zeros(len(tim_rel), dtype=float)
        for i, t in enumerate(tim_rel):
            contribution_pos = ap * np.exp(1j * 2 * np.pi * freq * t * 24)
            contribution_neg = am * np.exp(-1j * 2 * np.pi * freq * t * 24)
            yout[i] = np.real(np.sum(contribution_pos + contribution_neg))
        return yout[0] if len(yout) == 1 else yout

    def datetime_to_datenum(dt):
        return dt.toordinal() + 366 + dt.hour / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0

    TIDAL_OMEGAS = {
        'M2': 0.0805114, 'S2': 0.0833333, 'N2': 0.0789992, 'K2': 0.0835615,
        'K1': 0.0417807, 'O1': 0.0387307, 'P1': 0.0415526, 'Q1': 0.0372185,
        'M4': 0.1610228, 'M6': 0.2415342
    }

    def compute_tide(tidecons_dict, timenum, lats):
        lats = np.atleast_1d(lats)
        total_tide = np.zeros(len(lats))
        for name, omega in TIDAL_OMEGAS.items():
            tcon = tidecons_dict[name]
            for i in range(len(lats)):
                if not np.isnan(tcon[i, 0]):
                    total_tide[i] += t_predic(timenum, name, omega, tcon[i:i + 1], latitude=lats[i])
        return total_tide if len(total_tide) > 1 else total_tide[0]

    def apply_ellipsoid(mss_raw, lats):
        lats = np.atleast_1d(lats)
        lat_rad = lats * np.pi / 180
        ellip_correction = ((6378136.3 - 6378137) * np.sin(lat_rad) ** 2 + (6356751.600563 - 6356752.31424518) * np.cos(
            lat_rad) ** 2)
        ans = mss_raw + ellip_correction
        return ans if len(ans) > 1 else ans[0]

    # --------- 2. 读取 NPZ 并执行分站点定标计算 ---------
    real_npz_files = []
    if os.path.isdir(ipf_config.input):
        for root_dir, _, files in os.walk(ipf_config.input):
            for f in files:
                if f.endswith('.npz') and 'MATCHED' in f:
                    real_npz_files.append(os.path.join(root_dir, f))

    if not real_npz_files:
        Logger.error("Error: Could not find .npz file from the matching phase.")
    else:
        npz_file = real_npz_files[0]
        Logger.info(f"Loading data payload: {os.path.basename(npz_file)}")
        data = np.load(npz_file, allow_pickle=True)
        match_records = data['match_records']

        site_biases = {
            'zhiwan': {'cycles': [], 'biases': [], 'dropped_cycles': []},
            'wailingding': {'cycles': [], 'biases': [], 'dropped_cycles': []},
            'dangan': {'cycles': [], 'biases': [], 'dropped_cycles': []}
        }

        seen_keys = set()

        for record in match_records:
            try:
                site_name = record['site_name'].lower()
                cycle = record['cycle']

                unique_key = f"{site_name}_{cycle}"
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                pass_time_str = record['pass_time_str']
                sshalt = record['sshalt']
                tide001 = record['tide001']
                lat_p = record['lat_p']
                lattg = record['lattg']
                mss_raw_tg = record['mss_raw_tg']
                mss_raw_alt = record['mss_raw_alt']
                tidecons_tg = record['tidecons_tg']
                tidecons_alt = record['tidecons_alt']

                timenum = datetime_to_datenum(datetime.strptime(pass_time_str, "%Y%m%d %H:%M:%S"))

                tidetg = compute_tide(tidecons_tg, timenum, [lattg]) * 0.01
                tidealt = compute_tide(tidecons_alt, timenum, lat_p) * 0.01
                dtide = tidealt - tidetg

                geoidtg = apply_ellipsoid(mss_raw_tg, lattg)
                geoid01 = apply_ellipsoid(mss_raw_alt, lat_p)
                dgeoid1 = geoid01 - geoidtg

                bias01 = sshalt - (tide001 + dgeoid1 + dtide)
                ppp = np.where((bias01 > 0.15) | (bias01 < -0.15))[0]
                bias01_clean = np.delete(bias01, ppp)

                if len(bias01_clean) > 0:
                    mean_bias = np.mean(bias01_clean)
                    if site_name in site_biases:
                        site_biases[site_name]['biases'].append(mean_bias)
                        site_biases[site_name]['cycles'].append(cycle)
                else:
                    if site_name in site_biases:
                        site_biases[site_name]['dropped_cycles'].append(cycle)
            except Exception as e:
                pass

        # --------- 3. 分站点结果汇总报告与排序 ---------
        res_txt = os.path.join(outputPath,
                               f"CAL_RESULT_PER_SITE_{ipf_config.Sat_ID}_{ipf_config.Start_date}_{ipf_config.End_date}.txt")
        all_biases_for_global = []
        global_mean, global_std = 0.0, 0.0

        with open(res_txt, 'w', encoding='utf-8') as f:
            f.write("Altimeter Absolute Calibration Report (Categorized by Site)\n")
            f.write("============================================================\n\n")

            for site, data in site_biases.items():
                if len(data['cycles']) > 0:
                    sorted_idx = np.argsort(data['cycles'])
                    sorted_cycles = np.array(data['cycles'])[sorted_idx]
                    sorted_biases = np.array(data['biases'])[sorted_idx]
                    sorted_dropped = sorted(data['dropped_cycles'])

                    data['cycles'] = sorted_cycles.tolist()
                    data['biases'] = sorted_biases.tolist()

                    site_mean = np.mean(sorted_biases)
                    site_std = np.std(sorted_biases)
                    all_biases_for_global.extend(sorted_biases.tolist())

                    f.write(f"Site: {site.upper()}\n")
                    f.write(f"Total Valid Passes: {len(sorted_biases)}\n")
                    f.write(f"Mean Bias: {site_mean:.4f} m\n")
                    f.write(f"Bias STD:  {site_std:.4f} m\n")
                    f.write(
                        f"Dropped Cycles (>0.15m limit): {', '.join(map(str, sorted_dropped)) if sorted_dropped else 'None'}\n")
                    f.write("Detail (Cycle, Bias):\n")
                    for c, b in zip(data['cycles'], data['biases']):
                        f.write(f"  {c}, {b:.4f}\n")
                    f.write("-" * 30 + "\n\n")

            all_biases_all = np.array(all_biases_for_global)
            if len(all_biases_all) > 0:
                global_mean = np.mean(all_biases_all)
                global_std = np.std(all_biases_all)
                f.write(f"GLOBAL SUMMARY\n")
                f.write(f"Total Valid Passes: {len(all_biases_all)}\n")
                f.write(f"Global Mean Bias: {global_mean:.4f} m\n")
                f.write(f"Global Bias STD:  {global_std:.4f} m\n")

        Logger.info(f"Categorized report saved to: {os.path.basename(res_txt)}")

        # --------- 4. 绘图：独立的趋势折线图、直方图以及各岛独立图 ---------
        colors = {'zhiwan': 'royalblue', 'wailingding': 'forestgreen', 'dangan': 'orange'}
        markers = {'zhiwan': 'o', 'wailingding': 's', 'dangan': '^'}

        # 4.1 生成大合集对比趋势图 (独立图片 1)
        try:
            plt.figure(figsize=(10, 6))
            for site, data in site_biases.items():
                if len(data['biases']) > 0:
                    plt.plot(data['cycles'], data['biases'],
                             color=colors.get(site, 'k'), marker=markers.get(site, 'o'),
                             linestyle='-', linewidth=1.5, markersize=6,
                             label=f"{site.upper()} (Mean: {np.mean(data['biases']):.4f}m)", alpha=0.8)

            if len(all_biases_for_global) > 0:
                plt.axhline(y=global_mean, color='crimson', linestyle='-', linewidth=2.5, label='Global Mean')

            plt.title(f"{ipf_config.Sat_ID} Altimeter Calibration Trend by Site", fontproperties=font_prop, fontsize=15)
            plt.xlabel("Cycle Number", fontproperties=font_prop, fontsize=13)
            plt.ylabel("Bias (m)", fontproperties=font_prop, fontsize=13)
            plt.grid(True, linestyle=':', alpha=0.6)
            plt.legend(prop=font_prop, loc='upper right', frameon=True, shadow=True)

            trend_path = os.path.join(outputPath,
                                      f"CAL_TREND_COMBINED_{ipf_config.Sat_ID}_{ipf_config.Start_date}_{ipf_config.End_date}.png")
            plt.savefig(trend_path, dpi=300, bbox_inches='tight')
            plt.close()
            Logger.info(f"Combined trend plot saved to: {os.path.basename(trend_path)}")
        except Exception as e:
            Logger.warn(f"Failed to generate combined trend plot: {e}")

        # 4.2 生成全局误差频率直方图 (独立图片 2)
        if len(all_biases_for_global) > 0:
            try:
                plt.figure(figsize=(8, 6))
                plt.hist(all_biases_for_global, bins=15, color='steelblue', alpha=0.7, edgecolor='black')

                plt.axvline(x=global_mean, color='crimson', linestyle='-', linewidth=2.5,
                            label=f'Mean: {global_mean:.4f}m')
                plt.axvline(x=global_mean + global_std, color='crimson', linestyle='--', linewidth=1.5,
                            label=f'+1 STD: {global_mean + global_std:.4f}m')
                plt.axvline(x=global_mean - global_std, color='crimson', linestyle='--', linewidth=1.5,
                            label=f'-1 STD: {global_mean - global_std:.4f}m')

                plt.title(f"{ipf_config.Sat_ID} Distribution of Calibration Biases", fontproperties=font_prop,
                          fontsize=15)
                plt.xlabel("Bias (m)", fontproperties=font_prop, fontsize=13)
                plt.ylabel("Frequency / count", fontproperties=font_prop, fontsize=13)
                plt.grid(True, linestyle=':', alpha=0.6)
                plt.legend(prop=font_prop, loc='upper right', frameon=True)

                hist_path = os.path.join(outputPath,
                                         f"CAL_HISTOGRAM_{ipf_config.Sat_ID}_{ipf_config.Start_date}_{ipf_config.End_date}.png")
                plt.savefig(hist_path, dpi=300, bbox_inches='tight')
                plt.close()
                Logger.info(f"Histogram plot saved to: {os.path.basename(hist_path)}")
            except Exception as e:
                Logger.warn(f"Failed to generate histogram plot: {e}")

        # 4.3 生成各岛屿的独立连线趋势图
        for site, data in site_biases.items():
            if len(data['biases']) > 0:
                try:
                    plt.figure(figsize=(10, 6))
                    site_color = colors.get(site, 'royalblue')
                    site_marker = markers.get(site, 'o')

                    biases_arr = np.array(data['biases'])
                    s_mean = np.mean(biases_arr)
                    s_std = np.std(biases_arr)

                    plt.plot(data['cycles'], data['biases'], linestyle='-', color=site_color,
                             marker=site_marker, markerfacecolor=site_color, markersize=6,
                             label=f'{site.upper()} Bias')

                    plt.axhline(y=s_mean, color='crimson', linestyle='-', linewidth=2, label=f'Mean: {s_mean:.4f}m')
                    plt.axhline(y=s_mean + s_std, color='crimson', linestyle='--', alpha=0.7,
                                label=f'+1 STD ({s_std:.4f}m)')
                    plt.axhline(y=s_mean - s_std, color='crimson', linestyle='--', alpha=0.7)

                    plt.title(f"{ipf_config.Sat_ID} Calibration Bias - {site.upper()}", fontproperties=font_prop,
                              fontsize=16)
                    plt.xlabel("Cycle Number", fontproperties=font_prop, fontsize=14)
                    plt.ylabel("Bias (m)", fontproperties=font_prop, fontsize=14)
                    plt.grid(True, linestyle=':', alpha=0.6)
                    plt.legend(prop=font_prop)

                    site_fig_path = os.path.join(outputPath,
                                                 f"CAL_TREND_{site.upper()}_{ipf_config.Sat_ID}_{ipf_config.Start_date}_{ipf_config.End_date}.png")
                    plt.savefig(site_fig_path, dpi=300, bbox_inches='tight')
                    plt.close()
                except Exception as e:
                    pass

        # ==================== 5. 生成JSON格式的标签文件 ====================
        Logger.info("生成JSON标签文件...")
        import json

        trend_img = trend_path.replace('\\', '/') if 'trend_path' in locals() else ""
        hist_img = hist_path.replace('\\', '/') if 'hist_path' in locals() else ""
        # 计算有效周期、被剔除周期、总匹配周期及百分比
        valid_num = len(all_biases_all) if 'all_biases_all' in locals() else 0
        dropped_num = sum([len(data['dropped_cycles']) for data in site_biases.values()])
        total_num = valid_num + dropped_num
        percent = (valid_num / total_num * 100) if total_num > 0 else 0.0

        json_data = {
            "${satId}": ipf_config.Sat_ID,
            "${sensorId}": "ALT",
            "${sensorId_C}": "高度计",
            "${data_level}": "L2B_IGDR",
            "${method_name}": "YCZ",
            "${method_name_C}": "验潮站外推法",
            "${start_time}": ipf_config.Start_date,
            "${end_time}": ipf_config.End_date,
            "${parameter_C}": "海面高度",
            "${data_version}": ipf_config.Data_version,
            "${algo_version}": "V01",
            "${responsibler}": "东彦铭",
            "${programmer}": "王士帅",
            "${produce_time}": datetime.now().strftime("%Y年%m月%d日"),
            "${introduction}": "海面高度验潮站外推法是指以万山岛高度计海上定标场配套验潮站长期连续观测的海面高度实测数据作为真值基准，对GL-SY星高度计观测的海面高度进行标定的方法，通过依托万山岛定标场的地理优势与观测条件，确定GL-SY星高度计过境万山岛定标场的观测路径与星下点位置，结合定标场周边地形特征、潮汐规律及大气修正参数，完成卫星高度计观测数据与万山岛验潮站实测数据的时空精准匹配，根据数据匹配和质量控制准则，剔除异常观测样本，将万山岛验潮站实测海面高度经空间外推、潮汐改正及环境误差校正后，换算为GL-SY星高度计星下点等效海面高度，对比GL-SY星高度计与万山岛验潮站外推等效海面高度的观测差异，统计计算得出定标系数与系统偏差修正值。",
            "${aux_data}": "万山岛验潮站数据",
            "${level}": "L2",
            "${aft_num}": str(valid_num),
            "${total_num}": str(total_num),  # <--- 新增这行：将总匹配周期传给模板
            "${aft_bias}": f"{global_mean * 100:.2f}" if 'global_mean' in locals() else "N/A",
            "${aft_std}": f"{global_std * 100:.2f}" if 'global_std' in locals() else "N/A",
            "${aux_data_des}": "真值基准选择万山岛高度计海上定标场配套验潮站长期连续观测的海面高度实测数据。",
            "${percent01}": f"{percent:.2f}",
            "${percent02}": f"{percent:.2f}",
            "${image_scatter_hist}": hist_img,
            "${image_trend}": trend_img
    }

        json_path = os.path.join(outputPath,
                                 f"calibration_result_{ipf_config.Sat_ID}_vs_YCZ_{ipf_config.Start_date}_{ipf_config.End_date}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        Logger.info(f"JSON标签文件已保存至: {json_path}")

        # ==================== 6. 生成Word格式的报告文件 ====================
        Logger.info("生成Word报告文件...")
        try:
            from docx import Document
            from docx.shared import Inches, Cm, Pt
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            # 如果XML未配置模板路径，默认在程序执行目录的conf文件夹下寻找
            template_path = getattr(ipf_config, 'Template_docx', None)
            if not template_path:
                template_path = os.path.join(current_dir,  "Template_docx")

            if not os.path.exists(template_path):
                Logger.warn(f"Word模板文件不存在: {template_path}，跳过Word报告生成")
            else:
                doc = Document(template_path)

                for paragraph in doc.paragraphs:
                    if "${image_dist}" in paragraph.text or "${image_scatter_hist}" in paragraph.text or "${image_trend}" in paragraph.text:
                        continue
                    for run in paragraph.runs:
                        for key, value in json_data.items():
                            if key in run.text:
                                run.text = run.text.replace(key, str(value))

                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            for paragraph in cell.paragraphs:
                                for run in paragraph.runs:
                                    for key, value in json_data.items():
                                        if key in run.text:
                                            run.text = run.text.replace(key, str(value))

                # 插入图片
                for paragraph in doc.paragraphs:
                    if "${image_scatter_hist}" in paragraph.text:
                        paragraph.clear()
                        img_path = json_data["${image_scatter_hist}"]
                        if os.path.exists(img_path):
                            run = paragraph.add_run()
                            run.add_picture(img_path, width=Inches(6.0))
                            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            Logger.info(f"已插入散点直方图: {img_path}")
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
                        break

                report_path = os.path.join(outputPath,
                                           f"calibration_report_{ipf_config.Sat_ID}_vs_YCZ_{ipf_config.Start_date}_{ipf_config.End_date}.docx")
                doc.save(report_path)
                Logger.info(f"Word报告已保存至: {report_path}")

        except ImportError as e:
            Logger.warn(f"python-docx未安装，跳过Word报告生成。请执行: pip install python-docx")
        except Exception as e:
            Logger.warn(f"生成Word报告失败: {str(e)}")

    # ========================== 新增的工程化计算引擎代码结束 ==========================

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
            "aux_data": "万山岛验潮站数据",
            "total_periods": int(valid_num) if 'valid_num' in dir() else 0,
            "total_num": int(total_num) if 'total_num' in dir() else 0,
            "percent": f"{percent:.2f}" if 'percent' in dir() else "0.00",
            "global_mean_cm": float(global_mean * 100) if 'global_mean' in dir() else None,
            "global_std_cm": float(global_std * 100) if 'global_std' in dir() else None,
        },
        "output_files": {
            "output_dir": outputPath.replace('\\', '/') if 'outputPath' in dir() else '',
            "json_path": os.path.join(outputPath,
                                      f"calibration_result_{ipf_config.Sat_ID}_vs_YCZ_{ipf_config.Start_date}_{ipf_config.End_date}.json").replace('\\', '/'),
            "report_path": os.path.join(outputPath,
                                        f"calibration_report_{ipf_config.Sat_ID}_vs_YCZ_{ipf_config.Start_date}_{ipf_config.End_date}.docx").replace('\\', '/'),
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
        # 文件名格式: S6A_P4_2__LR_STD__NT_088_044_20230401T002018_20230401T011630_F08.nc
        # 我们需要提取两个时间戳: 20230401T002018 和 20230401T011630
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
            # 如果文件结束时间早于查询开始时间，或文件开始时间晚于查询结束时间，则跳过
            if file_end_dt < start_dt or file_start_dt > end_dt:
                continue

            # 如果有交集，则添加到文件列表
            file_list.append(filepath)

        except ValueError as e:
            print(f"警告: 无法解析文件 {filename} 中的日期: {e}")
            continue

    return file_list