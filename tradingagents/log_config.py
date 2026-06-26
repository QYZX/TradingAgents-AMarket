import logging.config
import os

# 日志文件路径：项目根目录/logs/interface.log
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(_LOG_DIR, exist_ok=True)

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s - %(message)s',
        },
    },
    'handlers': {
        'interface_file': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(_LOG_DIR, 'interface.log'),
            'encoding': 'utf-8',
            'formatter': 'standard',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'tradingagents.interface': {
            'handlers': ['interface_file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger('tradingagents.interface')
