"""
裕鸢航空案例 — 支柱一·完整链路演示
====================================

链路:
    L1 客户集中度 → 触发深穿透
        → L2 订单正当性 6 维审查
        → 跨支柱调用: 支柱二·技术可替代性(Stub)
        → 跨支柱调用: 支柱三·价值与稳定性(Stub)
        → 综合判决
        → 跨区域(B/C)搜查令预埋

运行方式:
    python demos/run_pillar1_full_demo.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.probes.independence.probe_customer_concentration import ConcentrationInput  # noqa: E402
from src.probes.independence.probe_order_legitimacy import OrderLegitimacyInput  # noqa: E402
from src.probes.independence.probe_commercial_status import CommercialStatusInput  # noqa: E402
from src.probes.independence.orchestrator import run_pillar1, verdict_to_dict  # noqa: E402


def load_customer_input() -> ConcentrationInput:
    path = Path(__file__).parent / "demo_input" / "yuyuan_customer_data.json"
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return ConcentrationInput(
        company_name=raw["company_name"],
        top1_customer_name=raw["top1_customer"]["name"],
        yearly_ratios=raw["top1_customer"]["yearly_ratios"],
        report_periods=raw["report_period"],
        evidence_source=raw["evidence_source"],
    )


def load_order_input() -> OrderLegitimacyInput:
    path = Path(__file__).parent / "demo_input" / "yuyuan_order_data.json"
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return OrderLegitimacyInput(
        company_name=raw["company_name"],
        company_history=raw["company_history"],
        qualifications=raw["qualifications"],
        sales_efficiency=raw["sales_efficiency"],
        executive_background=raw["executive_background"],
        order_acquisition_process=raw["order_acquisition_process"],
        expense_anomalies=raw["expense_anomalies"],
    )


def load_commercial_input() -> CommercialStatusInput:
    path = Path(__file__).parent / "demo_input" / "yuyuan_commercial_status_data.json"
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return CommercialStatusInput(
        company_name=raw["company_name"],
        pricing_power=raw["pricing_power"],
        contract_status=raw["contract_status"],
        cost_passthrough=raw["cost_passthrough"],
        evidence_source=raw.get("evidence_source", {}),
    )


def print_section_header(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def pretty_print_verdict(v: dict) -> None:
    print_section_header(f"HawkEye  |  {v['pillar']}  最终判决")
    print(f"\n  公司:{v['company_name']}")
    print(f"  风险等级:{v['final_risk_level']}")
    print(f"  风险分数:{v['final_risk_score']} / 100")
    print(f"\n  综合判定:\n    {v['final_verdict_text']}")
    print(f"\n  合成过程:\n    {v['synthesis_reasoning']}")

    print_section_header("L1  表象数据预警(客户集中度)")
    l1 = v["l1_result"]
    print(f"  最新占比 {l1['latest_ratio']*100:.2f}%, 逐年上升: {l1['trend_is_increasing']}")
    print(f"  风险等级: {l1['risk_level']}({l1['risk_score']}分)")
    print(f"  判定:    {l1['verdict']}")
    if l1["cross_layer_actions"]:
        print(f"  L1 主动发出的跨层指令:")
        for action in l1["cross_layer_actions"]:
            print(f"    -> {action}")

    if v["l2_result"]:
        print_section_header("L2  订单获取正当性 6 维审查")
        l2 = v["l2_result"]
        print(f"  Pass={l2['pass_count']}  Warning={l2['warning_count']}  Fail={l2['fail_count']}")
        print(f"  风险等级: {l2['risk_level']}({l2['risk_score']}分)")
        print(f"  说明:    {l2['aggregation_explanation']}")
        print(f"\n  各维度详情:")
        for d in l2["dimensions"]:
            tag = {"Pass": "[ OK ]", "Warning": "[WARN]", "Fail": "[FAIL]"}[d["verdict"]]
            print(f"    {tag} {d['dimension_id']} {d['dimension_name']}")
            print(f"           事实: {d['fact_summary']}")
            print(f"           解释: {d['explanation']}")
    else:
        print("\n  L2 未触发(L1 未达高/重大,无需深穿透)")

    if v.get("l3_result"):
        print_section_header("L3  商业地位与议价权定性")
        l3 = v["l3_result"]
        print(f"  Pass={l3['pass_count']}  Warning={l3['warning_count']}  Fail={l3['fail_count']}")
        print(f"  风险等级: {l3['risk_level']}({l3['risk_score']}分)")
        print(f"  层级定性: {l3['qualitative_verdict']}")
        print(f"\n  各维度详情:")
        for d in l3["dimensions"]:
            tag = {"Pass": "[ OK ]", "Warning": "[WARN]", "Fail": "[FAIL]"}[d["verdict"]]
            print(f"    {tag} {d['dimension_id']} {d['dimension_name']} — {d['verdict_label']}")
            print(f"           事实: {d['fact_summary']}")
            print(f"           解释: {d['explanation']}")
        if l3.get("profit_stress_recommended"):
            print(f"\n  跨支柱建议: {l3['profit_stress_reason']}")
    else:
        print("\n  L3 未触发")

    if v["cross_pillar_calls"]:
        print_section_header("跨支柱 API 调用结果(Stub)")
        for api_name, result in v["cross_pillar_calls"].items():
            print(f"\n  >> {api_name}")
            for k, val in result.items():
                if k == "_meta":
                    continue
                print(f"     {k}: {val}")
            if "_meta" in result and result["_meta"].get("is_stub"):
                print(f"     (注:此为 Stub 实现,真实模型见 {result['_meta']['implemented_in']})")

    if v["cross_zone_signals"]:
        print_section_header("跨区域搜查令(预埋至区域 B / C)")
        for zone, signal in v["cross_zone_signals"].items():
            print(f"\n  {zone}: {signal}")
    print()


def main() -> None:
    customer_input = load_customer_input()
    order_input = load_order_input()
    commercial_input = load_commercial_input()

    verdict = run_pillar1(customer_input, order_input, commercial_input, prospectus_data=None)
    verdict_dict = verdict_to_dict(verdict)

    output_dir = Path(__file__).parent / "demo_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "yuyuan_pillar1_full_verdict.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(verdict_dict, f, ensure_ascii=False, indent=2)

    pretty_print_verdict(verdict_dict)
    print(f"  完整 JSON 已保存:")
    print(f"    {output_path}\n")


if __name__ == "__main__":
    main()
