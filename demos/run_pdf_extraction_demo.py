"""
PDF 自动抽取 → L1 探针 完整链路演示
======================================

链路:
    招股书 PDF
      → 客户集中度抽取器 (src/extract/)
      → 转换为 ConcentrationInput
      → L1 探针(src/probes/independence/probe_customer_concentration.py)
      → 结构化输出

运行方式:
    python demos/run_pdf_extraction_demo.py

预期 PDF 位置(可在 main() 中修改):
    data/raw/yuyuan/yuyuan_prospectus_v1.pdf
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.extract.customer_concentration_extractor import (  # noqa: E402
    extract_customer_concentration,
    result_to_dict as extraction_to_dict,
)
from src.probes.independence.probe_customer_concentration import (  # noqa: E402
    ConcentrationInput,
    evaluate_concentration,
    result_to_dict as probe_to_dict,
)


YUYUAN_DATA_ROOT = (
    Path(__file__).resolve().parent.parent
    / "data" / "raw" / "yuyuan"
)

EXPECTED_FILENAME = "yuyuan_prospectus_v1.pdf"


def section(title: str) -> None:
    print("\n" + "=" * 64)
    print(f"  {title}")
    print("=" * 64)


def discover_pdf(search_root: Path, preferred_filename: str) -> tuple[Path | None, str]:
    """
    自动发现招股书 PDF。
    返回 (路径, 状态消息)。
    大小写不敏感(适配 Windows + 不同的命名习惯)。
    """
    if not search_root.exists():
        return None, f"目录不存在: {search_root}"

    all_pdfs = list(search_root.rglob("*.pdf"))

    print(f"\n  扫描目录:{search_root}")
    print(f"  发现 {len(all_pdfs)} 份 PDF:")
    for p in all_pdfs:
        print(f"    - {p.relative_to(search_root)}")

    if len(all_pdfs) == 0:
        return None, f"未发现 PDF。请把招股书放进 {search_root}(或子目录)。"

    preferred_lower = preferred_filename.lower()
    exact_matches = [p for p in all_pdfs if p.name.lower() == preferred_lower]
    if exact_matches:
        return exact_matches[0], "按文件名精确匹配成功"

    keyword_matches = [
        p for p in all_pdfs
        if "prospectus" in p.name.lower()
        or "招股" in p.name
        or "招股说明书" in p.name
    ]
    if len(keyword_matches) == 1:
        return keyword_matches[0], "按关键词(招股/prospectus)模糊匹配到唯一一份"

    if len(all_pdfs) == 1:
        return all_pdfs[0], "未找到精确匹配,但目录内只有一份 PDF,自动选用"

    msg_lines = [
        f"无法自动判断哪份是招股书(共 {len(all_pdfs)} 份候选)。",
        f"",
        f"  解决方法(任选其一):",
        f"    1. 把招股书改名为 {preferred_filename}(其他 PDF 保持原名)",
        f"    2. 在文件名里包含\"招股\"或\"prospectus\"关键词(且只有一份)",
    ]
    return None, "\n".join(msg_lines)


def main() -> None:
    pdf_path, status = discover_pdf(YUYUAN_DATA_ROOT, EXPECTED_FILENAME)
    if pdf_path is None:
        print(f"\n  {status}\n")
        sys.exit(1)
    print(f"\n  自动发现 PDF:{pdf_path}")
    print(f"  状态:        {status}")

    section("Step 1  PDF 抽取")
    extraction = extract_customer_concentration(pdf_path)

    print(f"\n  抽取成功:    {extraction.success}")
    print(f"  置信度:      {extraction.confidence}")
    print(f"  采用策略:    {extraction.strategy_used}")
    print(f"  命中关键词:  {extraction.matched_section_keyword}")
    print(f"  涉及页码:    {extraction.source_pages}")
    print(f"  第一大客户:  {extraction.top1_customer_name}")
    print(f"  各期占比:    {[f'{r*100:.2f}%' for r in extraction.yearly_ratios]}")
    print(f"  各期标签:    {extraction.report_periods}")
    if extraction.messages:
        print(f"\n  策略日志(诊断用):")
        for msg in extraction.messages:
            print(f"    {msg}")

    output_dir = Path(__file__).parent / "demo_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    extraction_dump_path = output_dir / "yuyuan_pdf_extraction.json"
    with open(extraction_dump_path, "w", encoding="utf-8") as f:
        json.dump(extraction_to_dict(extraction), f, ensure_ascii=False, indent=2)
    print(f"\n  抽取原始结果已保存:{extraction_dump_path}")

    if not extraction.success:
        print("\n  抽取置信度不足,无法进入 L1 探针环节。")
        print(f"  请检查 {extraction_dump_path} 中的 raw_text_sample,可能需要调整关键词或正则。")
        sys.exit(0)

    section("Step 2  转换为 L1 探针输入")
    probe_input = ConcentrationInput(
        company_name="成都裕鸢航空智能制造股份有限公司",
        top1_customer_name=extraction.top1_customer_name or "未知",
        yearly_ratios=extraction.yearly_ratios,
        report_periods=extraction.report_periods,
        evidence_source={
            "document": "招股书 V1.0(PDF 自动抽取)",
            "page": extraction.source_pages[0] if extraction.source_pages else 0,
            "section": extraction.matched_section_keyword or "未知章节",
        },
    )
    print(f"  {probe_input}")

    section("Step 3  L1 探针判定")
    probe_result = evaluate_concentration(probe_input)
    print(f"  匹配规则:    {probe_result.matched_rule}")
    print(f"  风险等级:    {probe_result.risk_level}({probe_result.risk_score}/100)")
    print(f"  是否触发:    {'YES' if probe_result.triggered else 'NO'}")
    print(f"  判定:        {probe_result.verdict}")
    if probe_result.cross_layer_actions:
        print(f"\n  跨层穿透指令:")
        for action in probe_result.cross_layer_actions:
            print(f"    -> {action}")

    final_path = output_dir / "yuyuan_pdf_to_probe_full.json"
    with open(final_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "extraction": extraction_to_dict(extraction),
                "probe_result": probe_to_dict(probe_result),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n  全链路结果已保存:{final_path}\n")


if __name__ == "__main__":
    main()
