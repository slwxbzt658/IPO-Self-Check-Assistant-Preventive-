"""
裕鸢航空 — 支柱一完整链路 + LLM 自然语言诊断报告
==================================================

链路:
    手工/JSON 输入 → L1 + L2 探针 → Orchestrator 综合判决
    → DeepSeek 生成自然语言诊断书

运行前准备:
    1. pip install openai python-dotenv
    2. 复制 .env.example 为 .env，填入 DEEPSEEK_API_KEY

运行:
    python demos/run_pillar1_with_llm.py
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.probes.independence.probe_customer_concentration import ConcentrationInput  # noqa: E402
from src.probes.independence.probe_order_legitimacy import OrderLegitimacyInput  # noqa: E402
from src.probes.independence.orchestrator import run_pillar1, verdict_to_dict  # noqa: E402
from src.report.llm_explainer import generate_explanation  # noqa: E402


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


def main() -> None:
    print("\n" + "=" * 64)
    print("  HawkEye  |  支柱一完整链路 + LLM 解释层")
    print("=" * 64)

    customer_input = load_customer_input()
    order_input = load_order_input()
    verdict = run_pillar1(customer_input, order_input, prospectus_data=None)
    verdict_dict = verdict_to_dict(verdict)

    print(f"\n  结构化判决已完成")
    print(f"  公司:     {verdict_dict['company_name']}")
    print(f"  风险等级: {verdict_dict['final_risk_level']} ({verdict_dict['final_risk_score']}/100)")

    print("\n  正在调用 DeepSeek 生成自然语言诊断报告...")
    explanation = generate_explanation(verdict_dict)

    output_dir = Path(__file__).parent / "demo_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not explanation.success:
        print(f"\n  LLM 解释层失败: {explanation.error_message}")
        json_path = output_dir / "yuyuan_pillar1_verdict_only.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(verdict_dict, f, ensure_ascii=False, indent=2)
        print(f"  结构化 JSON 已保存: {json_path}\n")
        sys.exit(1)

    print("\n" + "=" * 64)
    print("  自然语言诊断报告")
    print("=" * 64 + "\n")
    print(explanation.report_text)

    full_output = {
        "structured_verdict": verdict_dict,
        "llm_report": explanation.report_text,
        "llm_meta": {
            "model": explanation.model,
            "success": explanation.success,
        },
    }
    output_path = output_dir / "yuyuan_pillar1_with_llm_report.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_output, f, ensure_ascii=False, indent=2)

    report_md_path = output_dir / "yuyuan_pillar1_diagnosis_report.md"
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(f"# HawkEye 诊断报告\n\n")
        f.write(f"**公司**: {verdict_dict['company_name']}\n\n")
        f.write(f"**风险等级**: {verdict_dict['final_risk_level']} ({verdict_dict['final_risk_score']}/100)\n\n")
        f.write("---\n\n")
        f.write(explanation.report_text)
        f.write("\n")

    print("\n" + "=" * 64)
    print(f"  完整结果已保存:")
    print(f"    JSON: {output_path}")
    print(f"    Markdown: {report_md_path}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
