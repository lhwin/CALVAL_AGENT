"""
海洋潮汐外推定标算子 - 忠实包装自 GPF 源码:
src/OceanTide/match/func_GLSY_ALT_GDR_AUX_YCZ_MATCH.py (MATCH)
src/OceanTide/cal/func_GLSY_ALT_AUX_YCZ_GDR_CAL.py (CAL)
"""
import time
import logging
from typing import Dict, Any, Optional
import numpy as np
from scipy import stats as stats_log
try:
    from src.OceanTide.cal.func_GLSY_ALT_AUX_YCZ_GDR_CAL import func_ycz_cal_pro
    from src.OceanTide.match.func_GLSY_ALT_GDR_AUX_YCZ_MATCH import func_ycz_matching_pro
    from src.config import *
except:
    from operators.src.OceanTide.cal.func_GLSY_ALT_AUX_YCZ_GDR_CAL import func_ycz_cal_pro
    from operators.src.OceanTide.match.func_GLSY_ALT_GDR_AUX_YCZ_MATCH import func_ycz_matching_pro
    from operators.src.config import *


class OceanTideCalibration:
    """海洋潮汐外推定标 (卫星 vs 验潮站)。"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("ocean_tide")

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            
# MATCH

            match_result = func_ycz_matching_pro(self.config)

            
# CAL: 把 MATCH 的输出目录作为 CAL 的输入

            self.config.input = match_result["output_files"]["output_dir"]
            cal_result = func_ycz_cal_pro(self.config)

            return {
                "status": "success",
                "execution_time": time.time() - t0,
                "match_result": match_result,
                "cal_result": cal_result,
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "execution_time": time.time() - t0,
            }

    def run_match(self):
        return func_ycz_matching_pro(self.config)

    def run_cal(self):
        return func_ycz_cal_pro(self.config)


if __name__ == "__main__":
    config = {
        "Sat_ID": "S6A",
        "Data_version": "V001",
        "Product_Type": "SSH",
        "Start_date": "20230501",
        "End_date": "20230503",
        "order_id": "0",
        "operation_type": "match",# Match特有
        "input": r"D:\BaiduSyncdisk\project\202610\data\satelite\S6A",
        "input_AUX": r"D:\BaiduSyncdisk\project\202610\data\satelite\YCZ",
        "AUX_YCZ": "zhiwan",
        "MSS_PATH": r"D:\BaiduSyncdisk\project\202610\data\DTU18MSS_1min.nc",
        "FES2014_PATH": r"D:\BaiduSyncdisk\project\202610\data\FES2014",
        "output": r"output_local_test\ocean_tide_0",# Cal特有
        "Match_Data_Type": "YCZ",
        "template_doc": "",
        "template_docx": "", # 可选
        "outputFileType": "GL_SSH_YCZ_MATCH_RESULT",
        "proc_name": "gl_ssh_ycz_match_pro",
        "version": "1.0",
    }
    config = OceanTideItem(**config)

    op = OceanTideCalibration(config)
    result = op.run()
    print(result)