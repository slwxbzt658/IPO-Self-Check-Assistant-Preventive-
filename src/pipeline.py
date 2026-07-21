"""
HawkEye 主分析流水线
====================

把"PDF → 抽取 → 探针判定 → LLM 报告"整条链路封装成一个函数。
供 Gradio 界面（app.py）和命令行 Demo 共同调用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.extract.customer_concentration_extractor import (
    ExtractionResult,
    extract_customer_concentration,
)
from src.probes.independence.probe_customer_concentration import (
    ConcentrationInput,
    evaluate_concentration,
)
from src.probes.independence.probe_order_legitimacy import (
    OrderLegitimacyInput,
    evaluate_order_legitimacy,
)
from src.probes.independence.probe_commercial_status import (
    CommercialStatusInput,
)
from src.probes.independence.orchestrator import (
    Pillar1FinalVerdict,
    run_pillar1,
    verdict_to_dict,
)
from src.report.llm_explainer import ExplanationResult, generate_explanation


@dataclass
class PipelineResult:
    success: bool
    error_message: str = ""

    extraction: Optional[ExtractionResult] = None
    verdict: Optional[Pillar1FinalVerdict] = None
    verdict_dict: Optional[dict] = None
    explanation: Optional[ExplanationResult] = None


def _build_order_input(company_name: str) -> OrderLegitimacyInput:
    """
    L2 探针的输入目前是手工录入的裕鸢数据。
    后续版本会接入 PDF 自动抽取，当前用固定数据占位。
    """
    return OrderLegitimacyInput(
        company_name=company_name,
        company_history={
            "transformation_date": "2017-03",
            "first_major_contract_date": "2018-08",
            "first_major_customer": "中航工业 A01 单位",
            "note": "2017年3月转型，2018年8月进入核心供应链",
        },
        qualifications={
            "military_security_cert": {
                "obtained": True,
                "level": "武器装备科研生产单位三级保密资格",
                "date": "2017-08",
            }
        },
        sales_efficiency={
            "year": 2019,
            "sales_headcount": 4,
            "revenue_supported_cny": 100_000_000,
            "note": "报告期初4名销售人员撬动过亿军工订单",
        },
        executive_background={
            "rotating_door_detected": False,
            "note": "实控人曾就职于沈阳黎明，未在A01关键岗位任职",
        },
        order_acquisition_process={
            "self_described_method": "招投标、比选、商务谈判",
            "details_disclosed": False,
            "note": "对早期如何认识客户缺乏细节支撑",
        },
        expense_anomalies={
            "manufacturing_expense_unusual_high": True,
            "consulting_fee_breakdown_disclosed": False,
            "note": "制造费用偏高，疑似隐藏外部顾问费",
        },
    )


def _build_commercial_status_input(company_name: str) -> CommercialStatusInput:
    """L3 探针输入目前是手工录入的裕鸢数据。"""
    return CommercialStatusInput(
        company_name=company_name,
        pricing_power={
            "provisional_price_ratio_pct": 59.22,
            "year": 2020,
            "uses_price_reduction_strategy": True,
            "three_vendor_bidding_since_year": 2021,
            "core_customer": "中航工业 A01 单位",
            "note": "2020 年暂定价合同占比 59.22%; 存在主动降价与三方竞价压力",
        },
        contract_status={
            "deliver_before_contract_ratio_pct": 41.37,
            "year": 2020,
            "note": "2020 年先发货后签合同占比 41.37%",
        },
        cost_passthrough={
            "product_name": "机体结构件",
            "margin_from_pct": 52,
            "margin_to_pct": 45,
            "forced_by_customer": "中航工业 A01 单位",
            "below_cost_stoppage": True,
            "note": "核心产品毛利率由 52% 降至 45%, 存在低于成本被迫停工",
        },
        evidence_source={
            "document": "招股书 V1.0（手工录入）",
            "sections": ["重大事项提示", "业务模式", "毛利率分析"],
        },
    )


def run_full_analysis(
    pdf_path: str | Path,
    *,
    company_name: str = "待分析企业",
    api_key: Optional[str] = None,
    enable_llm: bool = True,
) -> PipelineResult:
    """
    完整分析流水线：PDF → 抽取 → 探针 → LLM 报告

    Args:
        pdf_path:     招股书 PDF 路径
        company_name: 公司名称（可由界面传入）
        api_key:      DeepSeek API Key（空则从环境变量读取）
        enable_llm:   是否启用 LLM 解释层（调试时可关闭节省费用）
    """
    pdf_path = Path(pdf_path)
    result = PipelineResult(success=False)

    # ── Step 1: PDF 抽取 ────────────────────────────────────
    extraction = extract_customer_concentration(pdf_path)
    result.extraction = extraction

    if not extraction.success or len(extraction.yearly_ratios) < 2:
        result.error_message = (
            f"PDF 抽取失败或数据不足（置信度：{extraction.confidence}）。\n"
            f"日志：{'; '.join(extraction.messages)}"
        )
        return result

    # ── Step 2: L1 探针 ─────────────────────────────────────
    l1_input = ConcentrationInput(
        company_name=company_name,
        top1_customer_name=extraction.top1_customer_name or "未知客户",
        yearly_ratios=extraction.yearly_ratios,
        report_periods=extraction.report_periods,
        evidence_source={
            "document": "招股书（PDF 自动抽取）",
            "page": extraction.source_pages[0] if extraction.source_pages else 0,
            "section": extraction.matched_section_keyword or "未知章节",
        },
    )

    # ── Step 3: L2 / L3 探针（暂用固定数据）─────────────────
    l2_input = _build_order_input(company_name)
    l3_input = _build_commercial_status_input(company_name)

    # ── Step 4: 编排器综合判决 ───────────────────────────────
    verdict = run_pillar1(l1_input, l2_input, l3_input, prospectus_data=None)
    result.verdict = verdict
    result.verdict_dict = verdict_to_dict(verdict)

    # ── Step 5: LLM 解释层 ──────────────────────────────────
    if enable_llm:
        explanation = generate_explanation(result.verdict_dict, api_key=api_key)
        result.explanation = explanation
        if not explanation.success:
            result.error_message = f"LLM 调用失败：{explanation.error_message}"

    result.success = True
    return result
