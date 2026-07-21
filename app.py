"""
HawkEye · IPO 预审风险分析系统
================================

Gradio Web 界面入口。

运行方式:
    python app.py
    # 然后在浏览器打开 http://127.0.0.1:7860
"""

import os
import sys
import tempfile
from pathlib import Path

import gradio as gr

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline import run_full_analysis  # noqa: E402


# ── 风险等级 → 颜色标签 ──────────────────────────────────────
RISK_COLOR = {
    "重大": "🔴",
    "高":   "🟠",
    "中":   "🟡",
    "低":   "🟢",
}


def _format_extraction_info(result) -> str:
    ext = result.extraction
    if ext is None:
        return "未完成抽取"
    lines = [
        f"**命中关键词**：{ext.matched_section_keyword}",
        f"**抽取页码**：{ext.source_pages}",
        f"**第一大客户**：{ext.top1_customer_name or '未识别'}",
        f"**各期占比**：{[f'{r*100:.2f}%' for r in ext.yearly_ratios]}",
        f"**各期标签**：{ext.report_periods}",
        f"**置信度**：{ext.confidence}",
    ]
    return "\n".join(lines)


def _format_l1_result(result) -> str:
    if result.verdict_dict is None:
        return ""
    l1 = result.verdict_dict.get("l1_result", {})
    risk = l1.get("risk_level", "未知")
    icon = RISK_COLOR.get(risk, "⚪")
    lines = [
        f"**风险等级**：{icon} {risk}（{l1.get('risk_score', 0)}/100）",
        f"**最新占比**：{l1.get('latest_ratio', 0)*100:.2f}%",
        f"**逐年上升**：{'是' if l1.get('trend_is_increasing') else '否'}",
        f"**判定**：{l1.get('verdict', '')}",
    ]
    actions = l1.get("cross_layer_actions", [])
    if actions:
        lines.append("\n**触发的跨层指令**：")
        for a in actions:
            lines.append(f"- {a}")
    return "\n".join(lines)


def _format_l2_result(result) -> str:
    if result.verdict_dict is None:
        return ""
    l2 = result.verdict_dict.get("l2_result")
    if l2 is None:
        return "L2 未触发（L1 风险等级未达高/重大）"
    risk = l2.get("risk_level", "未知")
    icon = RISK_COLOR.get(risk, "⚪")
    lines = [
        f"**风险等级**：{icon} {risk}（{l2.get('risk_score', 0)}/100）",
        f"**统计**：Pass={l2.get('pass_count',0)}  "
        f"Warning={l2.get('warning_count',0)}  "
        f"Fail={l2.get('fail_count',0)}",
        "",
        "**各维度详情**：",
    ]
    verdict_icon = {"Pass": "✅", "Warning": "⚠️", "Fail": "❌"}
    for d in l2.get("dimensions", []):
        icon_d = verdict_icon.get(d.get("verdict", ""), "❓")
        lines.append(
            f"{icon_d} **{d.get('dimension_id')} {d.get('dimension_name')}**"
        )
        lines.append(f"　事实：{d.get('fact_summary', '')}")
        lines.append(f"　解释：{d.get('explanation', '')}")
    return "\n".join(lines)


def _format_l3_result(result) -> str:
    if result.verdict_dict is None:
        return ""
    l3 = result.verdict_dict.get("l3_result")
    if l3 is None:
        return "L3 未触发（L1 风险等级未达高/重大，或未提供商业地位数据）"
    risk = l3.get("risk_level", "未知")
    icon = RISK_COLOR.get(risk, "⚪")
    lines = [
        f"**风险等级**：{icon} {risk}（{l3.get('risk_score', 0)}/100）",
        f"**统计**：Pass={l3.get('pass_count', 0)}  "
        f"Warning={l3.get('warning_count', 0)}  "
        f"Fail={l3.get('fail_count', 0)}",
        "",
        f"**层级定性**：{l3.get('qualitative_verdict', '')}",
        "",
        "**各维度详情**：",
    ]
    verdict_icon = {"Pass": "✅", "Warning": "⚠️", "Fail": "❌"}
    for d in l3.get("dimensions", []):
        icon_d = verdict_icon.get(d.get("verdict", ""), "❓")
        lines.append(
            f"{icon_d} **{d.get('dimension_id')} {d.get('dimension_name')}**"
            f" — {d.get('verdict_label', '')}"
        )
        lines.append(f"　事实：{d.get('fact_summary', '')}")
        lines.append(f"　解释：{d.get('explanation', '')}")
    if l3.get("profit_stress_recommended"):
        lines.append("")
        lines.append(f"**跨支柱建议**：{l3.get('profit_stress_reason', '')}")
    return "\n".join(lines)


