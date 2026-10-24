"""Temas claro/escuro do RecoverMap (PySide6)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

_DARK = {
    QPalette.ColorRole.Window: "#14151c",
    QPalette.ColorRole.WindowText: "#e8e8f0",
    QPalette.ColorRole.Base: "#1b1d27",
    QPalette.ColorRole.AlternateBase: "#212331",
    QPalette.ColorRole.Text: "#e8e8f0",
    QPalette.ColorRole.Button: "#232535",
    QPalette.ColorRole.ButtonText: "#e8e8f0",
    QPalette.ColorRole.Highlight: "#4f46e5",
    QPalette.ColorRole.HighlightedText: "#ffffff",
    QPalette.ColorRole.ToolTipBase: "#1b1d27",
    QPalette.ColorRole.ToolTipText: "#e8e8f0",
    QPalette.ColorRole.PlaceholderText: "#7c7f96",
}

_LIGHT = {
    QPalette.ColorRole.Window: "#f6f6f8",
    QPalette.ColorRole.WindowText: "#1c1c22",
    QPalette.ColorRole.Base: "#ffffff",
    QPalette.ColorRole.AlternateBase: "#eef0f4",
    QPalette.ColorRole.Text: "#1c1c22",
    QPalette.ColorRole.Button: "#e8e8ee",
    QPalette.ColorRole.ButtonText: "#1c1c22",
    QPalette.ColorRole.Highlight: "#4f46e5",
    QPalette.ColorRole.HighlightedText: "#ffffff",
    QPalette.ColorRole.ToolTipBase: "#ffffff",
    QPalette.ColorRole.ToolTipText: "#1c1c22",
    QPalette.ColorRole.PlaceholderText: "#8a8d9c",
}


def apply_theme(app, dark: bool) -> None:
    """Aplica Fusion + paleta clara ou escura em toda a aplicacao."""
    from PySide6.QtWidgets import QStyleFactory
    src = _DARK if dark else _LIGHT
    app.setStyle(QStyleFactory.create("Fusion"))
    pal = QPalette()
    for role, color in src.items():
        pal.setColor(role, QColor(color))
        pal.setColor(QPalette.ColorGroup.Disabled, role,
                     QColor(color).darker(130) if dark else QColor(color).lighter(108))
    app.setPalette(pal)
