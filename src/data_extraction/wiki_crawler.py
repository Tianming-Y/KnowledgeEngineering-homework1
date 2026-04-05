"""wiki_crawler.py — Wikipedia BFS 多跳爬虫

以种子页面为起点，按广度优先策略爬取关联页面，并通过
WikiParser 解析每个页面得到结构化 JSON，保存到 data/raw/。
"""

import json
import logging
import os
import re
import time
from collections import deque
from pathlib import Path
from typing import Optional

from .wiki_parser import WikiParser

logger = logging.getLogger(__name__)


class WikiCrawler:
    """Wikipedia BFS 爬虫。"""

    def __init__(self, config: dict, project_root: str = "."):
        """
        Parameters
        ----------
        config : dict
            从 settings.yaml 的 ``crawler`` 节加载的配置字典。
        project_root : str
            项目根目录路径，用于计算 data/raw 等相对路径。
        """
        self.seed_page: str = config["seed_page"]
        self.max_depth: int = config.get("max_depth", 2)
        self.max_pages: int = config.get("max_pages", 80)
        self.interval: float = config.get("request_interval", 1.0)
        self.user_agent: str = config.get("user_agent", "TuringKG-Bot/1.0")

        relevance = config.get("relevance", {})
        self.seed_keywords: list[str] = [
            kw.lower() for kw in relevance.get("seed_keywords", [])
        ]
        self.excluded_prefixes: list[str] = relevance.get("excluded_prefixes", [])
        self.excluded_suffixes: list[str] = relevance.get("excluded_suffixes", [])

        self.raw_dir = Path(project_root) / config.get("raw_dir", "data/raw")
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        self.parser = WikiParser(user_agent=self.user_agent)

        # 统计
        self._crawled_count = 0

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def crawl(self) -> list[str]:
        """执行 BFS 爬取，返回成功爬取的页面标题列表。"""
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()  # (title, depth)
        crawled_titles: list[str] = []

        # 加载已爬取页面（增量爬取）
        for f in self.raw_dir.glob("*.json"):
            visited.add(self._filename_to_title(f.stem))

        if visited:
            logger.info("增量爬取: 已存在 %d 个页面，将跳过", len(visited))

        queue.append((self.seed_page, 0))

        while queue and self._crawled_count < self.max_pages:
            title, depth = queue.popleft()

            if title in visited:
                continue
            visited.add(title)

            # 种子页面不进行相关性过滤
            if depth > 0 and not self._is_relevant(title):
                logger.debug("过滤不相关页面: %s", title)
                continue

            logger.info(
                "[%d/%d] 爬取 depth=%d: %s",
                self._crawled_count + 1,
                self.max_pages,
                depth,
                title,
            )

            page_data = self.parser.parse(title)
            if page_data is None:
                logger.warning("跳过不存在的页面: %s", title)
                continue

            # 保存 JSON
            page_data["crawl_depth"] = depth
            self._save(page_data)
            crawled_titles.append(title)
            self._crawled_count += 1

            # 将出链入队（下一层）
            if depth < self.max_depth:
                for link_title in page_data.get("outlinks", []):
                    if link_title not in visited:
                        queue.append((link_title, depth + 1))

            # 速率限制
            time.sleep(self.interval)

        logger.info("爬取完成，共获取 %d 个页面", self._crawled_count)
        return crawled_titles

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _is_relevant(self, title: str) -> bool:
        """判断页面标题是否与图灵 / 计算机科学领域相关。"""
        # 排除系统命名空间
        for prefix in self.excluded_prefixes:
            if title.startswith(prefix):
                return False

        # 排除消歧义页等
        for suffix in self.excluded_suffixes:
            if title.endswith(suffix):
                return False

        # 关键词匹配（标题中包含任一种子关键词即视为相关）
        title_lower = title.lower()
        return any(kw in title_lower for kw in self.seed_keywords)

    def _save(self, page_data: dict) -> None:
        """将页面数据保存为 JSON 文件。"""
        safe_name = self._title_to_filename(page_data["title"])
        filepath = self.raw_dir / f"{safe_name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(page_data, f, ensure_ascii=False, indent=2)
        logger.debug("已保存: %s", filepath)

    @staticmethod
    def _title_to_filename(title: str) -> str:
        """将页面标题转换为安全的文件名。"""
        # 替换文件系统不允许的字符
        name = re.sub(r'[<>:"/\\|?*]', "_", title)
        # 限制长度
        return name[:200]

    @staticmethod
    def _filename_to_title(filename: str) -> str:
        """从文件名还原页面标题（近似还原，用于增量去重）。"""
        return filename.replace("_", " ")
