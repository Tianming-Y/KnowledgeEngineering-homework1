"""数据采集总入口脚本。

本文件把“爬取页面”和“清洗文本”两个步骤串成一个可直接运行的前半段流水线。
它从 ``config/settings.yaml`` 读取抓取与路径配置，依次调度 ``WikiCrawler`` 和
``DataCleaner``，是项目从网络页面到本地结构化文档的统一入口。

使用方式：
- 直接执行 ``python src/data_extraction/run_extraction.py``。

输入：
- ``config/settings.yaml`` 中的 crawler 和 paths 配置。

输出：
- ``data/raw`` 中的原始页面 JSON。
- ``data/processed`` 中的清洗后页面 JSON。
- 终端中的阶段日志与汇总统计。

与其他文件的关系：
- 调用 ``src.data_extraction`` 子包导出的 ``WikiCrawler`` 与 ``DataCleaner``。
- 它的输出构成整个项目其余模块的上游数据基础。
"""

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
