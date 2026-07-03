"""
客户集中度抽取器 v0.2 - 多策略
==================================

v0.1 的问题:只搜"前五大客户"一个章节,结果抽到的是"前五合计占比"(99%),
而我们要的是"第一大客户单独占比"(60-70%)。

v0.2 升级:
    1. 多策略并行: prose / front_matter / table_top5
    2. 合理性过滤: top-1 占比一般在 30%-92%,>95% 视为 top-5 合计直接淘汰
    3. 详细诊断: 每个策略尝试了什么页、找到什么、淘汰了什么,全部入日志

策略优先级(从精确到模糊):
    A. prose_first_customer    -- "第一大客户"锚点旁 3 个合理百分比
    B. front_matter_risk       -- "重大事项提示"章节里搜
    C. named_customer_anchor   -- 特定客户名(中航工业A01 等)旁
    D. section_top5_table      -- 兜底(原 v0.1 逻辑)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable

from src.ingest.pdf_reader import PDFReader, PageText


# ============================================================
# 配置常量
# ============================================================

TOP1_REASONABLE_RANGE = (0.25, 0.92)

TRIPLE_PERCENT_PATTERN = re.compile(
    r"(\d{1,3}\.\d{1,2})\s*%[、，,\s和及]+\s*"
    r"(\d{1,3}\.\d{1,2})\s*%[、，,\s和及]+\s*"
    r"(\d{1,3}\.\d{1,2})\s*%"
)

PERIOD_PATTERN = re.compile(
    r"(20\d{2})\s*年(?:度)?(?:\s*1\s*[-–至～]\s*(\d{1,2})\s*月)?"
)

CUSTOMER_NAME_PATTERNS = [
    r"中航工业\s*[A-Z]?\d+\s*单位",
    r"中国航发\s*[A-Z]?\d+\s*单位",
    r"中航\s*[A-Z]?\d+\s*单位",
]


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ExtractionResult:
    success: bool
    confidence: str  # high / medium / low
    top1_customer_name: Optional[str] = None
    yearly_ratios: list[float] = field(default_factory=list)
    report_periods: list[str] = field(default_factory=list)
    source_pages: list[int] = field(default_factory=list)
    matched_section_keyword: Optional[str] = None
    raw_text_sample: str = ""
    messages: list[str] = field(default_factory=list)
    strategy_used: Optional[str] = None


# ============================================================
# 工具函数
# ============================================================

def _is_plausible_top1_ratios(ratios: list[float]) -> bool:
    """3 个数字都在 25%-92% 区间 → 像 top-1 客户占比;若都 >95% → 像 top-5 合计"""
    if len(ratios) < 3:
        return False
    return all(TOP1_REASONABLE_RANGE[0] <= r <= TOP1_REASONABLE_RANGE[1] for r in ratios)


def _find_customer_name(text: str) -> Optional[str]:
    """从文本中找客户名(中航工业 A01 这种)"""
    for pat in CUSTOMER_NAME_PATTERNS:
        m = re.search(pat, text)
        if m:
            return re.sub(r"\s+", "", m.group(0))
    return None


def _find_report_periods(text: str, expected_count: int) -> list[str]:
    """提取报告期年份标签"""
    found = PERIOD_PATTERN.findall(text)
    seen: set[str] = set()
    periods: list[str] = []
    for year, end_month in found:
        if end_month:
            label = f"{year}H{1 if int(end_month) <= 6 else 2}"
        else:
            label = year
        if label not in seen:
            seen.add(label)
            periods.append(label)
        if len(periods) >= expected_count:
            break
    return periods


def _collect_pages_with_keywords(reader: PDFReader, keywords: list[str]) -> list[int]:
    """返回包含任一关键词的页码集合(排序去重)"""
    pages: set[int] = set()
    for kw in keywords:
        for p in reader.search_keyword_pages(kw):
            pages.add(p)
    return sorted(pages)


def _try_extract_from_window(
    window: str,
    pages: list[PageText],
    strategy_name: str,
    keyword_used: str,
) -> Optional[ExtractionResult]:
    """在一段文本窗口里找 3 个合理的 top-1 百分比"""
    for match in TRIPLE_PERCENT_PATTERN.finditer(window):
        ratios = [float(g) / 100.0 for g in match.groups()]
        if not _is_plausible_top1_ratios(ratios):
            continue

        customer = _find_customer_name(window)
        periods = _find_report_periods(window, len(ratios))

        return ExtractionResult(
            success=True,
            confidence="high",
            top1_customer_name=customer,
            yearly_ratios=ratios,
            report_periods=periods if len(periods) == len(ratios) else [
                f"期{i + 1}" for i in range(len(ratios))
            ],
            source_pages=[p.page_number for p in pages],
            matched_section_keyword=f"{strategy_name} | 锚点={keyword_used}",
            raw_text_sample=window[:600],
            messages=[
                f"[{strategy_name}] 命中: 锚点关键词='{keyword_used}', "
                f"页码={[p.page_number for p in pages]}, 比例={[f'{r*100:.2f}%' for r in ratios]}"
            ],
            strategy_used=strategy_name,
        )
    return None


# ============================================================
# 各策略实现
# ============================================================

def _strategy_prose_first_customer(reader: PDFReader, log: list[str]) -> Optional[ExtractionResult]:
    """策略 A: 锚点'第一大客户' / '对第一大客户'"""
    anchors = ["对第一大客户", "公司第一大客户", "第一大客户"]
    candidate_pages = _collect_pages_with_keywords(reader, anchors)
    log.append(f"[A.prose_first_customer] 找到 {len(candidate_pages)} 个候选页: {candidate_pages[:10]}")

    for page_num in candidate_pages:
        pages = reader.get_pages_range(max(1, page_num - 1), page_num + 1)
        combined = "\n".join(p.text for p in pages)

        for kw in anchors:
            pos = combined.find(kw)
            if pos < 0:
                continue
            window = combined[pos:pos + 800]
            result = _try_extract_from_window(window, pages, "prose_first_customer", kw)
            if result:
                return result
    log.append(f"[A.prose_first_customer] 未在任何候选页找到合理的 top-1 占比组合")
    return None


def _strategy_front_matter_risk(reader: PDFReader, log: list[str]) -> Optional[ExtractionResult]:
    """策略 B: 在重大事项提示/重大风险章节里搜"""
    anchors = ["重大事项提示", "重大风险提示", "重大风险因素", "客户集中度风险", "客户依赖"]
    candidate_pages = _collect_pages_with_keywords(reader, anchors)
    log.append(f"[B.front_matter_risk] 找到 {len(candidate_pages)} 个候选页: {candidate_pages[:10]}")

    for page_num in candidate_pages:
        pages = reader.get_pages_range(page_num, page_num + 3)
        combined = "\n".join(p.text for p in pages)

        for kw in anchors:
            pos = combined.find(kw)
            if pos < 0:
                continue
            window = combined[pos:pos + 1500]
            result = _try_extract_from_window(window, pages, "front_matter_risk", kw)
            if result:
                return result
    log.append(f"[B.front_matter_risk] 未在风险章节附近找到合理的 top-1 占比组合")
    return None


def _strategy_named_customer(reader: PDFReader, log: list[str]) -> Optional[ExtractionResult]:
    """策略 C: 用具体客户名锚点"""
    anchors = ["中航工业A01", "中航工业 A01", "中航工业Ａ01"]
    candidate_pages = _collect_pages_with_keywords(reader, anchors)
    log.append(f"[C.named_customer] 找到 {len(candidate_pages)} 个候选页: {candidate_pages[:10]}")

    for page_num in candidate_pages:
        pages = reader.get_pages_range(max(1, page_num - 1), page_num + 1)
        combined = "\n".join(p.text for p in pages)

        for kw in anchors:
            pos = combined.find(kw)
            if pos < 0:
                continue
            window = combined[max(0, pos - 100):pos + 500]
            result = _try_extract_from_window(window, pages, "named_customer", kw)
            if result:
                return result
    log.append(f"[C.named_customer] 未在客户名锚点附近找到合理的 top-1 占比组合")
    return None


def _strategy_section_top5(reader: PDFReader, log: list[str]) -> Optional[ExtractionResult]:
    """策略 D(兜底): 前五大客户章节(可能抓到的是合计,低置信度)"""
    section_keywords = ["前五大客户", "前五名客户", "主要客户情况"]
    candidate_pages = _collect_pages_with_keywords(reader, section_keywords)
    log.append(f"[D.section_top5(兜底)] 找到 {len(candidate_pages)} 个候选页: {candidate_pages[:10]}")

    if not candidate_pages:
        return None

    first_page = candidate_pages[0]
    pages = reader.get_pages_range(first_page, first_page + 2)
    combined = "\n".join(p.text for p in pages)

    all_pcts = re.findall(r"(\d{1,3}\.\d{1,2})\s*%", combined)
    ratios = []
    for v in all_pcts[:6]:
        try:
            f = float(v) / 100.0
            if 0 < f <= 1:
                ratios.append(f)
        except ValueError:
            pass

    if not ratios:
        return None

    if _is_plausible_top1_ratios(ratios[:3]):
        confidence = "medium"
        message = "在前五大客户章节里发现疑似 top-1 占比(置信度中)"
    else:
        confidence = "low"
        message = "在前五大客户章节里只找到前五合计占比(>95%),不可作为 top-1 输入"

    log.append(f"[D.section_top5(兜底)] 在页 {first_page} 附近抓到 {len(ratios)} 个百分比")
    return ExtractionResult(
        success=False,
        confidence=confidence,
        top1_customer_name=_find_customer_name(combined),
        yearly_ratios=ratios,
        report_periods=_find_report_periods(combined, len(ratios)),
        source_pages=[p.page_number for p in pages],
        matched_section_keyword="section_top5",
        raw_text_sample=combined[:600],
        messages=[message],
        strategy_used="section_top5(兜底)",
    )


# ============================================================
# 主入口
# ============================================================

_STRATEGIES: list[tuple[str, Callable[[PDFReader, list[str]], Optional[ExtractionResult]]]] = [
    ("A.prose_first_customer", _strategy_prose_first_customer),
    ("B.front_matter_risk", _strategy_front_matter_risk),
    ("C.named_customer", _strategy_named_customer),
    ("D.section_top5", _strategy_section_top5),
]


def extract_customer_concentration(pdf_path: Path | str) -> ExtractionResult:
    """多策略并发抽取 + 选最优结果"""
    pdf_path = Path(pdf_path)
    diagnostics: list[str] = []
    attempts: list[ExtractionResult] = []

    with PDFReader(pdf_path) as reader:
        diagnostics.append(f"PDF 总页数: {reader.num_pages()}")

        for name, strategy in _STRATEGIES:
            attempt = strategy(reader, diagnostics)
            if attempt is not None:
                attempts.append(attempt)
                if attempt.success:
                    attempt.messages = diagnostics + attempt.messages
                    return attempt

    if attempts:
        best = max(attempts, key=lambda r: {"high": 3, "medium": 2, "low": 1}.get(r.confidence, 0))
        best.messages = diagnostics + best.messages
        return best

    return ExtractionResult(
        success=False,
        confidence="low",
        messages=diagnostics + ["所有策略均未命中,建议提供高分辨率扫描页或人工录入"],
    )


def result_to_dict(result: ExtractionResult) -> dict:
    return asdict(result)
