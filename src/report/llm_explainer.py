"""
LLM 自然语言解释层
====================

将支柱一 Orchestrator 的结构化 JSON 判决，转换为可读的自然语言诊断报告。

设计原则（对应 Eval 框架中的幻觉拦截）:
    - LLM 只能基于传入的 verdict JSON 说话，不得编造新事实
    - 报告必须引用 JSON 中的 evidence_spans / fact_summary
    - API Key 从环境变量读取，不写入代码或 Git

DeepSeek 使用 OpenAI 兼容接口:
    base_url = https://api.deepseek.com
    model    = deepseek-chat
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional


DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"


SYSTEM_PROMPT = """你是 HawkEye IPO 预审系统的「主编」角色，负责将结构化探针结果写成自然语言诊断报告。

【硬性规则 — 违反任何一条即为失败】
1. 只能使用用户消息中 JSON 里已有的事实和数据，禁止编造招股书内容、数字、客户名或法规条文。
2. 每个风险结论必须标注证据来源（来自 JSON 中的 evidence_spans、fact_summary 或 explanation 字段）。
3. 若 JSON 中某字段为 Stub（_meta.is_stub=true），必须在报告中注明「待支柱二/三真实模型实现后复核」。
4. 不得给出投资建议，不得预测股价或上市结果。
5. 使用中文，语气专业、简洁，像发审委工作底稿摘要，不要空洞套话。

【报告结构】
## 一、Executive Summary（3-5 句话）
## 二、L1 表象预警：客户集中度
## 三、L2 订单获取正当性（若有）
## 四、跨支柱交叉验证（若有）
## 五、综合风险等级与核心结论
## 六、建议进一步核查事项（来自 cross_zone_signals，若有）
"""


@dataclass
class ExplanationResult:
    success: bool
    report_text: str
    model: str = DEFAULT_MODEL
    error_message: Optional[str] = None
    raw_verdict_summary: dict = field(default_factory=dict)


def _load_api_key() -> Optional[str]:
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()
    return None


def _try_load_dotenv() -> None:
    """若安装了 python-dotenv 且存在 .env，自动加载。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def _build_user_message(verdict: dict[str, Any]) -> str:
    return (
        "请根据以下 HawkEye 支柱一·独立性探针的结构化输出，撰写自然语言诊断报告。\n\n"
        f"```json\n{json.dumps(verdict, ensure_ascii=False, indent=2)}\n```"
    )


def generate_explanation(
    verdict: dict[str, Any],
    *,
    api_key: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
) -> ExplanationResult:
    """
    调用 DeepSeek 生成自然语言诊断报告。

    Args:
        verdict: run_pillar1() 输出的 verdict_to_dict() 结果
        api_key: 可选，默认从 DEEPSEEK_API_KEY 环境变量读取
    """
    _try_load_dotenv()
    key = api_key or _load_api_key()
    if not key:
        return ExplanationResult(
            success=False,
            report_text="",
            error_message=(
                "未找到 API Key。请设置环境变量 DEEPSEEK_API_KEY，"
                "或在项目根目录创建 .env 文件（参考 .env.example）。"
            ),
            raw_verdict_summary={
                "company": verdict.get("company_name"),
                "risk_level": verdict.get("final_risk_level"),
            },
        )

    try:
        from openai import OpenAI
    except ImportError:
        return ExplanationResult(
            success=False,
            report_text="",
            error_message="缺少 openai 库。请运行: pip install openai",
            raw_verdict_summary={
                "company": verdict.get("company_name"),
                "risk_level": verdict.get("final_risk_level"),
            },
        )

    client = OpenAI(api_key=key, base_url=base_url)
    user_message = _build_user_message(verdict)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=2000,
        )
        report = response.choices[0].message.content or ""
        return ExplanationResult(
            success=True,
            report_text=report.strip(),
            model=model,
            raw_verdict_summary={
                "company": verdict.get("company_name"),
                "risk_level": verdict.get("final_risk_level"),
                "risk_score": verdict.get("final_risk_score"),
            },
        )
    except Exception as exc:
        return ExplanationResult(
            success=False,
            report_text="",
            error_message=f"DeepSeek API 调用失败: {exc}",
            raw_verdict_summary={
                "company": verdict.get("company_name"),
                "risk_level": verdict.get("final_risk_level"),
            },
        )
