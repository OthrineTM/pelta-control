"""ROG-style theme: dark panels with cut corners, slanted shapes, accent color, ROG font.

The ROG font and headset artwork belong to ASUS and are not shipped with this project.
install.sh copies them from a local ROG PELTA (Armoury Crate) package into assets/ when
present; without them the theme falls back to system fonts and a generic headset icon.
"""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QFrame, QSizePolicy, QWidget

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

ROG_RED = QColor("#ff0a3c")
BG = QColor("#08080b")
PANEL = QColor("#121217")
PANEL_HI = QColor("#1b1b22")
LINE = QColor("#2a2a33")
TEXT = QColor("#e8e8ee")
MUTED = QColor("#7c7c8a")
GREEN = QColor("#22e07a")
AMBER = QColor("#ffb020")


class Theme:
    accent = QColor(ROG_RED)
    display_family = None  # ROG font family if available
    listeners = []

    @classmethod
    def load_fonts(cls):
        for f in sorted(ASSETS.glob("*.ttf")):
            fid = QFontDatabase.addApplicationFont(str(f))
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            if fams:
                cls.display_family = fams[0]

    @classmethod
    def display(cls, size, bold=False):
        f = QFont(cls.display_family or "Noto Sans", size)
        if not cls.display_family:
            f.setWeight(QFont.Black)
            f.setItalic(True)
        f.setBold(bold or not cls.display_family)
        f.setLetterSpacing(QFont.PercentageSpacing, 104)
        return f

    @classmethod
    def set_accent(cls, color):
        cls.accent = QColor(color)
        for fn in list(cls.listeners):
            try:
                fn()
            except RuntimeError:  # widget already deleted
                cls.listeners.remove(fn)

    @classmethod
    def stylesheet(cls):
        a = cls.accent.name()
        return f"""
        QWidget {{ color: {TEXT.name()}; }}
        #Root {{ background: {BG.name()}; }}
        QLabel#Caption {{ color: {MUTED.name()}; font-size: 8pt; letter-spacing: 2px; }}
        QLabel#Value {{ color: {a}; font-weight: bold; }}
        QComboBox {{
            background: {PANEL_HI.name()}; border: 1px solid {LINE.name()}; border-left: 3px solid {a};
            padding: 5px 10px; min-width: 150px;
        }}
        QComboBox:hover {{ border-color: {a}; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox QAbstractItemView {{
            background: {PANEL.name()}; border: 1px solid {a}; selection-background-color: {a};
            outline: none; padding: 2px;
        }}
        QSlider::groove:horizontal {{ height: 4px; background: {LINE.name()}; }}
        QSlider::sub-page:horizontal {{ background: {a}; }}
        QSlider::handle:horizontal {{
            background: {a}; width: 8px; margin: -8px 0; border: 1px solid {BG.name()};
        }}
        QSlider::handle:horizontal:hover {{ background: white; }}
        QSlider:disabled {{ opacity: 0.4; }}
        QSlider::sub-page:horizontal:disabled {{ background: {LINE.name()}; }}
        QSlider::handle:horizontal:disabled {{ background: {MUTED.name()}; }}
        QToolTip {{ background: {PANEL.name()}; color: {TEXT.name()}; border: 1px solid {a}; }}
        QMenu {{ background: {PANEL.name()}; border: 1px solid {LINE.name()}; }}
        QMenu::item:selected {{ background: {a}; }}
        QMessageBox, QColorDialog {{ background: {PANEL.name()}; }}
        QPushButton {{ background: {PANEL_HI.name()}; border: 1px solid {LINE.name()}; padding: 6px 14px; }}
        QPushButton:hover {{ border-color: {a}; }}
        """


def cut_path(rect, cut=12, cut_tl=True, cut_br=True):
    """Rectangle with the top-left and bottom-right corners clipped diagonally."""
    r = QRectF(rect)
    p = QPainterPath()
    p.moveTo(r.left() + (cut if cut_tl else 0), r.top())
    p.lineTo(r.right(), r.top())
    p.lineTo(r.right(), r.bottom() - (cut if cut_br else 0))
    p.lineTo(r.right() - (cut if cut_br else 0), r.bottom())
    p.lineTo(r.left(), r.bottom())
    p.lineTo(r.left(), r.top() + (cut if cut_tl else 0))
    p.closeSubpath()
    return p


