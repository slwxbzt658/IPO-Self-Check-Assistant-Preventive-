"""
支柱一·独立性 — 总指挥(Orchestrator)
=========================================

支柱一是整个系统的"主攻原生支柱",但它**不自己**做技术评估或财务测算。
它的真正职责是:
    1. 跑本地原生探针(L1 客户集中度 + L2 订单正当性)
    2. 在 L1 触发后,主动发起对支柱二、支柱三的跨支柱 API 调用
    3. 综合本地结论与跨支柱反馈,出具最终的独立性风险判决

这就是 04a 文档反复强调的"编排者"(Orchestrator)模式。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional

from src.probes.independence.probe_customer_concentration import (
    ConcentrationInput,
    ProbeResult as L1Result,
    evaluate_concentration,
)
from src.probes.independence.probe_order_legitimacy import (
    OrderLegitimacyInput,
    OrderLegitimacyResult,
    evaluate_order_legitimacy,
)
from src.probes.innovation.stub_tech_replaceability import assess_tech_replaceability
from src.probes.growth.stub_value_and_stability import assess_value_source_and_stability


# 风险等级的严重程度排序(越靠后越严重)
_RISK_LEVEL_ORDER = ["低", "中", "高", "重大"]


@dataclass
class Pillar1FinalVerdict:
    pillar: str
    company_name: str
    final_risk_level: str
    final_risk_score: int
    final_verdict_text: str
    l1_result: dict
    l2_result: Optional[dict]
    cross_pillar_calls: dict = field(default_factory=dict)
    synthesis_reasoning: str = ""
    cross_zone_signals: dict = field(default_factory=dict)


def _max_risk_level(levels: list[str]) -> str:
    """取列表中最严重的风险等级"""
    ordered = [lv for lv in levels if lv in _RISK_LEVEL_ORDER]
    if not ordered:
        return "低"
    return max(ordered, key=_RISK_LEVEL_ORDER.index)


def _synthesize_verdict_text(
    l1: L1Result,
    l2: Optional[OrderLegitimacyResult],
    tech_result: Optional[dict],
    value_result: Optional[dict],
) -> str:
    """把多源证据合成为一段定性判决文本"""
    if l2 is None:
        return f"L1 风险等级为【{l1.risk_level}】,未触发深穿透,初步判定独立性可控。"

    parts = []
    parts.append(
        f"L1【客户集中度】触发{l1.risk_level}级别(最新占比 {l1.latest_ratio*100:.2f}%, "
        f"{'连续上升' if l1.trend_is_increasing else '未持续上升'})"
    )
    parts.append(
        f"L2【订单正当性 6 维审查】统计 Pass={l2.pass_count} / "
        f"Warning={l2.warning_count} / Fail={l2.fail_count},判定为【{l2.risk_level}】"
    )
    if tech_result is not None:
        parts.append(
            f"支柱二回传:技术可替代性={tech_result['replaceability_level']},"
            f"定性={tech_result['verdict_for_pillar1']}"
        )
    if value_result is not None:
        parts.append(
            f"支柱三回传:价值来源={value_result['value_source']},"
            f"稳定性评分={value_result['stability_score']},"
            f"定性={value_result['verdict_for_pillar1']}"
        )

    return "综合结论: " + " | ".join(parts) + "。该公司实质属于丧失独立持续经营能力的恶性单向寄生型代工。"


def run_pillar1(
    customer_input: ConcentrationInput,
    order_input: OrderLegitimacyInput,
    prospectus_data: Optional[dict] = None,
) -> Pillar1FinalVerdict:
    """
    支柱一完整链路:
        L1 → 若触发(高/重大) → L2 + 跨支柱调用 → 综合判决
    """
    l1 = evaluate_concentration(customer_input)

    l2: Optional[OrderLegitimacyResult] = None
    tech_result: Optional[dict] = None
    value_result: Optional[dict] = None
    cross_zone_signals: dict = {}

    deep_dive_triggered = l1.risk_level in ("高", "重大")

    if deep_dive_triggered:
        l2 = evaluate_order_legitimacy(order_input)
        tech_result = assess_tech_replaceability(prospectus_data)
        value_result = assess_value_source_and_stability(prospectus_data)

        cross_zone_signals = {
            "to_zone_B": "强制提取各期专家顾问费的支付名单、背景及金额,核查新增客户是否通过裙带关系获取",
            "to_zone_C": "拉取实控人及大股东底层银行流水,核查代还款、暗盘借款及资金体外循环",
        }

    candidate_levels = [l1.risk_level]
    if l2 is not None:
        candidate_levels.append(l2.risk_level)
    if tech_result is not None and tech_result["replaceability_level"] == "HIGH":
        candidate_levels.append("高")
    if value_result is not None and value_result["stability_score"] < 40:
        candidate_levels.append("高")

    final_level = _max_risk_level(candidate_levels)

    base_score = max(
        l1.risk_score,
        l2.risk_score if l2 is not None else 0,
    )
    cross_pillar_bonus = 0
    if tech_result is not None and tech_result["verdict_for_pillar1"] == "恶性寄生":
        cross_pillar_bonus += 5
    if value_result is not None and value_result["verdict_for_pillar1"].startswith("代工"):
        cross_pillar_bonus += 5
    final_score = min(100, base_score + cross_pillar_bonus)

    verdict_text = _synthesize_verdict_text(l1, l2, tech_result, value_result)

    cross_pillar_calls = {}
    if tech_result is not None:
        cross_pillar_calls["pillar2.assess_tech_replaceability"] = tech_result
    if value_result is not None:
        cross_pillar_calls["pillar3.assess_value_source_and_stability"] = value_result

    reasoning = (
        f"判决合成: L1={l1.risk_level}({l1.risk_score}) + "
        f"L2={l2.risk_level if l2 else '未触发'}({l2.risk_score if l2 else 0}) + "
        f"跨支柱加成 +{cross_pillar_bonus} → 最终【{final_level}】({final_score})"
    )

    from src.probes.independence.probe_customer_concentration import result_to_dict as l1_to_dict
    from src.probes.independence.probe_order_legitimacy import result_to_dict as l2_to_dict

    return Pillar1FinalVerdict(
        pillar="支柱一·独立性",
        company_name=customer_input.company_name,
        final_risk_level=final_level,
        final_risk_score=final_score,
        final_verdict_text=verdict_text,
        l1_result=l1_to_dict(l1),
        l2_result=l2_to_dict(l2) if l2 is not None else None,
        cross_pillar_calls=cross_pillar_calls,
        synthesis_reasoning=reasoning,
        cross_zone_signals=cross_zone_signals,
    )


def verdict_to_dict(verdict: Pillar1FinalVerdict) -> dict:
    return asdict(verdict)
