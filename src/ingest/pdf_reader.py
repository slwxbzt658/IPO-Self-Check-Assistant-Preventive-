"""
PDF 文本提取底座
==================

使用 PyMuPDF(fitz)做基础文本抽取。本模块不做业务解析,只负责:
    - 打开 PDF
    - 按页码取文本
    - 关键词定位
    - 取某范围内的页面文本

业务级抽取(如客户集中度)在 src/extract/ 下,会调用本模块。

设计原则:
    - 上下文管理器(with PDFReader(...) as r): 确保文件句柄正确关闭
    - 1-indexed 页码: 对外暴露的页码与招股书印刷页码一致(从 1 开始)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import fitz  # PyMuPDF


@dataclass
class PageText:
    """单页文本的封装"""
    page_number: int  # 1-indexed
    text: str

    def __repr__(self) -> str:
        preview = self.text[:50].replace("\n", " ")
        return f"PageText(page={self.page_number}, text='{preview}...')"


class PDFReader:
    """轻量级 PDF 阅读器,以上下文管理器方式使用"""

    def __init__(self, pdf_path: Path | str) -> None:
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {self.pdf_path}")
        self._doc: fitz.Document | None = None

    def __enter__(self) -> "PDFReader":
        self._doc = fitz.open(str(self.pdf_path))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    @property
    def doc(self) -> fitz.Document:
        if self._doc is None:
            raise RuntimeError("PDFReader 未打开,请用 with 语句包裹使用")
        return self._doc

    def num_pages(self) -> int:
        return self.doc.page_count

    def get_page_text(self, page_number: int) -> str:
        """page_number 是 1-indexed"""
        if not (1 <= page_number <= self.doc.page_count):
            raise IndexError(f"页码 {page_number} 超出范围 [1, {self.doc.page_count}]")
        return self.doc[page_number - 1].get_text()

    def search_keyword_pages(self, keyword: str, *, max_pages: int | None = None) -> list[int]:
        """返回包含关键词的所有页码(1-indexed)"""
        result: list[int] = []
        limit = self.doc.page_count if max_pages is None else min(max_pages, self.doc.page_count)
        for i in range(limit):
            text = self.doc[i].get_text()
            if keyword in text:
                result.append(i + 1)
        return result

    def get_pages_range(self, start: int, end: int) -> list[PageText]:
        """获取 [start, end] 范围内的所有页面(1-indexed,闭区间)"""
        result: list[PageText] = []
        for i in range(max(1, start), min(self.doc.page_count, end) + 1):
            result.append(PageText(page_number=i, text=self.doc[i - 1].get_text()))
        return result

    def iter_pages(self) -> Iterator[PageText]:
        """迭代所有页面"""
        for i in range(self.doc.page_count):
            yield PageText(page_number=i + 1, text=self.doc[i].get_text())
