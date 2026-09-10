"""P1-6: 统一日志配置 — 时间戳 + 级别 + 模块名 + 文件输出.

所有后端模块共用 logger 'day102', 通过 import logger 即可使用.
日志同时输出到控制台 (StreamHandler) 和 logs/day102.log (FileHandler).

用法:
  from log_setup import logger
  logger.info("[watcher] 数据轮询线程已启动")
  logger.error("[api] MQTT 下发失败: ...")
"""
import logging
import os
import sys

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(_LOG_DIR, exist_ok=True)

_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
_LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'


def setup_logger(name: str = 'day102', level: int = logging.INFO) -> logging.Logger:
    """创建并配置 logger. 重复调用不会重复添加 handler."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)

    # 文件输出
    fh = logging.FileHandler(os.path.join(_LOG_DIR, 'day102.log'), encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台输出 (stderr, 不干扰 Flask 的 stdout)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


# 全局单例: 所有模块共用
logger = setup_logger()
