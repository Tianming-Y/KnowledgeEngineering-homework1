"""采集结果清洗与分句模块。

本文件负责把 ``data/raw`` 中的原始 Wikipedia 页面 JSON 转换为更适合下游处理的
``data/processed`` 文档。它统一执行文本去噪、Unicode 规范化、引用标记删除和句子切分，
为 NER、候选对生成和关系抽取提供稳定输入。

使用方式：
- 通常由 ``src/data_extraction/run_extraction.py`` 在爬取完成后统一调用 ``clean_all()``。
- 也可以单独实例化 ``DataCleaner`` 指向任意原始目录和输出目录。

输入：
- ``data/raw/*.json``，字段通常包含 ``summary``、``sections``、``infobox`` 等内容。

输出：
- ``data/processed/*.json``，保留原有结构并新增 ``summary_sentences`` 与每个 section 的
    ``sentences`` 字段，便于后续按句子处理。

与其他文件的关系：
- 上游依赖 ``wiki_crawler.py`` / ``wiki_parser.py`` 生成原始页面文件。
- 下游 ``src/ner/batch_process.py`` 和 ``src/relation_extraction/generate_candidates.py``
    都直接消费这里的句子级输出。
"""

import json
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

# 分句正则: 英文句号/问号/感叹号 后接空格或行末
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


class DataCleaner:
    """从 raw JSON 文件中清洗文本，输出到 processed 目录。"""

    def __init__(
        self, raw_dir: str = "data/raw", processed_dir: str = "data/processed"
    ):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def clean_all(self) -> list[str]:
        """清洗 raw 目录下所有 JSON 文件，返回已处理的文件名列表。"""
        processed_files: list[str] = []
        for json_path in sorted(self.raw_dir.glob("*.json")):
            try:
                self._clean_one(json_path)
                processed_files.append(json_path.stem)
            except Exception:
                logger.exception("清洗失败: %s", json_path.name)
        logger.info("清洗完成，共处理 %d 个文件", len(processed_files))
        return processed_files

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _clean_one(self, json_path: Path) -> None:
        """清洗单个 JSON 文件并输出到 processed 目录。"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cleaned = {
            "title": data.get("title", ""),
            "url": data.get("url", ""),
            "summary": self._clean_text(data.get("summary", "")),
            "summary_sentences": self._split_sentences(
                self._clean_text(data.get("summary", ""))
            ),
            "sections": [],
            "infobox": data.get("infobox", {}),
            "categories": data.get("categories", []),
            "outlinks": data.get("outlinks", []),
            "crawl_depth": data.get("crawl_depth", -1),
        }

        for section in data.get("sections", []):
            clean_text = self._clean_text(section.get("text", ""))
            if not clean_text:
                continue
            cleaned["sections"].append(
                {
                    "heading": section.get("heading", ""),
                    "text": clean_text,
                    "sentences": self._split_sentences(clean_text),
                }
            )

        out_path = self.processed_dir / json_path.name
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        logger.debug("已输出: %s", out_path)

    # ------------------------------------------------------------------
    # 文本清洗工具
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_text(text: str) -> str:
        """执行一系列文本清洗操作。"""
        if not text:
            return ""

        # 1. Unicode NFKC 规范化
        text = unicodedata.normalize("NFKC", text)

        # 2. 去除引用标记 [1], [2], [note 1], [a] 等
        text = re.sub(r"\[\d+\]", "", text)
        text = re.sub(r"\[note \d+\]", "", text)
        text = re.sub(r"\[[a-z]\]", "", text)

        # 3. 去除 HTML 残留标签
        text = re.sub(r"<[^>]+>", "", text)

        # 4. 去除多余空白
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """将文本按英文句子边界拆分。"""
        if not text:
            return []
        sentences = _SENT_SPLIT.split(text)
        return [s.strip() for s in sentences if s.strip()]
