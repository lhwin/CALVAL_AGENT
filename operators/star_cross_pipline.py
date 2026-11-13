"""
星星交叉定标算子 - 忠实包装自 GPF 源码:
src/StarCross/match/func_GLSY_ALT_GDR_AUX_SAT_MATCH.py (MATCH)
src/StarCross/cal/func_GLSY_ALT_AUX_Sat_GDR_CAL.py (CAL)
"""

import time
import logging
from typing import Dict, Any, Optional
import numpy as np
from scipy import stats as stats_log

try:
    from src.StarCross.cal.func_GLSY_ALT_AUX_Sat_GDR_CAL import func_cross_cal_pro
    from src.StarCross.match.func_GLSY_ALT_GDR_AUX_SAT_MATCH import func_cross_matching_pro
    from src.config import *
except Exception as e:
    from operators.src.StarCross.cal.func_GLSY_ALT_AUX_Sat_GDR_CAL import func_cross_cal_pro
    from operators.src.StarCross.match.func_GLSY_ALT_GDR_AUX_SAT_MATCH import func_cross_matching_pro
    from operators.src.config import *

class StarCrossCalibration:
    """星星交叉定标 (星间交叉: 主卫星 vs 辅助卫星)。"""

    def __init__(self, config):
        self.config = StarCrossItem(**config)
        self.logger = logging.getLogger("star_cross")

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        # MATCH: 需要先设置 AUX_Sat 和 input_AUX
        match_result = func_cross_matching_pro(self.config)
            
            # CAL: 把 MATCH 的输出目录作为 CAL 的输入
        self.config.input = match_result["output_dir"]
        cal_result = func_cross_cal_pro(self.config)

        return {
                "status": "success",
                "execution_time": time.time() - t0,
                "cal_result": cal_result,
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
    "Product_Type": "SSH",
    "Start_date": "20230501",
    "End_date": "20230503",
    "Match_time": "2.0",
    "Template_docx": "",
    "order_id": "0",
    "input": r"D:\\BaiduSyncdisk\\project\\202610\\data\\satelite\\S6A",
    "input_AUX": r"D:\BaiduSyncdisk\\project\\202610\data\satelite\\JA3",
    "output": r"output_local_test\star_cross_0",
    "outputFileType": "GL_SSH_STAR_CROSS_MATCH_RESULT",
    "proc_name": "gl_ssh_cross_match_pro",
    "version": "1.0",
    "Select_Area": "[-60,60,-180,180]",
    "distance_to_coast": 50,
    "ocean_depth": 1000,
    "wind_speed": "[0,40]"  
    }
    # config = StarCrossItem(**config)

    # 运行
    op = StarCrossCalibration(config)
    result = op.run()
    print(result)
