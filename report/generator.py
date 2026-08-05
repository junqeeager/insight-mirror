"""报告生成器"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from core.models import Profile
from core.utils import format_duration


class ReportGenerator:
    """报告生成器"""

    def __init__(self, templates_dir: str = "./report/templates"):
        self.templates_dir = Path(templates_dir)
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
        )
        # 注册自定义过滤器
        self.env.filters["format_duration"] = format_duration

    def generate_html(self, profile: Profile, output_dir: str = "./data/reports") -> str:
        """
        生成 HTML 报告

        Args:
            profile: 画像数据
            output_dir: 输出目录

        Returns:
            生成的文件路径
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        html_content = self.render_html(profile)

        # 写入文件
        filename = f"{profile.id}_{profile.period}.html"
        filepath = output_path / filename
        filepath.write_text(html_content, encoding="utf-8")

        return str(filepath)

    def render_html(self, profile: Profile) -> str:
        """渲染 HTML 报告内容（不落盘）。"""
        template_name = f"{profile.period}.html"
        if not (self.templates_dir / template_name).exists():
            template_name = "weekly.html"

        template = self.env.get_template(template_name)
        data = {
            "profile": profile,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "format_duration": format_duration,
        }
        return template.render(**data)

    def generate_summary(self, profile: Profile) -> str:
        """生成纯文本摘要"""
        lines = []
        lines.append(f"# 个人认知画像报告")
        lines.append(f"## {profile.period.upper()} 报告")
        lines.append(f"生成时间: {profile.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 概览
        lines.append("### 📊 概览")
        lines.append(f"- 总事件数: {profile.total_events}")
        lines.append(f"- 总投入时长: {format_duration(profile.total_duration)}")
        lines.append(f"- 活跃天数: {profile.active_days}")
        lines.append("")

        # Top 主题
        if profile.top_topics:
            lines.append("### 🏆 Top 兴趣领域")
            for i, topic in enumerate(profile.top_topics[:10], 1):
                lines.append(f"{i}. {topic.name} (权重: {topic.weight:.3f})")
            lines.append("")

        # 来源分布
        if profile.source_distribution:
            lines.append("### 📡 来源分布")
            for source, count in sorted(
                profile.source_distribution.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"- {source}: {count} 条")
            lines.append("")

        # 趋势
        if profile.emerging_topics:
            lines.append("### 📈 新兴兴趣")
            for topic in profile.emerging_topics:
                lines.append(f"- {topic}")
            lines.append("")

        if profile.declining_topics:
            lines.append("### 📉 衰退兴趣")
            for topic in profile.declining_topics:
                lines.append(f"- {topic}")
            lines.append("")

        # 洞察
        if profile.insights:
            lines.append("### 💡 个人洞察")
            for insight in profile.insights:
                lines.append(f"- {insight}")

        return "\n".join(lines)
