"""统一日志模块

提供结构化日志输出，替代 print() 调用。
关键操作必须打 INFO 级别日志。

使用方式:
    from debate_prd.core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("操作完成 round=1 consensus_count=3")
"""

import logging
import sys

_LOG_FORMAT = "[%(levelname)s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_logger_instance: logging.Logger | None = None


def get_logger(name: str = "debate_prd") -> logging.Logger:
    """获取日志实例

    Args:
        name: 日志模块名称

    Returns:
        配置好的 Logger 实例
    """
    global _logger_instance

    if _logger_instance is None:
        _logger_instance = logging.getLogger("debate_prd")
        _logger_instance.setLevel(logging.INFO)

        if not _logger_instance.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)
            handler.setFormatter(formatter)
            _logger_instance.addHandler(handler)

    return _logger_instance.getChild(name.split(".")[-1])


def set_log_level(level: int):
    """设置日志级别

    Args:
        level: logging.DEBUG, logging.INFO, logging.WARNING 等
    """
    logger = get_logger()
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)
