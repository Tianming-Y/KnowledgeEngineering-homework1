"""Wikipedia 页面解析器。

本文件负责把单个 Wikipedia 条目拆解成适合后续 NLP 处理的结构化数据，
包括摘要、分章节正文、Infobox 键值对、分类和页面内部链接。它是爬虫阶段的
“单页理解器”，只处理一页，不负责遍历整张链接图。

使用方式：
- ``WikiCrawler`` 在遍历页面标题时会调用 ``WikiParser.parse(title)``。
- 开发时也可以直接实例化 ``WikiParser``，单独调试页面解析质量。

输入：
- 页面标题字符串。
- 通过 MediaWiki API 返回的 HTML 与结构化响应。

输出：
- ``parse`` 返回一个字典，字段包括 ``title``、``url``、``summary``、``sections``、
    ``infobox``、``categories``、``outlinks``；若页面不存在则返回 ``None``。

与其他文件的关系：
- 上游由 ``src/data_extraction/wiki_crawler.py`` 调度。
- 下游由 ``src/data_extraction/data_cleaner.py`` 清洗其输出文本字段。
"""

import re
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class WikiParser:
    """解析单个 Wikipedia 页面，返回结构化字典。"""

    WIKI_API = "https://en.wikipedia.org/w/api.php"

    def __init__(self, user_agent: str = "TuringKG-Bot/1.0"):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def parse(self, title: str) -> Optional[dict]:
        """解析给定标题的 Wikipedia 页面，返回结构化字典。

        Returns
        -------
        dict | None
            包含 title, url, summary, sections, infobox, categories, outlinks
            的字典；若页面不存在则返回 None。
        """
        html = self._fetch_html(title)
        if html is None:
            return None

        soup = BeautifulSoup(html, "lxml")

        summary = self._extract_summary(title)
        sections = self._extract_sections(soup)
        infobox = self._extract_infobox(soup)
        categories = self._fetch_categories(title)
        outlinks = self._fetch_outlinks(title)

        return {
            "title": title,
            "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "summary": summary,
            "sections": sections,
            "infobox": infobox,
            "categories": categories,
            "outlinks": outlinks,
        }

    # ------------------------------------------------------------------
    # MediaWiki API 辅助
    # ------------------------------------------------------------------

    def _fetch_html(self, title: str) -> Optional[str]:
        """通过 MediaWiki parse API 获取页面 HTML。"""
        params = {
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "redirects": 1,
        }
        try:
            resp = self.session.get(self.WIKI_API, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                logger.warning("页面不存在: %s — %s", title, data["error"].get("info"))
                return None
            return data["parse"]["text"]["*"]
        except Exception:
            logger.exception("获取页面 HTML 失败: %s", title)
            return None

    def _extract_summary(self, title: str) -> str:
        """通过 MediaWiki extracts API 获取摘要。"""
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "format": "json",
            "redirects": 1,
        }
        try:
            resp = self.session.get(self.WIKI_API, params=params, timeout=30)
            resp.raise_for_status()
            pages = resp.json()["query"]["pages"]
            page = next(iter(pages.values()))
            return page.get("extract", "")
        except Exception:
            logger.exception("获取摘要失败: %s", title)
            return ""

    def _fetch_categories(self, title: str) -> list[str]:
        """获取页面分类列表。"""
        params = {
            "action": "query",
            "titles": title,
            "prop": "categories",
            "cllimit": "max",
            "format": "json",
            "redirects": 1,
        }
        try:
            resp = self.session.get(self.WIKI_API, params=params, timeout=30)
            resp.raise_for_status()
            pages = resp.json()["query"]["pages"]
            page = next(iter(pages.values()))
            cats = page.get("categories", [])
            return [c["title"].replace("Category:", "") for c in cats]
        except Exception:
            logger.exception("获取分类失败: %s", title)
            return []

    def _fetch_outlinks(self, title: str) -> list[str]:
        """获取页面内部链接（出链）列表。"""
        outlinks: list[str] = []
        params = {
            "action": "query",
            "titles": title,
            "prop": "links",
            "pllimit": "max",
            "plnamespace": 0,  # 仅主命名空间
            "format": "json",
            "redirects": 1,
        }
        try:
            while True:
                resp = self.session.get(self.WIKI_API, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                pages = data["query"]["pages"]
                page = next(iter(pages.values()))
                for link in page.get("links", []):
                    outlinks.append(link["title"])
                if "continue" in data:
                    params.update(data["continue"])
                else:
                    break
        except Exception:
            logger.exception("获取出链失败: %s", title)
        return outlinks

    # ------------------------------------------------------------------
    # HTML 解析
    # ------------------------------------------------------------------

    def _extract_sections(self, soup: BeautifulSoup) -> list[dict]:
        """从 HTML 中按 <h2>/<h3> 拆分章节，提取纯文本段落。"""
        sections: list[dict] = []
        current_heading = "Introduction"
        current_paragraphs: list[str] = []

        # 移除目录、导航框、参考文献等无用块
        for tag in soup.find_all(
            ["div", "table", "sup", "span"],
            class_=re.compile(r"toc|navbox|reflist|reference|mw-editsection|metadata"),
        ):
            tag.decompose()

        body = soup.find("div", class_="mw-parser-output")
        if body is None:
            return sections

        for element in body.children:
            name = getattr(element, "name", None)

            # Wikipedia 新版 HTML: h2/h3 被包裹在 <div class="mw-heading"> 中
            heading_tag = None
            if name == "div" and element.get("class"):
                classes = element.get("class", [])
                if any(c.startswith("mw-heading") for c in classes):
                    heading_tag = element.find(["h2", "h3"])

            # 兼容旧版: h2/h3 直接作为 body 子节点
            if name in ("h2", "h3"):
                heading_tag = element

            if heading_tag is not None:
                # 保存上一节
                text = "\n".join(current_paragraphs).strip()
                if text:
                    sections.append({"heading": current_heading, "text": text})
                headline = heading_tag.get_text(strip=True)
                # 去掉编辑链接后缀
                headline = re.sub(r"\[edit\]$", "", headline).strip()
                current_heading = headline
                current_paragraphs = []
            elif name == "p":
                para = element.get_text(separator=" ", strip=True)
                if para:
                    current_paragraphs.append(para)

        # 保存最后一节
        text = "\n".join(current_paragraphs).strip()
        if text:
            sections.append({"heading": current_heading, "text": text})

        return sections

    def _extract_infobox(self, soup: BeautifulSoup) -> dict:
        """从 Infobox 表格中提取键值对。"""
        infobox: dict = {}
        table = soup.find("table", class_=re.compile(r"infobox"))
        if table is None:
            return infobox

        for row in table.find_all("tr"):
            header = row.find("th")
            data = row.find("td")
            if header and data:
                key = header.get_text(separator=" ", strip=True)
                value = data.get_text(separator=" ", strip=True)
                if key and value:
                    infobox[key] = value

        return infobox
