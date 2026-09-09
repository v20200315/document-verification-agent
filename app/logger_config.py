import logging

# 配置全局日志
logging.basicConfig(
    level=logging.INFO,  # 设置全局日志级别
    format="%(asctime)s - %(levelname)s - %(message)s",  # 定义日志格式
)

# 可选：创建一个常用的全局 logger
logger = logging.getLogger("global_logger")
