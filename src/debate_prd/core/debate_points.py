"""共识/分歧点管理

从 debate_loop.py 拆分，负责：
- 共识点提取和格式化
- 分歧点查找和更新
- PRD 条目分类和格式化

遵循规范：
- 函数不超过 50 行
- 使用 Guard Clause 减少嵌套
"""

from typing import Optional
from .debate_state import DebateState, ConsensusPoint, DisagreementPoint


def update_state_from_analysis(state: DebateState, analysis: dict, round_num: int):
    """根据 LLM 分析结果更新 DebateState"""
    _update_locked_consensus(state, analysis, round_num)
    _update_pending_consensus(state, analysis, round_num)
    _update_disagreements(state, analysis, round_num)

    updates = analysis.get("prd_supplement_updates", [])
    if updates:
        state.prd_supplement = "\n".join(updates)

    _sync_legacy_fields(state)


def _update_locked_consensus(state: DebateState, analysis: dict, round_num: int):
    """更新锁定共识"""
    for item in analysis.get("locked_consensus", []):
        point = ConsensusPoint(
            content=item.get("content", ""),
            category=item.get("category", ""),
            locked=True,
            evidence=item.get("evidence", []),
            round_created=round_num,
        )
        if point.content and point not in state.locked_consensus:
            state.locked_consensus.append(point)


def _update_pending_consensus(state: DebateState, analysis: dict, round_num: int):
    """更新待定共识"""
    for item in analysis.get("pending_consensus", []):
        point = ConsensusPoint(
            content=item.get("content", ""),
            category=item.get("category", ""),
            locked=False,
            evidence=item.get("evidence", []),
            round_created=round_num,
        )
        if point.content and point not in state.pending_consensus:
            state.pending_consensus.append(point)


def _update_disagreements(state: DebateState, analysis: dict, round_num: int):
    """更新分歧点"""
    for item in analysis.get("active_disagreements", []):
        disagreement = DisagreementPoint(
            topic=item.get("topic", ""),
            pm_position=item.get("pm_position", ""),
            dev_position=item.get("dev_position", ""),
            priority=item.get("priority", "normal"),
            category=item.get("category", ""),
            round_created=round_num,
            attempts=0,
        )
        if not disagreement.topic:
            continue

        existing = find_disagreement(state, disagreement.topic)
        if existing:
            existing.pm_position = disagreement.pm_position
            existing.dev_position = disagreement.dev_position
        else:
            state.active_disagreements.append(disagreement)


def _sync_legacy_fields(state: DebateState):
    """同步旧字段（兼容过渡期）"""
    for point in state.locked_consensus:
        if point.content not in state.agree_points:
            state.agree_points.append(point.content)
    for point in state.pending_consensus:
        if point.content not in state.partial_agree_points:
            state.partial_agree_points.append(point.content)


def find_disagreement(state: DebateState, topic: str) -> Optional[DisagreementPoint]:
    """查找已存在的分歧点"""
    for d in state.active_disagreements:
        if d.topic == topic or topic in d.topic or d.topic in topic:
            return d
    return None


def format_disagreements(state: DebateState) -> str:
    """格式化分歧点列表"""
    if not state.active_disagreements:
        return "暂无明确分歧点"

    lines = []
    for i, d in enumerate(state.active_disagreements, 1):
        if d.resolved:
            continue
        priority_mark = _get_priority_mark(d.priority)
        lines.append(f"{i}. {priority_mark} {d.topic}")
        if d.pm_position:
            lines.append(f"   PM立场: {d.pm_position[:80]}")
        if d.dev_position:
            lines.append(f"   Dev立场: {d.dev_position[:80]}")
        lines.append(f"   讨论次数: {d.attempts}")

    return "\n".join(lines) if lines else "暂无明确分歧点"


def _get_priority_mark(priority: str) -> str:
    """获取优先级标记"""
    if priority == "high":
        return "[高优先]"
    elif priority == "normal":
        return "[中优先]"
    return "[低优先]"


def format_consensus(points: list[str]) -> str:
    """格式化共识点"""
    if not points:
        return "暂无"
    return "\n".join(f"✅ {p[:100]}" for p in points[:6])


def format_disagreement(points: list[str]) -> str:
    """格式化分歧点"""
    if not points:
        return "暂无"
    return "\n".join(f"❌ {p[:100]}" for p in points[:6])


