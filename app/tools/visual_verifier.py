"""Prometheus Visual & Layout Verification Tool.

Inspects HTML/CSS documents for image dimension constraints, layout overflows,
unhandled fixed pixel widths, and missing static assets to prevent UI breakage.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisualInspectionReport:
    is_valid: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    image_count: int = 0
    constrained_image_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "violations": self.violations,
            "warnings": self.warnings,
            "image_count": self.image_count,
            "constrained_image_count": self.constrained_image_count,
        }


class VisualVerifier:
    """Automated visual and layout integrity inspector for Prometheus."""

    @staticmethod
    def inspect_html_layout(
        html_content: str,
        workspace_root: str | None = None,
    ) -> VisualInspectionReport:
        report = VisualInspectionReport(is_valid=True)
        if not html_content or not html_content.strip():
            report.warnings.append("Boş HTML içeriği kontrol edildi.")
            return report

        # 1. Find all <img> tags
        img_pattern = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
        img_matches = img_pattern.findall(html_content)
        report.image_count = len(img_matches)

        for idx, attrs in enumerate(img_matches, 1):
            src_match = re.search(r'src=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            style_match = re.search(r'style=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            class_match = re.search(r'class=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            width_attr = re.search(r'\bwidth=["\']?(\d+)[px%]?["\']?', attrs, re.IGNORECASE)

            src = src_match.group(1) if src_match else f"image_{idx}"
            style = style_match.group(1) if style_match else ""
            cls_name = class_match.group(1) if class_match else ""

            # Check if dimensions are constrained via inline style, width attribute, or CSS class
            has_style_constraint = any(
                k in style for k in ["width:", "max-width:", "height:", "max-height:"]
            )
            has_width_attr = bool(width_attr)
            
            # Check if CSS class has matching rule in HTML <style> block
            has_class_constraint = False
            if cls_name:
                for single_cls in cls_name.split():
                    cls_rule = f".{single_cls}"
                    if cls_rule in html_content:
                        # Check if class definition includes dimension constraints
                        rule_block_match = re.search(
                            re.escape(cls_rule) + r"\s*\{([^}]*)\}",
                            html_content,
                            re.DOTALL,
                        )
                        if rule_block_match:
                            rule_content = rule_block_match.group(1)
                            if any(
                                k in rule_content
                                for k in ["width:", "max-width:", "height:", "max-height:"]
                            ):
                                has_class_constraint = True
                                break

            if has_style_constraint or has_width_attr or has_class_constraint:
                report.constrained_image_count += 1
            else:
                report.is_valid = False
                report.violations.append(
                    f"Görsel '{src}' için CSS genişlik/yükseklik kısıtlaması (max-width / width) bulunamadı! Görsel ekranda devasa boyutta taşabilir."
                )

            # 2. Check static file existence if workspace_root is provided
            if workspace_root and src.startswith("/static/"):
                relative_static_path = src.lstrip("/")
                full_path = os.path.join(workspace_root, relative_static_path)
                app_static_path = os.path.join(workspace_root, "app", relative_static_path)
                if not os.path.exists(full_path) and not os.path.exists(app_static_path):
                    report.warnings.append(
                        f"Statik görsel dosyası bulunamadı: '{src}'"
                    )

        # 3. Check for absurdly large fixed container widths
        large_fixed_width = re.findall(r'width:\s*(\d{4,})px', html_content, re.IGNORECASE)
        for w in large_fixed_width:
            if int(w) > 2400:
                report.warnings.append(
                    f"Aşırı büyük sabit genişlik tespit edildi ({w}px). Ekran taşması yapabilir."
                )

        return report
