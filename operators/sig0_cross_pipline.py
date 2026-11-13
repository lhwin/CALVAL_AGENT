"""
Sig0交叉定标算子 - 忠实包装自 GPF 源码:
src/Sig0Cross/match/func_GLSY_ALT_GDR_AUX_SAT_SIG0_MATCH.py (MATCH)
src/Sig0Cross/cal/func_GLSY_ALT_AUX_Sat_GDR_SIG0_CAL.py (CAL)
"""
import time
import logging
from typing import Dict, Any, Optional
import numpy as np
from scipy import stats as stats_log

from src.Sig0Cross.cal.func_GLSY_ALT_AUX_Sat_GDR_SIG0_CAL import func_cross_cal_pro
from src.Sig0Cross.match.func_GLSY_ALT_GDR_AUX_SAT_SIG0_MATCH import func_cross_matching_pro
from src.config import *


class Sig0CrossCalibration:
    """Sig0交叉定标 (星间交叉: 主卫星 vs 辅助卫星)。"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("sig0_cross")

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            
# MATCH

            match_result = func_cross_matching_pro(self.config)

            
# CAL: 把 MATCH 的输出目录作为 CAL 的输入

            self.config.input = match_result["output_files"]["output_dir"]
            cal_result = func_cross_cal_pro(self.config)

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
        return func_cross_matching_pro(self.config)

    def run_cal(self):
        return func_cross_cal_pro(self.config)


if __name__ == "__main__":
    config = {
        "Sat_ID": "S6A",
        "AUX_Sat": "JA3",
        "Data_version": "V001",
        "Match_Data_Type": "JA3",
        "Product_Type": "SIG0",
        "Start_date": "20230501",
        "End_date": "20230503",
        "Match_time": "2.0",
        "Template_docx": "",
        "order_id": "0",
        "input": r"D:\BaiduSyncdisk\\project\\202610\data\satelite\S6A",
        "input_AUX": r"D:\BaiduSyncdisk\\project\\202610\data\satelite\JA3",
        "output": r"output_local_test\sig0_cross_0",
        "outputFileType": "GL_SSH_SIG0_CROSS_MATCH_RESULT",
        "proc_name": "gl_ssh_sig0_cross_match_pro",
        "version": "1.0",
    }
    config = Sig0CrossItem(**config)

    op = Sig0CrossCalibration(config)
    result = op.run()
    print(result)