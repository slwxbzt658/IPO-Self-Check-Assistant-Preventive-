"""
支柱二·维度 A:技术不可替代性与转换成本模型(Stub 版本)
========================================================

【MVP 状态】这是一个桩(Stub)实现。
真正的逻辑将在 04b 文档完成后实现。

为什么需要 Stub:
- 支柱一(独立性)需要"技术可替代性"的结论才能定性重大依赖
- 但支柱二的完整模型尚未开发
- 于是给一个返回固定值的桩,让支柱一的链路先跑通

接口契约严格遵循 04a 文档 §5.3.1。
"""

from typing import Any


def assess_tech_replaceability(prospectus_data: Any) -> dict:
    """
    评估发行人的技术不可替代性。

    Args:
        prospectus_data: 招股书结构化数据(MVP 阶段暂不使用)

    Returns:
        遵循 04a §5.3.1 schema 的字典。
    """
    return {
        "replaceability_level": "HIGH",
        "moat_depth": 25,
        "evidence": "[Stub] 核心技术仅为设备物理改造,缺乏自研工艺壁垒;"
                    "客户可通过采购同型号高端设备直接替代该公司的加工服务。",
        "verdict_for_pillar1": "恶性寄生",
        "_meta": {
            "is_stub": True,
            "implemented_in": "04b_pillar2_innovation 支柱二·创新性微创模型.md(待建)",
            "note": "MVP 阶段返回基于裕鸢案例事实的硬编码结论;"
                    "真实模型将通过研发费用率、专利质量、代工占比等多因子计算",
        },
    }
