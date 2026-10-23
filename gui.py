"""ExoApp window (PySide6)."""

import json
import os
import sys

import exoapp_core as core
from i18n import LANGUAGES, Translator

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QColorDialog, QComboBox, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox,
    QPushButton, QRadioButton, QSizePolicy, QSpinBox, QStyle, QToolBar, QToolButton,
    QVBoxLayout, QWidget)

from preview import Preview

MODE_KEYS = ["static", "breathing", "spectrum-breathing", "rainbow", "spectrum-cycle",
             "multicolor", "wave", "tail", "rave", "epilepsy", "off"]
BRIGHTNESS = [(1, "level.low"), (2, "level.normal"), (4, "level.high")]
SPEED = [(1, "speed.slow"), (2, "speed.normal"), (3, "speed.fast")]
DIRECTION = [("down", "dir.down"), ("up", "dir.up")]
DEFAULT_PALETTE = ["ff0000", "ff8000", "ffff00", "00ff00", "00ffff", "0000ff", "ff00ff"]
DEFAULT_DPI = [(800, "ff0000"), (1600, "00ff00"), (2400, "0000ff"),
               (3200, "ffff00"), (4000, "00ffff"), (5000, "ff00ff")]
SETTINGS_FILE = os.path.join(core.CONFIG_DIR, "settings.json")
ASSETS = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.realpath(__file__))), "assets")


def color_count(mode):
    if mode == "breathing":
        return 1
    return core.COLOR_OFFSET.get(mode, (0, 0))[1]


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    os.makedirs(core.CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)



