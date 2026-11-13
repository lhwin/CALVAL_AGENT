# -*-coding:utf-8 -*-
import xml.dom.minidom as minidom
import logging
import socket
import os

#解析工单
class MyIPFConfig:
    def __init__(self, configFile):
        dom = minidom.parse(configFile)
        root = dom.documentElement
        # proc_name、version、order_id、input、output、动态参数
        procnameRoot = root.getElementsByTagName('Processor_Name')
        self.proc_name = procnameRoot[0].firstChild.data

        versionRoot = root.getElementsByTagName('Version')
        self.version = versionRoot[0].firstChild.data

        orderRoot = root.getElementsByTagName('Order_Id')
        self.order_id = orderRoot[0].firstChild.data

        inputRoot = root.getElementsByTagName('Input')[0].getElementsByTagName("File_Name")
        self.input = inputRoot[0].firstChild.data

        outputRoot = root.getElementsByTagName('Output')[0].getElementsByTagName("File_Name")
        self.output = outputRoot[0].firstChild.data

        outputFileTypeRoot = root.getElementsByTagName('Output')[0].getElementsByTagName("File_Type")
        self.outputFileType = outputFileTypeRoot[0].firstChild.data

                # 获取所有Processing_Parameter元素
        param_elements = dom.getElementsByTagName('Processing_Parameter')

        # 创建字典存储Name-Value对
        params = {}

        # 遍历所有Processing_Parameter元素
        for param in param_elements:
            # 获取Name和Value元素
            name_elements = param.getElementsByTagName('Name')
            value_elements = param.getElementsByTagName('Value')
            
            # 确保元素存在
            if name_elements and value_elements:
                name = name_elements[0].firstChild.nodeValue
                value = value_elements[0].firstChild.nodeValue
                params[name] = value

        self.Sat_ID =params['Sat_ID']
        self.Data_version = params['Data_version']
        self.Match_Data_Type = params['Match_Data_Type']
        self.Product_Type = params['Product_Type']
        self.Start_date = params['Start_date']
        self.End_date = params['End_date']
        self.Select_Area = params.get('Select_Area', '[-60,60,-180,180]')
        self.distance_to_coast = float(params.get('distance_to_coast', '50'))
        self.ocean_depth = float(params.get('ocean_depth', '1000'))
        self.wind_speed = params.get('wind_speed', None)
        self.Template_docx = params.get('Template_docx', None)

#解析其他配置文件，（可选）
class CacuConfig:
    def __init__(self, cacuConfigFile):
        dom = minidom.parse(cacuConfigFile)
        root = dom.documentElement
        # number_of_threads、L、P0、K
        threadsRoot = root.getElementsByTagName('number_of_threads')
        self.number_of_threads = int(threadsRoot[0].firstChild.data)

        LRoot = root.getElementsByTagName('filtering_parameter_L')
        self.L = int(LRoot[0].firstChild.data)

        P0Root = root.getElementsByTagName('filtering_parameter_P0')
        self.P0 = int(P0Root[0].firstChild.data)

        KRoot = root.getElementsByTagName('filtering_parameter_K')
        self.K = int(KRoot[0].firstChild.data)

        saveRSDTiffFlagRoot = root.getElementsByTagName('save_RSDtiff_flag')
        self.saveRSDTiffFlag = int(saveRSDTiffFlagRoot[0].firstChild.data)

        saveRSDXmlFlagRoot = root.getElementsByTagName('save_RSDxml_flag')
        self.saveRSDXmlFlag = int(saveRSDXmlFlagRoot[0].firstChild.data)

        saveRSDH5FlagRoot = root.getElementsByTagName('save_RSDh5_flag')
        self.saveRSDH5Flag = int(saveRSDH5FlagRoot[0].firstChild.data)

        saveRGBTiffFlagRoot = root.getElementsByTagName('save_RGBtiff_flag')
        self.saveRGBTiffFlag = int(saveRGBTiffFlagRoot[0].firstChild.data)

        saveRGBJpgFlagRoot = root.getElementsByTagName('save_RGBjpg_flag')
        self.saveRGBJpgFlag = int(saveRGBJpgFlagRoot[0].firstChild.data)

        saveThumbJpgFlagRoot = root.getElementsByTagName('save_Thumbjpg_flag')
        self.saveThumbJpgFlag = int(saveThumbJpgFlagRoot[0].firstChild.data)

        softwareVersionRoot = root.getElementsByTagName('softwareVersion')
        self.softwareVersion = softwareVersionRoot[0].firstChild.data


class Logger:
    def __init__(self, filepath, proc_name, version, if_output_to_screen=True):
        # 2022-07-05T17:20:36.715 localhost.localdomain csx_l4a_ship_pro 01_00 [0000006823]: [I] test
        hostname = socket.gethostname()
        LOG_FORMAT = "%(asctime)s.%(msecs)03d {} {} {} [%(process)010d]: %(message)s".format(hostname, proc_name,
                                                                                             version)
        DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
        logging.basicConfig(filename=filepath, level=logging.INFO, format=LOG_FORMAT,
                            datefmt=DATE_FORMAT)
        if if_output_to_screen:
            console = logging.StreamHandler()
            console.setLevel(logging.DEBUG)
            console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
            logging.getLogger('').addHandler(console)

    @staticmethod
    def info(message):
        tmp_message = "[I] " + message
        logging.info(tmp_message)

    @staticmethod
    def error(message):
        tmp_message = "[E] " + message
        logging.error(tmp_message)

    @staticmethod
    def debug(message):
        tmp_message = "[D] " + message
        logging.debug(tmp_message)

    @staticmethod
    def warn(message):
        tmp_message = "[W] " + message
        logging.warning(tmp_message)

    @staticmethod
    def progress(pro):
        # [P] [000_STA_000],[P] [003_PRO_000],[P] [045_PRO_000],[P] [100_END_000]
        s1 = "%03d" % pro
        s2 = "PRO"
        if pro == 0:
            s2 = "STA"
        elif pro == 100:
            s2 = "END"
        s3 = "000"
        tmp_message = "[P] " + "[{}_{}_{}]".format(s1, s2, s3)
        logging.info(tmp_message)


# product.xml
def write_product_xml(product_xml_path, product_path, file_type):
    dom = minidom.Document()
    product_list_node = dom.createElement('product_list')
    product_list_node.setAttribute('count', '1')
    dom.appendChild(product_list_node)

    product_node = dom.createElement('product')
    product_node.setAttribute('index', '1')
    product_node.setAttribute('File_Type', file_type)
    product_list_node.appendChild(product_node)

    files = os.listdir(product_path)
    for file in files:
        file_path = os.path.join(product_path, file)
        file_node = dom.createElement('file')
        file_text = dom.createTextNode(file_path)
        file_node.appendChild(file_text)
        product_node.appendChild(file_node)

    try:
        with open(product_xml_path, 'w', encoding='UTF-8') as fh:
            # writexml()第一个参数是目标文件对象，第二个参数是根节点的缩进格式，第三个参数是其他子节点的缩进格式，
            # 第四个参数制定了换行格式，第五个参数制定了xml内容的编码。
            dom.writexml(fh, indent='', addindent='\t', newl='\n', encoding='UTF-8')
            Logger.info("write product xml success")
    except Exception as err:
        Logger.error("write product xml error:{0}".format(err))