"""run_extraction.py — 运行数据采集全流程"""

import logging
import json
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_extraction")

from src.data_extraction import WikiCrawler, DataCleaner

with open("config/settings.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

crawler_cfg = config["crawler"]
paths_cfg = config["paths"]
crawler_cfg["raw_dir"] = paths_cfg["raw_data"]

# ---- 阶段 1: 爬取 ----
logger.info("=" * 50)
logger.info(
    "阶段 1: Wikipedia 数据爬取 (max_depth=%d, max_pages=%d)",
    crawler_cfg["max_depth"],
    crawler_cfg["max_pages"],
)
logger.info("=" * 50)

crawler = WikiCrawler(config=crawler_cfg)
titles = crawler.crawl()

# ---- 阶段 2: 清洗 ----
logger.info("=" * 50)
logger.info("阶段 2: 文本清洗与去噪")
logger.info("=" * 50)

cleaner = DataCleaner(
    raw_dir=paths_cfg["raw_data"],
    processed_dir=paths_cfg["processed_data"],
)
cleaned = cleaner.clean_all()

# ---- 汇总 ----
logger.info("=" * 50)
logger.info("全流程完成: 爬取 %d 页, 清洗 %d 文件", len(titles), len(cleaned))
logger.info("=" * 50)