def slant_poly(rect, skew):
    r = QRectF(rect)
    return QPolygonF([QPointF(r.left() + skew, r.top()), QPointF(r.right(), r.top()),
                      QPointF(r.right() - skew, r.bottom()), QPointF(r.left(), r.bottom())])


class Accented:
    """Mixin: repaint when the accent color changes."""

    def _hook_accent(self):
        Theme.listeners.append(self.update)


class CutPanel(QFrame, Accented):
    """Card with clipped corners, thin border, accent tick and an uppercase title."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.title = title.upper()
        self._hook_accent()
        top = 34 if title else 14
        self.setContentsMargins(16, top, 16, 14)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = cut_path(r, 14)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, PANEL_HI)
        g.setColorAt(1, PANEL)
        p.fillPath(path, g)
        p.setPen(QPen(LINE, 1))
        p.drawPath(path)
        a = Theme.accent
        p.setPen(QPen(a, 2))
        p.drawLine(QPointF(r.left() + 14, r.top() + 1), QPointF(r.left() + 70, r.top() + 1))
        p.drawLine(QPointF(r.right() - 1, r.bottom() - 34), QPointF(r.right() - 1, r.bottom() - 16))
        if self.title:
            p.setPen(TEXT)
            p.setFont(Theme.display(9))
            p.drawText(QRectF(r.left() + 16, r.top() + 8, r.width() - 32, 20),
                       Qt.AlignLeft | Qt.AlignVCenter, self.title)
            p.setPen(QPen(a, 1))
            fm = p.fontMetrics()
            x = r.left() + 22 + fm.horizontalAdvance(self.title)
            for i in range(3):
                p.drawLine(QPointF(x + i * 6, r.top() + 23), QPointF(x + 4 + i * 6, r.top() + 13))


class SlantButton(QAbstractButton, Accented):
    """Checkable parallelogram button used for tabs and effect tiles."""

    def __init__(self, text, parent=None, height=34, font_size=9):
        super().__init__(parent)
        self.setText(text.upper())
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._h = height
        self._fs = font_size
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hook_accent()

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self.text()) + 48, self._h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        poly = slant_poly(r, 10)
        a = Theme.accent
        if self.isChecked():
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, a)
            g.setColorAt(1, a.darker(160))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
        else:
            p.setBrush(PANEL_HI if self.underMouse() else PANEL)
            p.setPen(QPen(a if self.underMouse() else LINE, 1))
        p.drawPolygon(poly)
        p.setPen(Qt.white if self.isChecked() else (TEXT if self.isEnabled() else MUTED))
        p.setFont(Theme.display(self._fs))
        p.drawText(r, Qt.AlignCenter, self.text())

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class Toggle(QAbstractButton, Accented):
    """Slanted on/off switch with a label."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._hook_accent()

    def sizeHint(self):
        return QSize(60 + self.fontMetrics().horizontalAdvance(self.text()) + 12, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 5, 50, 16)
        on = self.isChecked()
        a = Theme.accent if self.isEnabled() else MUTED
        p.setPen(QPen(a if on else LINE, 1))
        p.setBrush(a.darker(260) if on else PANEL_HI)
        p.drawPolygon(slant_poly(track, 6))
        knob = QRectF(track.right() - 24 if on else track.left() + 2, track.top() + 2, 22, track.height() - 4)
        p.setPen(Qt.NoPen)
        p.setBrush(a if on else MUTED)
        p.drawPolygon(slant_poly(knob, 5))
        p.setPen(TEXT if self.isEnabled() else MUTED)
        p.drawText(QRectF(62, 0, self.width() - 62, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Swatch(QAbstractButton):
    """Diamond color chip."""

    def __init__(self, color, size=22, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self.color.name())

    def set_color(self, c):
        self.color = QColor(c)
        self.setToolTip(self.color.name())
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        poly = QPolygonF([QPointF(w / 2, 1), QPointF(w - 1, w / 2), QPointF(w / 2, w - 1), QPointF(1, w / 2)])
        p.setBrush(self.color)
        p.setPen(QPen(Qt.white if self.underMouse() else LINE, 1.5))
        p.drawPolygon(poly)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()


class Battery(QWidget, Accented):
    """Segmented slanted battery gauge with a large percentage readout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.percent = None
        self.charging = False
        self.setMinimumSize(250, 44)
        self._hook_accent()

    def set_state(self, percent, charging):
        self.percent, self.charging = percent, charging
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pct = self.percent
        low = pct is not None and pct <= 15 and not self.charging
        color = GREEN if self.charging else (AMBER if low else Theme.accent)
        p.setFont(Theme.display(20))
        txt = "--" if pct is None else f"{pct}"
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance("100")
        p.setPen(color if pct is not None else MUTED)
        p.drawText(QRectF(0, 0, tw, self.height() - 10), Qt.AlignRight | Qt.AlignVCenter, txt)
        p.setFont(Theme.display(9))
        p.drawText(QRectF(tw + 4, 4, 24, self.height() - 14), Qt.AlignLeft | Qt.AlignVCenter, "%")
        x0, segs, gap = tw + 34, 10, 4
        sw = (self.width() - x0 - 4 - gap * (segs - 1)) / segs
        filled = 0 if pct is None else math.ceil(pct / 10)
        for i in range(segs):
            r = QRectF(x0 + i * (sw + gap), 10, sw, self.height() - 26)
            p.setPen(Qt.NoPen)
            p.setBrush(color if i < filled else PANEL_HI)
            p.drawPolygon(slant_poly(r, 5))
        p.setFont(QFont(self.font().family(), 7))
        p.setPen(MUTED)
        label = "CHARGING" if self.charging else ("BATTERY LOW" if low else "BATTERY")
        p.drawText(QRectF(x0, self.height() - 14, self.width() - x0, 14), Qt.AlignLeft | Qt.AlignVCenter, label)


class HeadsetArt(QWidget, Accented):
    """Headset line art with an animated glow showing the current lighting effect."""

    def __init__(self, fallback_svg, parent=None):
        super().__init__(parent)
        art = next(iter(sorted(ASSETS.glob("A501*.svg"))), None)
        self.has_asus_art = art is not None
        data = Path(art or fallback_svg).read_bytes()
        if art:
            data = data.replace(b"#999999", b"#b8b8c4").replace(b"#666666", b"#6c6c78")
        self.renderer = QSvgRenderer(data)
        self.effect, self.color, self.brightness, self.connected = 1, QColor("#8000ff"), 100, False
        self.t = 0.0
        self.timer = QTimer(self, interval=40, timeout=self._tick)
        self.setMinimumSize(220, 300)
        self._hook_accent()

    def set_lighting(self, effect, color, brightness, connected=True):
        self.effect, self.color, self.brightness, self.connected = effect, QColor(color), brightness, connected
        animated = connected and brightness > 0 and effect in (2, 3, 4)
        self.timer.start() if animated else self.timer.stop()
        self.update()

    def _tick(self):
        self.t += 0.04
        self.update()

    def glow_color(self):
        if not self.connected or self.brightness == 0:
            return None
        c = QColor(self.color)
        level = self.brightness / 100
        if self.effect == 2:  # breathing
            level *= 0.25 + 0.75 * (0.5 + 0.5 * math.sin(self.t * 2.2))
        elif self.effect == 3:  # strobing
            level *= 1.0 if (self.t * 4) % 1 < 0.5 else 0.08
        elif self.effect == 4:  # color cycle
            c = QColor.fromHsvF((self.t * 0.12) % 1, 1, 1)
        c.setAlphaF(max(0.0, min(1.0, 0.85 * level)))
        return c

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        size = self.renderer.defaultSize()
        scale = min(r.width() / size.width(), r.height() / size.height()) * 0.9
        w, h = size.width() * scale, size.height() * scale
        target = QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)

        # diagonal backdrop lines
        p.setPen(QPen(QColor(255, 255, 255, 10), 1))
        for x in range(-int(r.height()), int(r.width()), 14):
            p.drawLine(QPointF(x, r.bottom()), QPointF(x + r.height(), r.top()))

        c = self.glow_color()
        if c:
            # LED zones sit on the ear cups (far cup partly hidden, near cup front right)
            for fx, fy, fr in ((0.30, 0.60, 0.30), (0.74, 0.72, 0.36)):
                center, rad = QPointF(target.left() + w * fx, target.top() + h * fy), w * fr
                g = QRadialGradient(center, rad)
                g.setColorAt(0, c)
                g.setColorAt(0.45, QColor(c.red(), c.green(), c.blue(), int(c.alpha() * 0.45)))
                g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))
                p.setBrush(QBrush(g))
                p.setPen(Qt.NoPen)
                p.drawEllipse(center, rad, rad)
        if not self.connected:
            p.setOpacity(0.35)
        self.renderer.render(p, target)