def _format_final_verdict(result) -> str:
    if result.verdict_dict is None:
        return ""
    v = result.verdict_dict
    risk = v.get("final_risk_level", "未知")
    icon = RISK_COLOR.get(risk, "⚪")
    lines = [
        f"## {icon} 综合风险等级：{risk}（{v.get('final_risk_score', 0)}/100）",
        "",
        f"**综合判定**：{v.get('final_verdict_text', '')}",
        "",
        f"**合成过程**：{v.get('synthesis_reasoning', '')}",
    ]
    signals = v.get("cross_zone_signals", {})
    if signals:
        lines.append("\n**跨区域搜查令**：")
        for zone, signal in signals.items():
            lines.append(f"- {zone}：{signal}")
    return "\n".join(lines)


def analyze(pdf_file, company_name: str, api_key: str) -> tuple:
    """
    Gradio 回调函数。
    返回：(抽取信息, L1结果, L2结果, L3结果, 综合判决, LLM报告, 状态)
    """
    if pdf_file is None:
        return "", "", "", "", "", "", "⚠️ 请先上传招股书 PDF"

    name = company_name.strip() or "待分析企业"
    key = api_key.strip() or None

    # 写入临时路径（Gradio 传来的是 NamedTemporaryFile 路径）
    pdf_path = pdf_file.name if hasattr(pdf_file, "name") else str(pdf_file)

    try:
        result = run_full_analysis(
            pdf_path,
            company_name=name,
            api_key=key,
            enable_llm=bool(key or os.environ.get("DEEPSEEK_API_KEY")),
        )
    except Exception as exc:
        return "", "", "", "", "", "", f"❌ 运行出错：{exc}"

    if not result.success and result.verdict_dict is None:
        return (
            _format_extraction_info(result),
            "",
            "",
            "",
            "",
            "",
            f"❌ {result.error_message}",
        )

    extraction_info = _format_extraction_info(result)
    l1_text = _format_l1_result(result)
    l2_text = _format_l2_result(result)
    l3_text = _format_l3_result(result)
    verdict_text = _format_final_verdict(result)

    llm_text = ""
    if result.explanation is not None:
        if result.explanation.success:
            llm_text = result.explanation.report_text
        else:
            llm_text = f"LLM 调用失败：{result.explanation.error_message}"

    status = "✅ 分析完成"
    if not result.explanation or not result.explanation.success:
        status += "（未启用 LLM 解释层，请填写 API Key）"

    return extraction_info, l1_text, l2_text, l3_text, verdict_text, llm_text, status


# ── Gradio 界面定义 ──────────────────────────────────────────

with gr.Blocks(
    title="HawkEye · IPO 预审风险分析",
    theme=gr.themes.Soft(),
) as demo:

    gr.Markdown(
        """
        # 🦅 HawkEye · IPO 预审风险分析系统
        **支柱一·独立性审查 Demo**

        上传招股书 PDF，系统自动提取客户集中度等关键指标，
        经多层探针判定后，生成带证据溯源的风险诊断报告。

        > 当前版本：支柱一 L1+L2+L3 探针已实现，支柱二/三远程模型使用 Stub。
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            pdf_input = gr.File(
                label="上传招股书 PDF",
                file_types=[".pdf"],
            )
            company_input = gr.Textbox(
                label="公司名称（可选）",
                placeholder="例：成都裕鸢航空智能制造股份有限公司",
            )
            api_key_input = gr.Textbox(
                label="DeepSeek API Key（可选，不填则跳过 LLM 报告）",
                placeholder="sk-...",
                type="password",
            )
            run_btn = gr.Button("🔍 开始分析", variant="primary")
            status_box = gr.Textbox(label="状态", interactive=False)

        with gr.Column(scale=2):
            with gr.Tab("📄 PDF 抽取"):
                extraction_output = gr.Markdown(label="抽取结果")
            with gr.Tab("🔴 L1 客户集中度"):
                l1_output = gr.Markdown(label="L1 探针结果")
            with gr.Tab("🔍 L2 订单正当性"):
                l2_output = gr.Markdown(label="L2 探针结果")
            with gr.Tab("💼 L3 商业地位"):
                l3_output = gr.Markdown(label="L3 探针结果")
            with gr.Tab("⚖️ 综合判决"):
                verdict_output = gr.Markdown(label="综合判决")
            with gr.Tab("📝 LLM 诊断报告"):
                llm_output = gr.Markdown(label="自然语言诊断报告")

    run_btn.click(
        fn=analyze,
        inputs=[pdf_input, company_input, api_key_input],
        outputs=[
            extraction_output,
            l1_output,
            l2_output,
            l3_output,
            verdict_output,
            llm_output,
            status_box,
        ],
    )

    gr.Markdown(
        """
        ---
        **数据说明**：所有分析数据均来源于公开披露文件，不构成投资建议。
        [GitHub](https://github.com/slwxbzt658/IPO-Self-Check-Assistant-Preventive-)
        """
    )


if __name__ == "__main__":
    demo.launch(share=False)
