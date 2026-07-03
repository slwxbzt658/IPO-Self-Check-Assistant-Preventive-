"""
裕鸢航空案例 — 支柱一·L1 客户集中度探针演示

运行方式(在项目根目录执行):
    python demos/run_pillar1_demo.py

预期输出:
    1. 控制台打印结构化判定结果
    2. 在 demos/demo_output/ 下生成完整的 JSON 结果
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.probes.independence.probe_customer_concentration import (  # noqa: E402
    ConcentrationInput,
    evaluate_concentration,
    result_to_dict,
)


def load_demo_input() -> ConcentrationInput:
    """读取裕鸢的人工录入数据并构造探针输入对象"""
    input_path = Path(__file__).parent / "demo_input" / "yuyuan_customer_data.json"
    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return ConcentrationInput(
        company_name=raw["company_name"],
        top1_customer_name=raw["top1_customer"]["name"],
        yearly_ratios=raw["top1_customer"]["yearly_ratios"],
        report_periods=raw["report_period"],
        evidence_source=raw["evidence_source"],
    )


def save_result_as_json(result_dict: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "yuyuan_customer_concentration_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)
    return output_path


def pretty_print(result_dict: dict, company_name: str) -> None:
    print("=" * 64)
    print(f"  HawkEye  |  支柱一·L1 表象数据预警")
    print(f"  案例:{company_name}")
    print("=" * 64)
    print(f"\n  探针 ID    : {result_dict['probe_id']}")
    print(f"  探针名称   : {result_dict['probe_name']}")
    print(f"  匹配规则   : {result_dict['matched_rule']}")
    print(f"  最新占比   : {result_dict['latest_ratio'] * 100:.2f}%")
    print(f"  逐年上升   : {'是' if result_dict['trend_is_increasing'] else '否'}")
    print(f"  是否触发   : {'YES' if result_dict['triggered'] else 'NO'}")
    print(f"  风险分数   : {result_dict['risk_score']} / 100")
    print(f"  风险等级   : {result_dict['risk_level']}")
    print(f"\n  判定结论:")
    print(f"    {result_dict['verdict']}")

    print(f"\n  证据片段:")
    for span in result_dict["evidence_spans"]:
        if "year" in span:
            print(f"    [{span['year']}] {span['field']} = {span['value']}")
        else:
            print(f"    [来源] {span['value']}")

    if result_dict["cross_layer_actions"]:
        print(f"\n  跨层穿透指令(触发 L2 / L3 / 跨支柱调用):")
        for action in result_dict["cross_layer_actions"]:
            print(f"    -> {action}")

    print(f"\n  法律依据:")
    for k, v in result_dict["legal_basis"].items():
        print(f"    {k}: {v}")
    print()


def main() -> None:
    input_data = load_demo_input()
    result = evaluate_concentration(input_data)
    result_dict = result_to_dict(result)

    output_dir = Path(__file__).parent / "demo_output"
    output_path = save_result_as_json(result_dict, output_dir)

    pretty_print(result_dict, input_data.company_name)
    print(f"  完整 JSON 已保存:")
    print(f"    {output_path}")
    print()


if __name__ == "__main__":
    main()
