import pytest
from app.tools.visual_verifier import VisualVerifier, VisualInspectionReport


def test_visual_verifier_detects_unconstrained_images():
    html_with_unconstrained_img = """
    <html>
    <body>
        <img src="/static/giant_logo.png" />
    </body>
    </html>
    """
    report = VisualVerifier.inspect_html_layout(html_with_unconstrained_img)
    assert report.is_valid is False
    assert len(report.violations) == 1
    assert "CSS genişlik/yükseklik kısıtlaması" in report.violations[0]


def test_visual_verifier_passes_constrained_images():
    html_with_constrained_img = """
    <html>
    <head>
        <style>
            .brand-logo { width: 40px; height: 40px; max-width: 40px; }
        </style>
    </head>
    <body>
        <img src="/static/logo.png" class="brand-logo" />
        <img src="/static/icon.png" style="width: 20px; height: 20px;" />
        <img src="/static/banner.png" width="300" />
    </body>
    </html>
    """
    report = VisualVerifier.inspect_html_layout(html_with_constrained_img)
    assert report.is_valid is True
    assert len(report.violations) == 0
    assert report.image_count == 3
    assert report.constrained_image_count == 3


def test_visual_verifier_warns_on_large_fixed_widths():
    html_with_huge_width = """
    <div style="width: 3200px;">Huge Content</div>
    """
    report = VisualVerifier.inspect_html_layout(html_with_huge_width)
    assert report.is_valid is True
    assert len(report.warnings) == 1
    assert "Aşırı büyük sabit genişlik" in report.warnings[0]


def test_lab_ui_has_zero_visual_violations():
    from app.lab_ui import LAB_UI
    report = VisualVerifier.inspect_html_layout(LAB_UI)
    assert report.is_valid is True
    assert len(report.violations) == 0

