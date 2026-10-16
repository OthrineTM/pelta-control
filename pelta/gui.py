"""ROG-styled control panel and tray icon for the ROG Pelta."""

import os
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSettings, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QLabel,
    QMenu, QMessageBox, QSlider, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import device, eq_presets
from .device import Pelta, PeltaError
from .rog import (
    BG, LINE, MUTED, PANEL, PANEL_HI, ROG_RED, TEXT, Battery, CutPanel, HeadsetArt, SlantButton, Swatch, Theme, Toggle,
)

APP_NAME = "Pelta Control"
ICON_PATH = Path(__file__).resolve().parent.parent / "icons/pelta-control.svg"
SWATCHES = ["#ff0a3c", "#8000ff", "#b57edc", "#c71585", "#ff00ff", "#4b0082", "#00c8ff", "#22e07a",
            "#ffb020", "#ffffff"]
POLL_MS = 30_000
LOW_BATTERY_ALERT = 15


def battery_icon(percent, charging, connected):
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QIcon(str(ICON_PATH)).paint(p, 0, 0, 64, 64)
    if connected and percent is not None:
        color = QColor("#22e07a") if charging else QColor("#ffb020") if percent <= LOW_BATTERY_ALERT else Theme.accent
        p.setBrush(QColor(0, 0, 0, 210))
        p.setPen(Qt.NoPen)
        p.drawRect(2, 34, 60, 28)
        p.setPen(color)
        p.setFont(Theme.display(17))
        p.drawText(pm.rect().adjusted(0, 34, 0, -2), Qt.AlignCenter, f"{percent}")
    p.end()
    return QIcon(pm)


def caption(text):
    lbl = QLabel(text.upper())
    lbl.setObjectName("Caption")
    return lbl


