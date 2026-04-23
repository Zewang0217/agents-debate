"""辩论消息分析

从 debate_loop.py 拆分，负责：
- 快速分析（正则提取标记）
- 偏题检测
- 幻觉引用检测
- 关键词提取

遵循规范：
- 函数不超过 50 行
- 使用 Guard Clause 减少嵌套
"""

import re
import jieba


def quick_analyze_round(pm_content: str, dev_content: str) -> dict:
    """快速分析 - 正则提取标记

    Args:
        pm_content: PM 本轮发言
        dev_content: Dev 本轮发言

    Returns:
        分析结果字典
    """
    result = {
        "new_agrees": [],
        "new_disagrees": [],
        "new_prd_items": [],
        "new_info": [],
        "new_constraints": [],
        "new_risks": [],
        "new_scenarios": [],
        "new_questions": [],
        "progress_detected": False,
    }

    patterns = {
        "agree": r"\[AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]",
        "disagree": r"\[DISAGREE:([^\n\]]*(?:\][^\n\]]*)*)\]",
        "prd": r"\[PRD_ITEM\] ([^\n]+)",
        "info": r"\[INFO\] ([^\n]+)",
        "constraint": r"\[CONSTRAINT\] ([^\n]+)",
        "risk": r"\[RISK\] ([^\n]+)",
        "scenario": r"\[SCENARIO\] ([^\n]+)",
        "question": r"\[QUESTION\] ([^\n]+)",
    }

    for content in [pm_content, dev_content]:
        _extract_by_patterns(content, patterns, result)

    _detect_progress(pm_content, dev_content, result)
    return result


def _extract_by_patterns(content: str, patterns: dict, result: dict):
    """按正则模式提取标记"""
    for key, pattern in patterns.items():
        matches = re.findall(pattern, content, re.DOTALL)
        target_key = (
            f"new_{key}s"
            if key in ["agree", "disagree"]
            else f"new_{key}s"
            if key != "prd"
            else "new_prd_items"
        )
        if key == "prd":
            target_key = "new_prd_items"
        elif key in ["agree", "disagree"]:
            target_key = f"new_{key}s"
        else:
            target_key = f"new_{key}s"

        for match in matches:
            item = match.strip() if isinstance(match, str) else match
            if item and item not in result.get(target_key, []):
                result[target_key].append(item)


def _detect_progress(pm_content: str, dev_content: str, result: dict):
    """检测是否有实质性推进"""
    progress_indicators = ["折中", "方案", "建议", "同意", "调整", "优化", "妥协"]
    for content in [pm_content, dev_content]:
        if any(indicator in content for indicator in progress_indicators):
            result["progress_detected"] = True
            break


def detect_off_topic(recent_msgs: list[str], topic: str, extract_keywords_func) -> dict:
    """偏题检测

    Args:
        recent_msgs: 最近的消息列表
        topic: 辩论议题
        extract_keywords_func: 关键词提取函数

    Returns:
        检测结果字典
    """
    result = {"is_off_topic": False, "hallucination": False, "guidance": ""}

    if len(recent_msgs) < 1:
        return result

    topic_keywords = set(extract_keywords_func(topic))

    for msg in recent_msgs:
        msg_keywords = set(extract_keywords_func(msg))
        overlap = len(topic_keywords & msg_keywords)

        if len(topic_keywords) > 0 and overlap < len(topic_keywords) * 0.3:
            result["is_off_topic"] = True
            return result

    for msg in recent_msgs:
        hallucinated = detect_hallucinated_reference(msg, topic, extract_keywords_func)
        if hallucinated:
            result["hallucination"] = True
            result["guidance"] = (
                f"[警告] 你引用的观点「{hallucinated[:50]}」与议题无关，请核实后重新发言"
            )
            return result

    return result


def detect_hallucinated_reference(
    msg: str, topic: str, extract_keywords_func
) -> str | None:
    """检测是否引用与议题无关的内容（幻觉检测）

    Args:
        msg: 发言内容
        topic: 辩论议题
        extract_keywords_func: 关键词提取函数

    Returns:
        如果检测到幻觉引用，返回引用内容；否则返回 None
    """
    patterns = [
        r"\[AGREE:\s*([^\]]+)\]",
        r"\[PARTIAL_AGREE:\s*([^\]]+)\]",
        r"对方.*指出[：:\s]*([^\n。]+)",
        r"对方.*说[：:\s]*([^\n。]+)",
        r"对方.*正确.*[：:\s]*([^\n。]+)",
    ]

    topic_keywords = set(extract_keywords_func(topic))
    unrelated_keywords = {
        "游戏",
        "H5",
        "小程序",
        "微信",
        "手机",
        "移动端",
        "APP",
        "应用",
    }

    for pattern in patterns:
        matches = re.findall(pattern, msg, re.DOTALL)
        for match in matches:
            referenced_content = match.strip()
            if len(referenced_content) < 5:
                continue

            ref_keywords = set(extract_keywords_func(referenced_content))
            overlap = len(ref_keywords & topic_keywords)

            topic_has_unrelated = any(kw in topic_keywords for kw in unrelated_keywords)
            ref_has_unrelated = any(kw in ref_keywords for kw in unrelated_keywords)

            if ref_has_unrelated and not topic_has_unrelated:
                return referenced_content

            if len(ref_keywords) > 0 and overlap == 0 and len(ref_keywords) >= 3:
                return referenced_content

    return None


def extract_keywords(text: str) -> list[str]:
    """提取关键词"""
    words = jieba.cut(text)
    stopwords = ["的", "是", "有", "在", "和", "对", "为", "这"]
    keywords = [w for w in words if len(w) > 1 and w not in stopwords]
    return keywords[:20]


def detect_critical_decision(
    recent_messages: list[str], asked_decisions: set
) -> dict | None:
    """检测关键决策点

    Args:
        recent_messages: 最近的消息列表
        asked_decisions: 已询问过的决策类别

    Returns:
        如果检测到关键决策点，返回决策信息；否则返回 None
    """
    CRITICAL_KEYWORDS = {
        "技术栈": ["技术栈", "框架", "React", "Vue", "Angular", "Next.js", "Nuxt"],
        "预算": ["预算", "成本", "费用", "投入", "资金"],
        "时间": ["时间", "周期", "上线", "交付", "deadline", "截止"],
        "团队": ["团队", "人力", "人员", "开发人员", "工程师"],
        "架构": ["架构", "微服务", "单体", "分布式", "单体应用"],
    }

    if len(recent_messages) < 2:
        return None

    recent_text = " ".join(recent_messages[-3:])

    for category, keywords in CRITICAL_KEYWORDS.items():
        if category in asked_decisions:
            continue

        for kw in keywords:
            if kw.lower() in recent_text.lower():
                asked_decisions.add(category)
                return {
                    "category": category,
                    "keyword": kw,
                    "question": f"关于【{category}】，您的倾向或约束是什么？",
                }

    return None


def get_decision_options(category: str) -> list[str]:
    """获取关键决策的默认选项"""
    OPTIONS = {
        "技术栈": ["React", "Vue", "其他框架", "无特定要求"],
        "预算": ["低成本优先", "平衡成本与质量", "质量优先"],
        "时间": ["1-3个月", "3-6个月", "6个月以上"],
        "团队": ["1-3人", "3-5人", "5人以上"],
        "架构": ["单体架构", "微服务", "混合架构"],
    }
    return OPTIONS.get(category, [])


__all__ = [
    "quick_analyze_round",
    "detect_off_topic",
    "detect_hallucinated_reference",
    "extract_keywords",
    "detect_critical_decision",
    "get_decision_options",
]