def categorize_prd_items(items: list[str]) -> str:
    """分类PRD条目"""
    if not items:
        return "暂无"

    product_keywords = ["用户", "目标", "功能", "体验", "需求", "价值", "MVP", "验证"]
    tech_keywords = ["技术", "性能", "加载", "架构", "实现", "兼容", "优化", "指标"]
    ops_keywords = ["运营", "推广", "数据", "留存", "增长", "商业化", "营收"]

    product_items = []
    tech_items = []
    ops_items = []
    other_items = []

    for item in items:
        item_lower = item.lower()
        if any(kw in item_lower for kw in product_keywords):
            product_items.append(item)
        elif any(kw in item_lower for kw in tech_keywords):
            tech_items.append(item)
        elif any(kw in item_lower for kw in ops_keywords):
            ops_items.append(item)
        else:
            other_items.append(item)

    return _format_categorized_items(product_items, tech_items, ops_items, other_items)


def _format_categorized_items(product, tech, ops, other) -> str:
    """格式化分类后的条目"""
    lines = []
    if product:
        lines.append("**产品相关:**")
        for item in product[:5]:
            lines.append(f"  - {item}")
    if tech:
        lines.append("**技术相关:**")
        for item in tech[:5]:
            lines.append(f"  - {item}")
    if ops:
        lines.append("**运营相关:**")
        for item in ops[:5]:
            lines.append(f"  - {item}")
    if other:
        lines.append("**其他:**")
        for item in other[:3]:
            lines.append(f"  - {item}")
    return "\n".join(lines) if lines else "暂无"


def apply_deep_analysis_result(
    state: DebateState, result: dict, prd_draft, round_num: int
):
    """应用深度分析结果到状态"""
    _resolve_disagreements(state, result)
    _update_disagreement_status(state, result)
    _add_locked_consensus(state, result, round_num)
    _update_prd_supplement(state, result, prd_draft, round_num)


def _resolve_disagreements(state: DebateState, result: dict):
    """处理已解决的分歧"""
    for item in result.get("resolved_disagreements", []):
        topic = item.get("topic", "")
        disagreement = find_disagreement(state, topic)
        if not disagreement:
            continue
        disagreement.resolved = True
        disagreement.resolution = item.get("resolution", "")
        if item.get("becomes_consensus"):
            state.locked_consensus.append(
                ConsensusPoint(
                    content=disagreement.resolution,
                    category=disagreement.category,
                    locked=True,
                    round_created=state.round_num,
                )
            )


def _update_disagreement_status(state: DebateState, result: dict):
    """更新分歧状态"""
    for item in result.get("updated_disagreements", []):
        topic = item.get("topic", "")
        disagreement = find_disagreement(state, topic)
        if disagreement:
            if item.get("pm_position"):
                disagreement.pm_position = item.get("pm_position")
            if item.get("dev_position"):
                disagreement.dev_position = item.get("dev_position")
            disagreement.attempts = item.get("attempts", disagreement.attempts)


def _add_locked_consensus(state: DebateState, result: dict, round_num: int):
    """添加新的锁定共识"""
    for content in result.get("new_locked_consensus", []):
        if content:
            point = ConsensusPoint(
                content=content, locked=True, round_created=round_num
            )
            if point not in state.locked_consensus:
                state.locked_consensus.append(point)


def _update_prd_supplement(state: DebateState, result: dict, prd_draft, round_num: int):
    """更新 PRD 补充版"""
    for update in result.get("prd_updates", []):
        if not update:
            continue
        if isinstance(update, dict):
            _add_prd_draft_item(prd_draft, update, round_num)
            content = update.get("content", "")
        else:
            content = str(update)

        if state.prd_supplement:
            state.prd_supplement += f"\n{content}"
        else:
            state.prd_supplement = content


def _add_prd_draft_item(prd_draft, update: dict, round_num: int):
    """添加 PRD 草稿条目"""
    if not prd_draft:
        return
    prd_draft.add_item(
        section=update.get("section", "核心功能"),
        content=update.get("content", ""),
        source=update.get("source", "moderator"),
        round_num=round_num,
        confidence=update.get("confidence", "medium"),
    )


__all__ = [
    "update_state_from_analysis",
    "find_disagreement",
    "format_disagreements",
    "format_consensus",
    "format_disagreement",
    "categorize_prd_items",
    "apply_deep_analysis_result",
]
