import logging
import os
from datetime import datetime

# LLM 交互日志配置
llm_logger = logging.getLogger("llm_interaction")
llm_logger.setLevel(logging.DEBUG)
os.makedirs("logs", exist_ok=True)
llm_handler = logging.FileHandler("logs/llm.log", encoding="utf-8")
llm_handler.setLevel(logging.DEBUG)
llm_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
llm_handler.setFormatter(llm_formatter)
llm_logger.addHandler(llm_handler)


def log_llm_call(agent_name, input_data, output_data=None, error=None):
    """记录 LLM 调用的参数和结果"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    if error:
        llm_logger.error(f"[{agent_name}] LLM 调用失败 - 时间: {timestamp}")
        llm_logger.error(f"[{agent_name}] 输入: {input_data}")
        llm_logger.error(f"[{agent_name}] 错误: {str(error)}")
    else:
        llm_logger.info(f"[{agent_name}] LLM 调用 - 时间: {timestamp}")
        llm_logger.info(f"[{agent_name}] 输入: {input_data}")
        llm_logger.info(f"[{agent_name}] 输出: {output_data}")
