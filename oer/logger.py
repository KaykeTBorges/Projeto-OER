import logging
import sys

from . import config

def setup_logger(name, log_file=None, level=logging.INFO):
    """Configurar logger com arquivo e console."""
    if log_file is None:
        log_file = f"{name}.log"

    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.LOGS_DIR / log_file

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger

def get_scraper_logger():
    return setup_logger("scraper", "scraper.log")

def get_parser_logger():
    return setup_logger("parser", "parser.log")

def get_pipeline_logger():
    return setup_logger("pipeline", "pipeline.log")

def get_ml_logger():
    return setup_logger("ml", "ml_pipeline.log")