class ColorButton(QToolButton):
    changed = Signal()

    def __init__(self, hexc, tr):
        super().__init__()
        self.tr_ = tr
        self.setFixedSize(30, 22)
        self.set_hex(hexc)
        self.clicked.connect(self.pick)

    def set_hex(self, hexc):
        self.hex = hexc
        self.setStyleSheet(f"QToolButton {{ background: #{hexc}; border: 1px solid #555; "
                           f"border-radius: 4px; }}")

    def pick(self):
        c = QColorDialog.getColor(QColor("#" + self.hex), self, self.tr_("pick_color"))
        if c.isValid():
            self.set_hex(c.name()[1:])
            self.changed.emit()

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.tr_ = Translator(self.settings.get("language"))
        self.mouse = None
        self.applied = None
        self.loading = False
        self.setWindowTitle("ExoApp")
        self.resize(1180, 560)

        # Toolbar: refresh + language.
        bar = QToolBar(movable=False)
        self.addToolBar(bar)
        self.reload_act = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "", self)
        self.reload_act.triggered.connect(self.connect_mouse)
        bar.addAction(self.reload_act)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.lang_label = QLabel()
        bar.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        for code, name in LANGUAGES:
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex([c for c, _ in LANGUAGES].index(self.tr_.lang))
        self.lang_combo.currentIndexChanged.connect(self.on_language)
        bar.addWidget(self.lang_combo)

        central = QWidget()
        self.setCentralWidget(central)
        columns = QHBoxLayout(central)
        columns.setContentsMargins(16, 8, 16, 12)
        columns.setSpacing(20)
        left, middle, right = QVBoxLayout(), QVBoxLayout(), QVBoxLayout()
        for col in (left, middle, right):
            columns.addLayout(col, 1)

        # Left: preview, profiles, apply.
        self.preview = Preview()
        left.addWidget(self.preview)
        self.dirty_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.dirty_label.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        left.addWidget(self.dirty_label)
        self.profile_box = QGroupBox()
        pl = QVBoxLayout(self.profile_box)
        self.profile_combo = QComboBox()
        self.profile_combo.activated.connect(self.on_profile_selected)
        pl.addWidget(self.profile_combo)
        row = QHBoxLayout()
        self.save_btn = QPushButton(clicked=self.on_save)
        self.save_as_btn = QPushButton(clicked=self.on_save_as)
        self.delete_btn = QPushButton(clicked=self.on_delete)
        for b in (self.save_btn, self.save_as_btn, self.delete_btn):
            row.addWidget(b)
        pl.addLayout(row)
        left.addWidget(self.profile_box)
        self.apply_btn = QPushButton(clicked=self.on_apply)
        self.apply_btn.setMinimumHeight(36)
        self.apply_btn.setStyleSheet(
            "QPushButton { background: #3584e4; color: white; border-radius: 18px; "
            "font-weight: bold; padding: 0 24px; } QPushButton:hover { background: #4a90e9; }")
        left.addWidget(self.apply_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.status = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, wordWrap=True)
        self.status.setStyleSheet("color: palette(placeholder-text);")
        left.addWidget(self.status)
        left.addStretch()

        # Middle: lighting.
        self.light_box = QGroupBox()
        self.light_form = QFormLayout(self.light_box)
        self.mode_combo, self.bright_combo, self.speed_combo, self.dir_combo = (
            QComboBox() for _ in range(4))
        for key in MODE_KEYS:
            self.mode_combo.addItem("", key)
        for combo, items in ((self.bright_combo, BRIGHTNESS), (self.speed_combo, SPEED),
                             (self.dir_combo, DIRECTION)):
            for value, _ in items:
                combo.addItem("", value)
        self.form_labels = {}
        for key, combo in (("effect", self.mode_combo), ("brightness", self.bright_combo),
                           ("speed", self.speed_combo), ("direction", self.dir_combo)):
            self.form_labels[key] = QLabel()
            self.light_form.addRow(self.form_labels[key], combo)
            combo.currentIndexChanged.connect(self.on_changed)
        colors = QHBoxLayout()
        colors.setSpacing(4)
        self.color_buttons = []
        for hexc in DEFAULT_PALETTE:
            b = ColorButton(hexc, self.tr_)
            b.changed.connect(self.on_changed)
            self.color_buttons.append(b)
            colors.addWidget(b)
        colors.addStretch()
        self.form_labels["colors"] = QLabel()
        self.light_form.addRow(self.form_labels["colors"], colors)
        middle.addWidget(self.light_box)
        middle.addStretch()

        # Right: DPI stages.
        self.dpi_box = QGroupBox()
        dl = QVBoxLayout(self.dpi_box)
        self.dpi_help = QLabel(wordWrap=True)
        self.dpi_help.setStyleSheet("color: palette(placeholder-text);")
        dl.addWidget(self.dpi_help)
        count_row = QHBoxLayout()
        self.count_label = QLabel()
        self.stage_count = QSpinBox(minimum=1, maximum=core.DPI_STAGES, value=6)
        self.stage_count.valueChanged.connect(self.on_changed)
        count_row.addWidget(self.count_label)
        count_row.addStretch()
        count_row.addWidget(self.stage_count)
        dl.addLayout(count_row)
        grid = QGridLayout()
        grid.setVerticalSpacing(4)
        self.radio_group = QButtonGroup(self)
        self.stage_rows = []
        for i, (dpi, hexc) in enumerate(DEFAULT_DPI):
            radio = QRadioButton()
            self.radio_group.addButton(radio, i)
            radio.toggled.connect(self.on_changed)
            spin = QSpinBox(minimum=core.DPI_MIN, maximum=core.DPI_MAX,
                            singleStep=core.DPI_STEP, value=dpi, suffix=" DPI")
            spin.setMinimumWidth(110)
            spin.valueChanged.connect(self.on_changed)
            color = ColorButton(hexc, self.tr_)
            color.changed.connect(lambda c=color: self.on_dpi_color(c))
            grid.addWidget(radio, i, 0)
            grid.addWidget(spin, i, 1)
            grid.addWidget(color, i, 2)
            self.stage_rows.append((radio, spin, color))
        grid.setColumnStretch(0, 1)
        dl.addLayout(grid)
        right.addWidget(self.dpi_box)
        right.addStretch()

        self.poll = QTimer(self, interval=50, timeout=self.poll_events)
        self.retranslate()
        self.refresh_profiles()
        self.connect_mouse()

    # --- language ------------------------------------------------------

    def on_language(self, index):
        self.tr_.lang = self.lang_combo.itemData(index)
        self.settings["language"] = self.tr_.lang
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.retranslate()

    def retranslate(self):
        t = self.tr_
        self.reload_act.setText(t("reload"))
        self.reload_act.setToolTip(t("reload"))
        self.lang_label.setText(t("language") + "  ")
        self.profile_box.setTitle(t("profile"))
        self.save_btn.setText(t("save"))
        self.save_as_btn.setText(t("save_as"))
        self.delete_btn.setText(t("delete"))
        self.apply_btn.setText(t("apply"))
        self.light_box.setTitle(t("lighting"))
        for key, label in self.form_labels.items():
            label.setText(t(key))
        for i, key in enumerate(MODE_KEYS):
            self.mode_combo.setItemText(i, t("mode." + key))
        for combo, items in ((self.bright_combo, BRIGHTNESS), (self.speed_combo, SPEED),
                             (self.dir_combo, DIRECTION)):
            for i, (_, key) in enumerate(items):
                combo.setItemText(i, t(key))
        self.dpi_box.setTitle(t("dpi"))
        self.dpi_help.setText(t("dpi_help"))
        self.count_label.setText(t("stage_count"))
        for i, (radio, _spin, _color) in enumerate(self.stage_rows):
            radio.setText(t("stage", n=i + 1))
            radio.setToolTip(t("active_stage"))
        if self.profile_combo.count():
            self.profile_combo.setItemText(0, t("no_profile"))
        self.update_dirty()

    # --- state <-> widgets ---------------------------------------------

    def current_state(self):
        mode = self.mode_combo.currentData()
        light = {
            "mode": mode,
            "brightness": self.bright_combo.currentData(),
            "speed": self.speed_combo.currentData(),
            "direction": self.dir_combo.currentData(),
            "colors": [b.hex for b in self.color_buttons[:color_count(mode)]],
        }
        n = self.stage_count.value()
        stages = [{"dpi": spin.value(), "color": color.hex}
                  for _radio, spin, color in self.stage_rows[:n]]
        active = max(self.radio_group.checkedId(), 0)
        return {"lighting": light, "dpi": {"stages": stages, "active": min(active, n - 1)}}

    @staticmethod
    def select(combo, value, fallback_last=False):
        i = combo.findData(value)
        if i < 0 and fallback_last:
            i = combo.count() - 1
        if i >= 0:
            combo.setCurrentIndex(i)

    def load_state(self, st):
        self.loading = True
        light = st.get("lighting", {})
        self.select(self.mode_combo, light.get("mode"))
        self.select(self.bright_combo, light.get("brightness", 4), fallback_last=True)
        self.select(self.speed_combo, light.get("speed", 2))
        self.select(self.dir_combo, light.get("direction", "down"))
        for btn, hexc in zip(self.color_buttons, light.get("colors", [])):
            btn.set_hex(hexc)
        dpi = st.get("dpi")
        if dpi and dpi.get("stages"):
            self.stage_count.setValue(len(dpi["stages"]))
            for (_radio, spin, color), stage in zip(self.stage_rows, dpi["stages"]):
                spin.setValue(stage["dpi"])
                color.set_hex(stage["color"])
            self.stage_rows[min(dpi.get("active", 0), len(dpi["stages"]) - 1)][0].setChecked(True)
        self.loading = False
        self.on_changed()

    def on_changed(self, *_):
        if self.loading:
            return
        st = self.current_state()
        mode = st["lighting"]["mode"]
        level = core.ALIASES.get(mode, mode) in core.LEVEL_OFFSET
        self.light_form.setRowVisible(self.bright_combo, level)
        self.light_form.setRowVisible(self.speed_combo, level and mode != "static")
        self.light_form.setRowVisible(self.dir_combo, mode == "rainbow")
        n = color_count(mode)
        self.light_form.setRowVisible(self.form_labels["colors"], n > 0)
        for i, b in enumerate(self.color_buttons):
            b.setVisible(i < n)
        count = len(st["dpi"]["stages"])
        for i, (radio, spin, color) in enumerate(self.stage_rows):
            for w in (radio, spin, color):
                w.setVisible(i < count)
        if self.radio_group.checkedId() < 0 or self.radio_group.checkedId() >= count:
            self.stage_rows[0][0].setChecked(True)
        self.preview.set_lighting(st["lighting"])
        self.update_dirty()

    def update_dirty(self):
        if self.applied is None:
            self.dirty_label.setText("")
        elif self.current_state() == self.applied:
            self.dirty_label.setText(self.tr_("in_sync"))
        else:
            self.dirty_label.setText(self.tr_("preview_only"))

    def on_dpi_color(self, btn):
        self.preview.flash_dpi(btn.hex)
        self.on_changed()

    # --- mouse -----------------------------------------------------------

    def notify(self, text):
        self.statusBar().showMessage(text, 3000)

    def connect_mouse(self):
        self.poll.stop()
        try:
            if self.mouse:
                self.mouse.close()
            self.mouse = core.Mouse()
            self.status.setText(f"{self.mouse.path} · firmware {self.mouse.firmware() or '?'}")
            st = self.mouse.get_state()
            self.applied = None
            self.load_state(st)
            self.applied = self.current_state()
            self.update_dirty()
            self.poll.start()
        except (RuntimeError, OSError, ImportError) as e:
            self.mouse = None
            self.status.setText(self.tr_("not_found", e=e))

    def poll_events(self):
        try:
            events = self.mouse.dpi_events()
        except OSError:
            self.poll.stop()
            self.mouse = None
            self.status.setText(self.tr_("unplugged"))
            return
        for ev in events:
            if 0 <= ev["active"] < len(self.stage_rows):
                # Keep the stored "active stage" in step with the DPI button so
                # the next write does not jump back to the old stage.
                self.loading = True
                self.stage_rows[ev["active"]][0].setChecked(True)
                self.loading = False
                if self.applied:
                    self.applied["dpi"]["active"] = ev["active"]
                self.preview.flash_dpi(self.stage_rows[ev["active"]][2].hex)
                self.on_changed()
                self.notify(self.tr_("dpi_now", dpi=ev["dpi"]))

    def on_apply(self):
        if self.mouse is None:
            self.connect_mouse()
            if self.mouse is None:
                return
        st = self.current_state()
        try:
            self.mouse.apply(st)
            self.applied = st
            self.update_dirty()
            self.notify(self.tr_("applied"))
        except (RuntimeError, OSError, ValueError) as e:
            self.notify(self.tr_("error", e=e))
            if isinstance(e, OSError):
                # The mouse may have been unplugged; reconnect on next try.
                self.poll.stop()
                self.mouse = None

    # --- profiles --------------------------------------------------------

    def refresh_profiles(self, select=None):
        self.profile_combo.clear()
        self.profile_combo.addItem(self.tr_("no_profile"), None)
        for name in core.list_profiles():
            self.profile_combo.addItem(name, name)
        if select:
            self.select(self.profile_combo, select)

    def on_profile_selected(self, index):
        name = self.profile_combo.itemData(index)
        if not name:
            return
        try:
            self.load_state(core.load_profile(name))
            self.notify(self.tr_("loaded", name=name))
        except (OSError, ValueError, KeyError) as e:
            self.notify(self.tr_("load_failed", e=e))

    def on_save(self):
        name = self.profile_combo.currentData()
        if not name:
            self.on_save_as()
            return
        core.save_profile(name, self.current_state())
        self.notify(self.tr_("saved", name=name))

    def on_save_as(self):
        name, ok = QInputDialog.getText(self, self.tr_("save_title"), self.tr_("save_prompt"))
        name = name.strip()
        if not ok or not name:
            return
        try:
            core.save_profile(name, self.current_state())
        except (OSError, ValueError) as e:
            self.notify(self.tr_("error", e=e))
            return
        self.refresh_profiles(select=name)
        self.notify(self.tr_("saved", name=name))

    def on_delete(self):
        name = self.profile_combo.currentData()
        if not name:
            return
        answer = QMessageBox.question(self, "ExoApp", self.tr_("delete_title", name=name)
                                      + "\n" + self.tr_("delete_body"))
        if answer == QMessageBox.StandardButton.Yes:
            core.delete_profile(name)
            self.refresh_profiles()
            self.notify(self.tr_("deleted", name=name))

    def closeEvent(self, event):
        self.poll.stop()
        if self.mouse:
            self.mouse.close()
        super().closeEvent(event)


def run():
    # Keep the app and window at module level: as function locals Python may
    # destroy the QApplication before the window, which segfaults on exit.
    global app, win
    app = QApplication(sys.argv[:1])
    app.setApplicationName("ExoApp")
    app.setDesktopFileName("exoapp")
    icon = os.path.join(ASSETS, "exoapp.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    win = Window()
    win.show()
    return app.exec()
