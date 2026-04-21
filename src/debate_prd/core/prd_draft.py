"""PRD 工作草稿 - 按章节组织 + 文件持久化"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib


@dataclass
class PRDItemExtended:
    """PRD 条目（扩展版）"""

    content: str
    source: str = ""
    status: str = "pending"
    category: str = ""
    round_num: int = 0
    confidence: str = "medium"


@dataclass
class PRDWorkingDraft:
    """PRD 工作草稿 - 按章节组织 + 文件持久化

    章节定义:
    - 目标用户
    - 核心功能
    - 技术约束
    - 成功指标
    - 风险点
    - 待定议题
    """

    topic: str
    sections: dict[str, list[PRDItemExtended]] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    DEFAULT_SECTIONS = [
        "目标用户",
        "核心功能",
        "技术约束",
        "成功指标",
        "风险点",
        "待定议题",
    ]

    def __post_init__(self):
        if not self.sections:
            self.sections = {s: [] for s in self.DEFAULT_SECTIONS}

    def add_item(
        self,
        section: str,
        content: str,
        source: str,
        round_num: int,
        confidence: str = "medium",
    ) -> PRDItemExtended:
        """添加条目到指定章节

        Args:
            section: 章节名称
            content: 条目内容
            source: 来源（consensus/pm/dev/moderator）
            round_num: 来源轮次
            confidence: 置信度（high/medium/low）

        Returns:
            新创建的 PRDItemExtended
        """
        if section not in self.sections:
            self.sections[section] = []

        item = PRDItemExtended(
            content=content,
            source=source,
            status="pending",
            category=section,
            round_num=round_num,
            confidence=confidence,
        )

        self.sections[section].append(item)
        self.last_updated = datetime.now()
        return item

    def get_summary(self) -> str:
        """生成摘要供深度分析 Prompt 使用

        Returns:
            章节摘要文本
        """
        lines = []
        for section, items in self.sections.items():
            if items:
                lines.append(f"### {section}")
                for item in items[-5:]:
                    status_mark = (
                        "✓"
                        if item.status == "confirmed"
                        else "?"
                        if item.status == "pending"
                        else "!"
                    )
                    confidence_mark = (
                        "[高]"
                        if item.confidence == "high"
                        else "[中]"
                        if item.confidence == "medium"
                        else "[低]"
                    )
                    lines.append(
                        f"  {status_mark} {confidence_mark} {item.content[:80]}"
                    )
        return "\n".join(lines) if lines else "暂无内容"

    def save_to_file(self, base_path: Path = None) -> Path:
        """持久化到 Markdown 文件

        路径格式: output/prd/{YYYY-MM-DD}/prd_draft_{topic_hash}_{timestamp}.md

        Args:
            base_path: 基础路径（默认为项目根目录下的 output/prd）

        Returns:
            保存的文件路径
        """
        if base_path is None:
            base_path = Path("output/prd")

        date_str = self.created_at.strftime("%Y-%m-%d")
        topic_hash = hashlib.md5(self.topic.encode()).hexdigest()[:8]
        timestamp = self.created_at.strftime("%H%M%S")

        dir_path = base_path / date_str
        dir_path.mkdir(parents=True, exist_ok=True)

        filename = f"prd_draft_{topic_hash}_{timestamp}.md"
        filepath = dir_path / filename

        content = self._render_markdown()
        filepath.write_text(content, encoding="utf-8")

        return filepath

    def _render_markdown(self) -> str:
        """渲染为 Markdown 格式"""
        lines = [
            f"# PRD 工作草稿: {self.topic}",
            f"",
            f"*创建时间: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}*",
            f"*最后更新: {self.last_updated.strftime('%Y-%m-%d %H:%M:%S')}*",
            f"",
        ]

        for section, items in self.sections.items():
            lines.append(f"## {section}")
            if items:
                for item in items:
                    status_mark = (
                        "✅"
                        if item.status == "confirmed"
                        else "⏳"
                        if item.status == "pending"
                        else "⚠️"
                    )
                    confidence_mark = (
                        "**高**"
                        if item.confidence == "high"
                        else "*中*"
                        if item.confidence == "medium"
                        else "_低_"
                    )
                    lines.append(
                        f"- {status_mark} [{confidence_mark}] (R{item.round_num}) {item.content}"
                    )
                    if item.source:
                        lines.append(f"  来源: {item.source}")
            else:
                lines.append("暂无")
            lines.append("")

        return "\n".join(lines)

    def load_from_file(self, filepath: Path) -> bool:
        """从文件恢复（断点续辩）

        Args:
            filepath: 文件路径

        Returns:
            是否成功加载
        """
        if not filepath.exists():
            return False

        try:
            content = filepath.read_text(encoding="utf-8")
            self._parse_markdown(content)
            return True
        except Exception as e:
            print(f"[PRDWorkingDraft] 加载失败: {e}")
            return False

    def _parse_markdown(self, content: str) -> None:
        """解析 Markdown 内容"""
        import re

        lines = content.split("\n")
        current_section = None

        for line in lines:
            if line.startswith("## "):
                current_section = line[3:].strip()
                if current_section not in self.sections:
                    self.sections[current_section] = []
            elif line.startswith("- ") and current_section:
                match = re.match(r"- (✅|⏳|⚠️) \[([^\]]+)\] \(R(\d+)\) (.+)", line)
                if match:
                    status = (
                        "confirmed"
                        if match.group(1) == "✅"
                        else "pending"
                        if match.group(1) == "⏳"
                        else "disputed"
                    )
                    confidence = (
                        "high"
                        if match.group(2) == "**高**"
                        else "medium"
                        if match.group(2) == "*中*"
                        else "low"
                    )
                    round_num = int(match.group(3))
                    item_content = match.group(4)

                    self.sections[current_section].append(
                        PRDItemExtended(
                            content=item_content,
                            status=status,
                            confidence=confidence,
                            round_num=round_num,
                            category=current_section,
                        )
                    )

    def to_dict(self) -> dict:
        """转换为字典格式（供 JSON 序列化）"""
        return {
            "topic": self.topic,
            "sections": {
                section: [
                    {
                        "content": item.content,
                        "source": item.source,
                        "status": item.status,
                        "category": item.category,
                        "round_num": item.round_num,
                        "confidence": item.confidence,
                    }
                    for item in items
                ]
                for section, items in self.sections.items()
            },
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }

    def get_all_items(self) -> list[PRDItemExtended]:
        """获取所有条目"""
        all_items = []
        for items in self.sections.values():
            all_items.extend(items)
        return all_items

    def get_items_by_confidence(
        self, min_confidence: str = "medium"
    ) -> list[PRDItemExtended]:
        """按置信度过滤条目

        Args:
            min_confidence: 最低置信度（high/medium/low）

        Returns:
            过滤后的条目列表
        """
        confidence_order = {"high": 3, "medium": 2, "low": 1}
        min_level = confidence_order.get(min_confidence, 2)

        return [
            item
            for item in self.get_all_items()
            if confidence_order.get(item.confidence, 2) >= min_level
        ]
