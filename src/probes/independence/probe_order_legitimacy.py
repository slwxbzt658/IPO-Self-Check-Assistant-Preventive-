"""
P1-L2 订单获取正当性与暗盘审查探针(6 维)
==========================================

支柱一·独立性 第二层(订单正当性)的本地原生探针。

输入:结构化的订单获取相关事实(JSON)
输出:6 维各自判定 + 层级聚合结论 + 跨支柱触发指令

每个维度独立判定 Pass / Warning / Fail,然后按 Fail/Warning 计数聚合到
层级风险等级。这是 04a 文档 §5.2 的代码落地。
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path
from typing import Optional


VERDICT_PASS = "Pass"
VERDICT_WARNING = "Warning"
VERDICT_FAIL = "Fail"


# ============================================================
# 数据结构
# ============================================================

@dataclass
class OrderLegitimacyInput:
    """L2 探针输入:订单获取相关的结构化事实"""
    company_name: str
    company_history: dict
    qualifications: dict
    sales_efficiency: dict
    executive_background: dict
    order_acquisition_process: dict
    expense_anomalies: dict


@dataclass
class DimensionResult:
    """单个维度的判定结果"""
    dimension_id: str
    dimension_name: str
    verdict: str
    score: int
    fact_summary: str
    explanation: str


@dataclass
class OrderLegitimacyResult:
    probe_id: str
    probe_name: str
    triggered: bool
    risk_score: int
    risk_level: str
    fail_count: int
    warning_count: int
    pass_count: int
    dimensions: list[DimensionResult] = field(default_factory=list)
    aggregation_explanation: str = ""
    legal_basis: dict = field(default_factory=dict)


# ============================================================
# 规则加载
# ============================================================

def load_rules(rules_path: Optional[Path] = None) -> dict:
    if rules_path is None:
        rules_path = Path(__file__).parent / "order_legitimacy_rules.json"
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 单维度判定函数
# 每个函数接收 input 数据 + 规则定义,返回 DimensionResult
# ============================================================

def _months_between(start: str, end: str) -> int:
    """计算两个 'YYYY-MM' 字符串之间的整月数"""
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    return (ey - sy) * 12 + (em - sm)


def evaluate_d1_qualification(input_data: OrderLegitimacyInput, rule: dict) -> DimensionResult:
    cert = input_data.qualifications.get("military_security_cert", {})
    obtained = cert.get("obtained", False)
    verdict = VERDICT_PASS if obtained else VERDICT_FAIL
    return DimensionResult(
        dimension_id=rule["id"],
        dimension_name=rule["name"],
        verdict=verdict,
        score=rule["scoring"][verdict],
        fact_summary=f"保密资格证: 已获取={obtained}, 级别={cert.get('level', 'N/A')}",
        explanation=("具备最基础合规资质" if obtained else "缺乏合规资质,涉嫌无证经营"),
    )


def evaluate_d2_history_timing(input_data: OrderLegitimacyInput, rule: dict) -> DimensionResult:
    hist = input_data.company_history
    months = _months_between(hist["transformation_date"], hist["first_major_contract_date"])
    pass_min = rule["thresholds_months"]["pass_min"]
    warning_min = rule["thresholds_months"]["warning_min"]
    if months >= pass_min:
        verdict = VERDICT_PASS
    elif months >= warning_min:
        verdict = VERDICT_WARNING
    else:
        verdict = VERDICT_FAIL
    return DimensionResult(
        dimension_id=rule["id"],
        dimension_name=rule["name"],
        verdict=verdict,
        score=rule["scoring"][verdict],
        fact_summary=f"转型 {hist['transformation_date']} → 首笔大单 {hist['first_major_contract_date']}, 间隔 {months} 个月",
        explanation=(
            f"军工长周期认证通常需 {pass_min} 个月以上"
            f";本案 {months} 个月"
            + ("、严重违背常识,涉嫌裙带或高层输送" if verdict == VERDICT_FAIL else
               "、偏短需要警惕" if verdict == VERDICT_WARNING else
               "、符合常识")
        ),
    )


def evaluate_d3_sales_efficiency(input_data: OrderLegitimacyInput, rule: dict) -> DimensionResult:
    se = input_data.sales_efficiency
    headcount = se["sales_headcount"]
    revenue = se["revenue_supported_cny"]
    per_person = revenue / max(1, headcount)
    pass_max = rule["thresholds_cny_per_person"]["pass_max"]
    warning_max = rule["thresholds_cny_per_person"]["warning_max"]
    if per_person < pass_max:
        verdict = VERDICT_PASS
    elif per_person < warning_max:
        verdict = VERDICT_WARNING
    else:
        verdict = VERDICT_FAIL
    return DimensionResult(
        dimension_id=rule["id"],
        dimension_name=rule["name"],
        verdict=verdict,
        score=rule["scoring"][verdict],
        fact_summary=f"{se['year']} 年销售 {headcount} 人撬动 {revenue/1e8:.2f} 亿营收, 人均 {per_person/1e4:.0f} 万",
        explanation=(
            "人均撬动收入处于行业合理区间" if verdict == VERDICT_PASS else
            "人均撬动收入偏高,需关注是否存在编外推手" if verdict == VERDICT_WARNING else
            "人均撬动收入显著异常,强烈暗示存在不在编制内的隐形获客推手"
        ),
    )


def evaluate_d4_rotating_door(input_data: OrderLegitimacyInput, rule: dict) -> DimensionResult:
    eb = input_data.executive_background
    detected = eb.get("rotating_door_detected", False)
    verdict = VERDICT_FAIL if detected else VERDICT_PASS
    return DimensionResult(
        dimension_id=rule["id"],
        dimension_name=rule["name"],
        verdict=verdict,
        score=rule["scoring"][verdict],
        fact_summary=eb.get("note", "无详细背景信息"),
        explanation=(
            "存在董监高来自大客户关键岗位的旋转门" if detected
            else "未发现明显直接的离职输送表象"
        ),
    )


def evaluate_d5_acquisition_process(input_data: OrderLegitimacyInput, rule: dict) -> DimensionResult:
    op = input_data.order_acquisition_process
    disclosed = op.get("details_disclosed", False)
    verdict = VERDICT_PASS if disclosed else VERDICT_WARNING
    return DimensionResult(
        dimension_id=rule["id"],
        dimension_name=rule["name"],
        verdict=verdict,
        score=rule["scoring"][verdict],
        fact_summary=f"获客方式自述: {op.get('self_described_method', 'N/A')}; 细节披露={disclosed}",
        explanation=(
            "招投标细节充分披露" if disclosed
            else "对早期如何认识客户缺乏细节支撑,转化为对保荐人的强核查指令"
        ),
    )


def evaluate_d6_expense_anomaly(input_data: OrderLegitimacyInput, rule: dict) -> DimensionResult:
    ea = input_data.expense_anomalies
    unusual_high = ea.get("manufacturing_expense_unusual_high", False)
    breakdown_missing = not ea.get("consulting_fee_breakdown_disclosed", True)
    if unusual_high and breakdown_missing:
        verdict = VERDICT_WARNING
    else:
        verdict = VERDICT_PASS
    return DimensionResult(
        dimension_id=rule["id"],
        dimension_name=rule["name"],
        verdict=verdict,
        score=rule["scoring"][verdict],
        fact_summary=ea.get("note", "无费用结构异常信号"),
        explanation=(
            "制造费用偏高且咨询费明细未披露,高度疑似隐藏外部顾问费" if verdict == VERDICT_WARNING
            else "费用结构未发现异常"
        ),
    )


# 维度 ID → 判定函数 的路由表
_DIMENSION_EVALUATORS = {
    "D1": evaluate_d1_qualification,
    "D2": evaluate_d2_history_timing,
    "D3": evaluate_d3_sales_efficiency,
    "D4": evaluate_d4_rotating_door,
    "D5": evaluate_d5_acquisition_process,
    "D6": evaluate_d6_expense_anomaly,
}


# ============================================================
# 层级聚合
# ============================================================

def _aggregate_level(fail_count: int, warning_count: int, agg_rules: list[dict]) -> tuple[str, int]:
    """按 Fail/Warning 计数聚合层级。规则顺序即优先级(从严到松)。"""
    if fail_count >= 2 or (fail_count >= 1 and warning_count >= 2):
        rule = agg_rules[0]
    elif fail_count >= 1:
        rule = agg_rules[1]
    elif warning_count >= 1:
        rule = agg_rules[2]
    else:
        rule = agg_rules[3]
    return rule["name"], rule["risk_score"]


# ============================================================
# 主入口
# ============================================================

def evaluate_order_legitimacy(input_data: OrderLegitimacyInput) -> OrderLegitimacyResult:
    schema = load_rules()

    dimension_results: list[DimensionResult] = []
    for rule in schema["dimensions"]:
        evaluator = _DIMENSION_EVALUATORS[rule["id"]]
        dimension_results.append(evaluator(input_data, rule))

    fail_count = sum(1 for d in dimension_results if d.verdict == VERDICT_FAIL)
    warning_count = sum(1 for d in dimension_results if d.verdict == VERDICT_WARNING)
    pass_count = sum(1 for d in dimension_results if d.verdict == VERDICT_PASS)

    risk_level, risk_score = _aggregate_level(
        fail_count, warning_count, schema["aggregation"]["thresholds"]
    )
    triggered = risk_level != "低"

    explanation = (
        f"6 维审查统计: Pass={pass_count}, Warning={warning_count}, Fail={fail_count}。"
        f"按聚合规则判定为【{risk_level}】。"
    )

    return OrderLegitimacyResult(
        probe_id=schema["probe_id"],
        probe_name=schema["probe_name"],
        triggered=triggered,
        risk_score=risk_score,
        risk_level=risk_level,
        fail_count=fail_count,
        warning_count=warning_count,
        pass_count=pass_count,
        dimensions=dimension_results,
        aggregation_explanation=explanation,
        legal_basis=schema["legal_basis"],
    )


def result_to_dict(result: OrderLegitimacyResult) -> dict:
    return asdict(result)
