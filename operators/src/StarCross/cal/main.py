# -*-coding:utf-8 -*-
import warnings
import sys
import time
import traceback
from func_GLSY_ALT_AUX_Sat_GDR_CAL import func_cross_cal_pro
from IPFUtils import MyIPFConfig, Logger
import os
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

if __name__ == '__main__':
    warnings.filterwarnings('ignore')
    t1 = time.time()
    # ######################################################## 测试时注释，打包时取消注释
    # if len(sys.argv) != 2:
    #     print("No task order file is given!")
    #     sys.exit(255)
    try:
        # 解析工单信息
        # ######################################################## 测试时注释，打包时取消注释
        # ipf_config = MyIPFConfig(sys.argv[1])
        # ######################################################## 打包时注释，测试时取消注释
        ipf_config = MyIPFConfig(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.xml")
        )
        # 初始化日志配置
        str_order_id = "%010d" % int(ipf_config.order_id)
        log_file_name = "log_{}_v{}_{}.txt".format(ipf_config.proc_name, ipf_config.version, str_order_id)
        log_file_path = os.path.join(ipf_config.output, log_file_name)
        Logger(log_file_path, ipf_config.proc_name, ipf_config.version)

        # print(common.utc_time_mark() + " [I]: 初始化完成，开始执行", flush=True)
        Logger.info("Initialization completed, execution started")
        mm = func_cross_cal_pro(ipf_config)

        t2 = time.time()
        time_duration = t2 - t1
        # msg = '运行结束，运行总时间：' + str(round(time_duration, 2)) + ' 秒'
        # print(common.utc_time_mark() + " [I]: " + msg, flush=True)
        msg = 'End of operation, total operation time:' + str(round(time_duration, 2)) + ' seconds'
        Logger.info(msg)
        if not mm:
            sys.exit(0)
        else:
            sys.exit(mm)
    except Exception as inst:
        print(traceback.format_exc())
        msg = str(inst.args[0])  # 捕捉异常消息
        # print(common.utc_time_mark() + " [E]: " + msg, flush=True)
        Logger.error(msg)
        t2 = time.time()
        time_duration = t2 - t1
        # msg = '运行结束，运行总时间：' + str(round(time_duration, 2)) + ' 秒'
        # print(common.utc_time_mark() + " [I]: " + msg, flush=True)
        msg = 'End of operation, total operation time:' + str(round(time_duration, 2)) + ' seconds'
        Logger.info(msg)
        sys.exit(255)