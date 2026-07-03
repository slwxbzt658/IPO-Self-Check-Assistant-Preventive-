"""
P1-L1 客户集中度穿透探针
=========================

支柱一·独立性 第一层(表象数据预警)的本地原生探针。

法律依据:《首次公开发行股票注册管理办法》第十二条
        "发行人必须具备独立持续经营能力,严禁严重依赖导致丧失独立性"

设计原则(对应 04a 文档):
- 本探针只回答"集中度是否触发表象红线"
- 不回答"为什么集中"(由 L2 订单正当性模型负责)
- 不回答"被收割多少"(由 L3 议价权模型负责)
- 高/重大风险时,主动发出"跨层穿透指令"通知 L2 和 L3
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class ConcentrationInput:
    """探针输入:客户集中度的原始事实数据"""
    company_name: str
    top1_customer_name: str
    yearly_ratios: list[float]
    report_periods: list[str]
    evidence_source: dict


@dataclass
class ProbeResult:
    """探针输出:结构化判定结果"""
    probe_id: str
    probe_name: str
    triggered: bool
    risk_score: int
    risk_level: str
    verdict: str
    matched_rule: str
    latest_ratio: float
    trend_is_increasing: bool
    evidence_spans: list[dict] = field(default_factory=list)
    cross_layer_actions: list[str] = field(default_factory=list)
    legal_basis: dict = field(default_factory=dict)


# ============================================================
# 规则加载
# ============================================================

def load_rules_schema(schema_path: Optional[Path] = None) -> dict:
    """从 rules_schema.json 加载规则定义(规则与代码解耦)"""
    if schema_path is None:
        schema_path = Path(__file__).parent / "rules_schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 内部辅助函数
# ============================================================

def _is_monotonically_increasing(values: list[float]) -> bool:
    """连续逐年上升趋势"""
    if len(values) < 2:
        return False
    return all(values[i] < values[i + 1] for i in range(len(values) - 1))


def _match_threshold_rule(latest_ratio: float, rules: list[dict]) -> dict:
    """按 threshold_inclusive 从高到低匹配第一条满足的规则"""
    sorted_rules = sorted(
        rules,
        key=lambda r: r["threshold_inclusive"],
        reverse=True,
    )
    for rule in sorted_rules:
        if latest_ratio >= rule["threshold_inclusive"]:
            return rule
    return sorted_rules[-1]


# ============================================================
# 核心判定逻辑
# ============================================================

def evaluate_concentration(input_data: ConcentrationInput) -> ProbeResult:
    """
    主入口:执行客户集中度探针。

    算法:
        1. 取最近一期占比作为判定基准
        2. 在 rules_schema.json 定义的阈值表中匹配规则
        3. 若占比连续上升,在基础分数上加 bonus_score
        4. 若风险等级达 高/重大,生成"跨层穿透指令"
        5. 拼装结构化结果(含证据溯源)
    """
    schema = load_rules_schema()

    latest_ratio = input_data.yearly_ratios[-1]
    matched = _match_threshold_rule(latest_ratio, schema["threshold_rules"])

    trend_is_increasing = _is_monotonically_increasing(input_data.yearly_ratios)
    trend_bonus = schema["trend_amplification"]["bonus_score"] if trend_is_increasing else 0
    final_score = min(100, matched["risk_score"] + trend_bonus)

    evidence_spans = [
        {
            "field": "top1_customer_ratio",
            "year": period,
            "value": f"{ratio * 100:.2f}%",
        }
        for ratio, period in zip(input_data.yearly_ratios, input_data.report_periods)
    ]
    evidence_spans.append({
        "field": "source",
        "value": (
            f"{input_data.evidence_source['document']}"
            f" 第 {input_data.evidence_source['page']} 页"
            f" {input_data.evidence_source['section']}"
        ),
    })

    cross_layer_actions: list[str] = []
    dispatch = schema["cross_layer_dispatch"]
    if matched["risk_level"] in dispatch["triggered_when_risk_level_in"]:
        cross_layer_actions = list(dispatch["actions"])

    triggered = matched["risk_level"] in ("中", "高", "重大")

    return ProbeResult(
        probe_id=schema["probe_id"],
        probe_name=schema["probe_name"],
        triggered=triggered,
        risk_score=final_score,
        risk_level=matched["risk_level"],
        verdict=matched["verdict"],
        matched_rule=matched["name"],
        latest_ratio=latest_ratio,
        trend_is_increasing=trend_is_increasing,
        evidence_spans=evidence_spans,
        cross_layer_actions=cross_layer_actions,
        legal_basis=schema["legal_basis"],
    )


def result_to_dict(result: ProbeResult) -> dict:
    """结构化结果转 dict(便于 JSON 序列化)"""
    return asdict(result)