class Stripe(QWidget):
    """Thin accent line under the header with a slanted end, like Armoury Crate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        Theme.listeners.append(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        p.setPen(QPen(LINE, 1))
        p.drawLine(0, 4, w, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(Theme.accent)
        p.drawPolygon(QPolygonF([QPointF(0, 2), QPointF(220, 2), QPointF(214, 7), QPointF(0, 7)]))
        for i in range(4):
            x = 232 + i * 10
            p.drawPolygon(QPolygonF([QPointF(x, 2), QPointF(x + 6, 2), QPointF(x, 7), QPointF(x - 6, 7)]))


class TileGroup(QWidget):
    """Row/grid of exclusive slanted tiles mapping to values."""

    changed = Signal(object)

    def __init__(self, options, columns=None, height=34, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.group = QButtonGroup(self)
        self.buttons = {}
        columns = columns or len(options)
        for i, (label, value) in enumerate(options):
            b = SlantButton(label, height=height, font_size=8)
            self.group.addButton(b)
            self.buttons[value] = b
            grid.addWidget(b, i // columns, i % columns)
            b.clicked.connect(lambda _=False, v=value: self.changed.emit(v))

    def value(self):
        for v, b in self.buttons.items():
            if b.isChecked():
                return v
        return None

    def set_value(self, value):
        b = self.buttons.get(value)
        if b:
            b.setChecked(True)


class LabeledSlider(QWidget):
    def __init__(self, maximum, fmt=str, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal, minimum=0, maximum=maximum)
        self.value_lbl = QLabel()
        self.value_lbl.setObjectName("Value")
        self.value_lbl.setFont(Theme.display(11))
        self.value_lbl.setMinimumWidth(56)
        self.value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.fmt = fmt
        self.slider.valueChanged.connect(lambda v: self.value_lbl.setText(self.fmt(v)))
        row.addWidget(self.slider)
        row.addWidget(self.value_lbl)

    def setValue(self, v):
        self.slider.setValue(v)
        self.value_lbl.setText(self.fmt(v))


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.settings = QSettings("pelta-control", "pelta-control")
        self.dev = None
        self.state = device.Status()
        self.loading = False
        self.alerted_low = False
        self.light_color = QColor("#8000ff")

        self.build_ui()
        self.build_tray()
        self.resize(940, 600)

        self.lighting_timer = QTimer(self, singleShot=True, interval=150, timeout=self.apply_lighting)
        self.sidetone_timer = QTimer(self, singleShot=True, interval=150, timeout=self.apply_sidetone_level)
        self.poll_timer = QTimer(self, interval=POLL_MS, timeout=self.refresh)
        self.poll_timer.start()
        QTimer.singleShot(0, self.refresh)

    # --- layout ----------------------------------------------------------

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel()
        self.title.setFont(Theme.display(24))
        titles.addWidget(self.title)
        titles.addWidget(caption("Wireless gaming headset  //  Linux control"))
        head.addLayout(titles)
        head.addStretch()
        conn_box = QVBoxLayout()
        conn_box.setSpacing(2)
        conn_box.addWidget(caption("Status"), alignment=Qt.AlignRight)
        self.conn = QLabel("SEARCHING")
        self.conn.setFont(Theme.display(10))
        conn_box.addWidget(self.conn, alignment=Qt.AlignRight)
        head.addLayout(conn_box)
        head.addSpacing(26)
        self.battery = Battery()
        self.battery.setFixedWidth(290)
        head.addWidget(self.battery)
        root.addLayout(head)
        root.addWidget(Stripe())

        body = QHBoxLayout()
        body.setSpacing(18)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        self.art = HeadsetArt(ICON_PATH)
        left.addWidget(self.art, 1)
        self.info = QLabel()
        self.info.setObjectName("Caption")
        self.info.setAlignment(Qt.AlignCenter)
        left.addWidget(self.info)
        body.addLayout(left, 4)

        right = QVBoxLayout()
        right.setSpacing(12)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_group = QButtonGroup(self)
        self.pages = QStackedWidget()
        for i, (name, page) in enumerate([("Lighting", self.page_lighting()), ("Audio", self.page_audio()),
                                          ("System", self.page_system()), ("Power", self.page_power())]):
            b = SlantButton(name, height=36, font_size=10)
            self.tab_group.addButton(b, i)
            tabs.addWidget(b)
            self.pages.addWidget(page)
        self.tab_group.idClicked.connect(self.pages.setCurrentIndex)
        self.tab_group.button(0).setChecked(True)
        right.addLayout(tabs)
        right.addWidget(self.pages, 1)
        body.addLayout(right, 6)

        self.update_title()
        Theme.listeners.append(self.update_title)

    def page(self, *panels):
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        for p in panels:
            col.addWidget(p)
        col.addStretch()
        return w

    def page_lighting(self):
        effect = CutPanel("Effect")
        lay = QVBoxLayout(effect)
        self.effect = TileGroup([(n, k) for k, n in device.EFFECTS.items()] + [("Off", 0)], columns=3)
        self.effect.changed.connect(self.on_effect)
        lay.addWidget(self.effect)

        color = CutPanel("Color")
        lay = QHBoxLayout(color)
        self.color_big = Swatch(self.light_color, size=44)
        self.color_big.setToolTip("Pick a custom color")
        self.color_big.clicked.connect(self.pick_color)
        lay.addWidget(self.color_big)
        lay.addSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, c in enumerate(SWATCHES):
            s = Swatch(c, size=24)
            s.clicked.connect(lambda _=False, c=c: self.set_color(QColor(c)))
            grid.addWidget(s, i // 5, i % 5)
        lay.addLayout(grid)
        lay.addStretch()
        custom = SlantButton("Custom", height=30, font_size=8)
        custom.setCheckable(False)
        custom.setFixedWidth(110)
        custom.clicked.connect(self.pick_color)
        lay.addWidget(custom)

        bright = CutPanel("Brightness")
        lay = QVBoxLayout(bright)
        self.brightness = LabeledSlider(20, lambda v: f"{v * 5}<span style='font-family:sans-serif;font-size:9pt'> %</span>")
        self.brightness.slider.setPageStep(2)
        self.brightness.slider.valueChanged.connect(self.queue_lighting)
        lay.addWidget(self.brightness)
        return self.page(effect, color, bright)

    def page_audio(self):
        mic = CutPanel("Microphone")
        lay = QVBoxLayout(mic)
        self.nr = Toggle("AI noise reduction")
        self.nr.toggled.connect(lambda v: self.send(lambda d: d.set_noise_reduction(v)))
        lay.addWidget(self.nr)

        st = CutPanel("Sidetone")
        lay = QVBoxLayout(st)
        self.sidetone = Toggle("Hear your own voice")
        self.sidetone.toggled.connect(self.on_sidetone)
        lay.addWidget(self.sidetone)
        self.sidetone_level = LabeledSlider(device.SIDETONE_MAX)
        self.sidetone_level.slider.valueChanged.connect(lambda _: self.loading or self.sidetone_timer.start())
        lay.addWidget(self.sidetone_level)
        lay.addWidget(caption("Active only while the microphone is in use"))

        eq = CutPanel("Equalizer")
        lay = QHBoxLayout(eq)
        txt = QLabel("The ROG EQ is a software effect. Add the official presets\n"
                     "(FPS, Racing, Rock, Vocal…) to EasyEffects.")
        txt.setStyleSheet(f"color:{MUTED.name()}")
        lay.addWidget(txt, 1)
        btn = SlantButton("Export presets", height=32, font_size=8)
        btn.setCheckable(False)
        btn.setFixedWidth(170)
        btn.clicked.connect(self.export_eq)
        lay.addWidget(btn)
        return self.page(mic, st, eq)

    def page_system(self):
        conn = CutPanel("Connection priority")
        lay = QVBoxLayout(conn)
        self.latency = TileGroup([(n, v) for v, n in device.LATENCY.items()])
        self.latency.changed.connect(lambda v: self.send(lambda d: d.set_latency(v)))
        lay.addWidget(self.latency)
        lay.addWidget(caption("2.4 GHz mode only"))

        voice = CutPanel("Voice prompts")
        lay = QVBoxLayout(voice)
        self.voice = TileGroup([(n, v) for v, n in device.VOICE_PROMPT.items()])
        self.voice.changed.connect(lambda v: self.send(lambda d: d.set_voice_prompt(v)))
        lay.addWidget(self.voice)

        theme = CutPanel("App theme")
        lay = QVBoxLayout(theme)
        self.accent_mode = TileGroup([("ROG red", "rog"), ("Match headset color", "headset")])
        self.accent_mode.set_value(self.settings.value("accent", "rog"))
        self.accent_mode.changed.connect(self.on_accent_mode)
        lay.addWidget(self.accent_mode)
        return self.page(conn, voice, theme)

    def page_power(self):
        sleep = CutPanel("Auto sleep")
        lay = QVBoxLayout(sleep)
        self.sleep = TileGroup([(f"{m} min" if m else "Never", m) for m in device.SLEEP_MINUTES], columns=6)
        self.sleep.changed.connect(self.apply_power)
        lay.addWidget(self.sleep)

        low = CutPanel("Low battery warning")
        lay = QVBoxLayout(low)
        lay.addWidget(caption("Lights blink below"))
        self.low_level = TileGroup([(f"{v}%" if v else "Off", v) for v in device.LOW_BATTERY_LEVELS], columns=6)
        self.low_level.changed.connect(self.apply_power)
        lay.addWidget(self.low_level)
        lay.addSpacing(6)
        self.low_voice = Toggle("Voice prompt on low battery")
        self.low_voice.toggled.connect(self.apply_power)
        lay.addWidget(self.low_voice)
        return self.page(sleep, low)

    def update_title(self):
        self.title.setText(f"<span style='color:{Theme.accent.name()}'>ROG</span> PELTA")

    # --- tray ------------------------------------------------------------

    def build_tray(self):
        self.tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), self)
        menu = QMenu()
        menu.addAction(QAction("Show", self, triggered=self.show_window))
        menu.addAction(QAction("Refresh", self, triggered=self.refresh))
        menu.addSeparator()
        menu.addAction(QAction("Quit", self, triggered=QApplication.quit))
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.toggle_window() if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_window(self):
        self.hide() if self.isVisible() else self.show_window()

    def closeEvent(self, event):
        if self.tray.isVisible():
            event.ignore()
            self.hide()

    # --- device ----------------------------------------------------------

    def ensure_device(self):
        if self.dev is None:
            self.dev = Pelta()
        return self.dev

    def drop_device(self):
        if self.dev:
            self.dev.close()
        self.dev = None

    def show_error(self, e):
        self.conn.setText(f"<span style='color:#ffb020'>{str(e).upper()}</span>")

    def send(self, fn):
        if self.loading:
            return
        try:
            fn(self.ensure_device())
        except PeltaError as e:
            self.drop_device()
            self.show_error(e)

    def refresh(self):
        try:
            s = self.ensure_device().status()
        except PeltaError as e:
            self.drop_device()
            s = device.Status()
            self.show_error(e)
        else:
            self.conn.setText("CONNECTED" if s.connected else
                              f"<span style='color:{MUTED.name()}'>HEADSET OFF</span>")
        self.state = s
        self.load_state(s)

    def load_state(self, s):
        self.loading = True
        self.pages.setEnabled(s.connected)
        self.battery.set_state(s.battery if s.connected else None, s.charging)
        if s.connected:
            self.effect.set_value(0 if s.brightness == 0 else s.effect)
            self.brightness.setValue((s.brightness or 50) // 5)
            if any(s.color):
                self.light_color = QColor(*s.color)
                self.color_big.set_color(self.light_color)
            self.nr.setChecked(s.noise_reduction)
            self.sidetone.setChecked(s.sidetone)
            self.sidetone_level.setValue(s.sidetone_level)
            self.sidetone_level.setEnabled(s.sidetone)
            self.latency.set_value(s.latency)
            self.voice.set_value(s.voice_prompt)
            self.sleep.set_value(s.sleep_minutes)
            self.low_level.set_value(s.low_battery_level)
            self.low_voice.setChecked(s.low_battery_voice)
            mode = device.PRODUCT_IDS.get(self.dev.product_id, "") if self.dev else ""
            self.info.setText(f"{mode.upper()}   //   FIRMWARE {' / '.join(s.firmware)}")
        else:
            self.info.setText("")
        self.loading = False
        self.update_art()
        self.update_accent()
        self.update_tray(s)

    def update_tray(self, s):
        self.tray.setIcon(battery_icon(s.battery, s.charging, s.connected))
        tip = "ROG Pelta: headset off" if not s.connected else \
            f"ROG Pelta: {s.battery}%" + (" (charging)" if s.charging else "")
        self.tray.setToolTip(tip)
        if s.connected and s.battery is not None and not s.charging:
            if s.battery <= LOW_BATTERY_ALERT and not self.alerted_low:
                self.tray.showMessage("ROG Pelta", f"Battery low: {s.battery}%", QSystemTrayIcon.Warning)
                self.alerted_low = True
            elif s.battery > LOW_BATTERY_ALERT + 5:
                self.alerted_low = False

    def update_art(self):
        effect = self.effect.value()
        bright = 0 if effect == 0 else self.brightness.slider.value() * 5
        self.art.set_lighting(effect or 1, self.light_color, bright, self.state.connected)

    def update_accent(self):
        if self.settings.value("accent", "rog") == "headset" and self.effect.value() not in (0, 4):
            color = self.light_color
        else:
            color = ROG_RED
        if color != Theme.accent:
            Theme.set_accent(color)
            QApplication.instance().setStyleSheet(Theme.stylesheet())
            self.update_tray(self.state)

    # --- actions ---------------------------------------------------------

    def on_effect(self, value):
        self.brightness.setEnabled(value != 0)
        self.queue_lighting()

    def queue_lighting(self, *_):
        if not self.loading:
            self.update_art()
            self.update_accent()
            self.lighting_timer.start()

    def apply_lighting(self):
        effect = self.effect.value()
        c = self.light_color
        rgb = (c.red(), c.green(), c.blue())
        if effect == 0:
            self.send(lambda d: d.set_lighting(self.state.effect or 1, 0, rgb))
        else:
            self.state.effect = effect
            self.send(lambda d: d.set_lighting(effect, self.brightness.slider.value() * 5, rgb))

    def set_color(self, color):
        self.light_color = QColor(color)
        self.color_big.set_color(color)
        if self.effect.value() in (0, 4, None):  # color cycle / off ignore the color
            self.effect.set_value(1)
            self.brightness.setEnabled(True)
        self.queue_lighting()

    def pick_color(self):
        c = QColorDialog.getColor(self.light_color, self, "Headset color")
        if c.isValid():
            self.set_color(c)

    def on_sidetone(self, on):
        self.sidetone_level.setEnabled(on)
        self.send(lambda d: d.set_sidetone(on))

    def apply_sidetone_level(self):
        self.send(lambda d: d.set_sidetone_level(self.sidetone_level.slider.value()))

    def apply_power(self, *_):
        self.send(lambda d: d.set_power(self.sleep.value(), self.low_level.value(), self.low_voice.isChecked()))

    def on_accent_mode(self, mode):
        self.settings.setValue("accent", mode)
        self.update_accent()

    def export_eq(self):
        try:
            paths = eq_presets.export()
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not write presets: {e}")
            return
        QMessageBox.information(
            self, APP_NAME,
            f"Added {len(paths)} presets to EasyEffects (Output → Presets → \"ROG Pelta - …\").\n\n"
            f"{paths[0].parent}")


INSTANCE_NAME = f"pelta-control-{os.getuid()}"


def signal_running_instance(show):
    """Return True if another instance is running (and ask it to show its window)."""
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"show" if show else b"noop")
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def listen_for_instances(win):
    QLocalServer.removeServer(INSTANCE_NAME)  # stale socket after a crash
    server = QLocalServer(win)
    server.listen(INSTANCE_NAME)

    def on_connection():
        conn = server.nextPendingConnection()
        conn.waitForReadyRead(300)
        if conn.readAll().data() == b"show":
            win.show_window()
        conn.disconnectFromServer()

    server.newConnection.connect(on_connection)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    if signal_running_instance(show="--tray" not in argv):
        return 0
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("pelta-control")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in ((QPalette.Window, BG), (QPalette.Base, PANEL), (QPalette.AlternateBase, PANEL_HI),
                        (QPalette.Button, PANEL_HI), (QPalette.Text, TEXT), (QPalette.WindowText, TEXT),
                        (QPalette.ButtonText, TEXT), (QPalette.Highlight, Theme.accent)):
        pal.setColor(role, color)
    app.setPalette(pal)
    Theme.load_fonts()
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(Theme.stylesheet())
    win = Window()
    listen_for_instances(win)
    if "--tray" not in argv:
        win.show()
    return app.exec()
