import sys
import os
import json
import shutil
import math
import ctypes
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QDialog, QFrame,
    QLineEdit, QDialogButtonBox, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import (
    QIcon, QDragEnterEvent, QDropEvent, QColor, QPixmap,
    QPainter, QFont, QPen, QBrush, QPalette,
)

SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"
ZONE_W = 150
ZONE_H = 100
BG = "#F3F9FE"


# ---- 設定の読み書き --------------------------------------------------------

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        folders = data.get("folders", [])
        if folders and isinstance(folders[0], str):
            folders = [{"path": p, "name": "", "use_date_folder": True,
                        "allow_filemove": True, "click_count": 0, "move_count": 0}
                       for p in folders]
            data["folders"] = folders
        else:
            for entry in folders:
                entry.setdefault("use_date_folder", True)
                entry.setdefault("allow_filemove", True)
                entry.setdefault("click_count", 0)
                entry.setdefault("move_count", 0)
        return data
    return {"folders": []}


def save_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ---- ファイル移動ロジック --------------------------------------------------

def today_folder_name() -> str:
    return datetime.now().strftime("%y%m%d")


def move_file(src: str, dest_folder: str, use_date_folder: bool) -> str:
    target_dir = Path(dest_folder) / today_folder_name() if use_date_folder else Path(dest_folder)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / Path(src).name
    if dest_path.exists():
        stem = Path(src).stem
        suffix = Path(src).suffix
        n = 1
        while dest_path.exists():
            dest_path = target_dir / f"{stem}_{n}{suffix}"
            n += 1
    shutil.move(src, dest_path)
    return str(dest_path)


# ---- アイコン生成 ----------------------------------------------------------

def _make_icon(size: int, draw_fn) -> QIcon:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(p, size)
    p.end()
    return QIcon(px)


def make_app_icon() -> QIcon:
    def draw(p: QPainter, s: int):
        p.setBrush(QColor("#0078D4"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(2, 2, s - 4, s - 4, 6, 6)
        p.setPen(QColor("white"))
        p.setFont(QFont("", int(s * 0.4), QFont.Weight.Bold))
        p.drawText(0, 0, s, s, Qt.AlignmentFlag.AlignCenter, "D")
    return _make_icon(32, draw)


def make_settings_icon(size: int = 28) -> QIcon:
    def draw(p: QPainter, s: int):
        cx, cy, r_out, r_in = s / 2, s / 2, s * 0.42, s * 0.18
        teeth = 8
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        pts = []
        for i in range(teeth * 2):
            angle = math.radians(i * 360 / (teeth * 2))
            r = r_out if i % 2 == 0 else r_out * 0.72
            pts.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))
        p.setBrush(QColor("#5A5A5A"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(cx, cy), r_in, r_in)
    return _make_icon(size, draw)


def make_tray_icon_btn(size: int = 28) -> QIcon:
    def draw(p: QPainter, s: int):
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5A5A5A"))
        m = s * 0.22
        p.drawRect(int(m), int(s * 0.22), int(s - m * 2), int(s * 0.14))
        cx, tip_y = s / 2, s * 0.82
        aw, ah = s * 0.38, s * 0.30
        p.drawPolygon(QPolygonF([
            QPointF(cx - aw, tip_y - ah),
            QPointF(cx + aw, tip_y - ah),
            QPointF(cx, tip_y),
        ]))
    return _make_icon(size, draw)


def make_drop_pixmap(size: int = 28, color: str = "#ccc") -> QPixmap:
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtCore import QPointF
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    cx = size / 2
    p.setPen(QPen(c, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(int(cx), int(size * 0.08), int(cx), int(size * 0.58))
    aw, ab = size * 0.28, size * 0.58
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(QPolygonF([
        QPointF(cx - aw, ab - size * 0.22),
        QPointF(cx + aw, ab - size * 0.22),
        QPointF(cx, ab),
    ]))
    m = size * 0.14
    p.setPen(QPen(c, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(int(m), int(size * 0.82), int(size - m), int(size * 0.82))
    p.end()
    return px


def icon_button(icon: QIcon, tooltip: str, size: int = 36) -> QPushButton:
    btn = QPushButton()
    btn.setIcon(icon)
    btn.setIconSize(QSize(size - 8, size - 8))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setStyleSheet("""
        QPushButton {
            border: 1px solid #E5E5E5;
            border-radius: 6px;
            background: #FFFFFF;
        }
        QPushButton:hover  { background: #EFF6FF; border-color: #0078D4; }
        QPushButton:pressed { background: #DCEEFB; }
    """)
    return btn


# ---- タイルスタイル --------------------------------------------------------

_TILE_BASE = """
    QFrame {{
        border: 1px solid {border};
        border-radius: 8px;
        background: {bg};
    }}
"""
TILE_IDLE  = _TILE_BASE.format(border="#D8E8F5", bg="#FDFEFF")
TILE_HOVER = _TILE_BASE.format(border="#0078D4", bg="#EFF6FF")


# ---- フォルダタイル（クリック＋D&D統合）-----------------------------------

class FolderTile(QFrame):
    files_dropped = pyqtSignal(list)
    folder_opened = pyqtSignal()

    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self._allow_filemove = folder_entry.get("allow_filemove", True)
        self.setFixedSize(ZONE_W, ZONE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(TILE_IDLE)
        if self._allow_filemove:
            self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._name = QLabel()
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(True)
        self._name.setStyleSheet(
            "color: #1A1A1A; font-size: 12px; font-weight: bold;"
            " border: none; background: transparent;"
        )

        layout.addStretch()
        layout.addWidget(self._name)
        if self._allow_filemove:
            drop_icon = QLabel()
            drop_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            drop_icon.setStyleSheet("border: none; background: transparent;")
            drop_icon.setPixmap(make_drop_pixmap(22, "#B0B0B0"))
            layout.addWidget(drop_icon)
        layout.addStretch()

        name = folder_entry.get("name", "").strip()
        path = folder_entry.get("path", "")
        self._name.setText(name if name else Path(path).name)

    def enterEvent(self, event):
        self.setStyleSheet(TILE_HOVER)

    def leaveEvent(self, event):
        self.setStyleSheet(TILE_IDLE)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(TILE_HOVER)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(TILE_IDLE)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(TILE_IDLE)
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path = self.folder_entry.get("path", "")
            if path and os.path.isdir(path):
                self.folder_opened.emit()
                os.startfile(path)


# ---- フォルダ追加・編集ダイアログ ------------------------------------------

class FolderEditDialog(QDialog):
    def __init__(self, entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フォルダの追加" if entry is None else "フォルダの編集")
        self.setMinimumWidth(440)
        self.result_entry: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("フォルダ:"))
        path_row = QHBoxLayout()
        self._path = QLineEdit()
        self._path.setPlaceholderText("フォルダのパス")
        if entry:
            self._path.setText(entry.get("path", ""))
        browse = QPushButton("参照...")
        browse.setFixedWidth(64)
        browse.clicked.connect(self._browse)
        path_row.addWidget(self._path)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        layout.addWidget(QLabel("表示名（任意）:"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("省略するとフォルダ名で表示されます")
        if entry:
            self._name.setText(entry.get("name", ""))
        layout.addWidget(self._name)

        self._date_check = QCheckBox("日付フォルダを生成する（例: 260709）")
        self._date_check.setChecked(entry.get("use_date_folder", True) if entry else True)
        layout.addWidget(self._date_check)

        self._filemove_check = QCheckBox("ファイル移動を有効にする（D&D でファイルを移動できます）")
        self._filemove_check.setChecked(entry.get("allow_filemove", True) if entry else True)
        layout.addWidget(self._filemove_check)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder:
            self._path.setText(folder)

    def _accept(self):
        path = self._path.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "エラー", "有効なフォルダパスを指定してください。")
            return
        self.result_entry = {
            "path": path,
            "name": self._name.text().strip(),
            "use_date_folder": self._date_check.isChecked(),
            "allow_filemove": self._filemove_check.isChecked(),
        }
        self.accept()


# ---- 登録フォルダ管理ダイアログ --------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フォルダ登録設定")
        self.setMinimumSize(560, 360)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("登録フォルダ一覧"))

        self._list = QListWidget()
        self._refresh_list()
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        for label, slot in [("追加", self._add), ("編集", self._edit), ("削除", self._remove)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _refresh_list(self):
        self._list.clear()
        for entry in self.settings["folders"]:
            name = entry.get("name", "").strip()
            path = entry.get("path", "")
            fm = "移動可" if entry.get("allow_filemove", True) else "移動不可"
            clicks = entry.get("click_count", 0)
            moves = entry.get("move_count", 0)
            label = name if name else Path(path).name
            self._list.addItem(
                f"[{fm}] {label}  —  {path}  （クリック:{clicks} 移動:{moves}）"
            )

    def _add(self):
        dlg = FolderEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            entry = dlg.result_entry
            entry["click_count"] = 0
            entry["move_count"] = 0
            self.settings["folders"].append(entry)
            save_settings(self.settings)
            self._refresh_list()

    def _edit(self):
        row = self._list.currentRow()
        if row < 0:
            return
        existing = self.settings["folders"][row]
        dlg = FolderEditDialog(entry=existing, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            result = dlg.result_entry
            result["click_count"] = existing.get("click_count", 0)
            result["move_count"] = existing.get("move_count", 0)
            self.settings["folders"][row] = result
            save_settings(self.settings)
            self._refresh_list()

    def _remove(self):
        row = self._list.currentRow()
        if row < 0:
            return
        entry = self.settings["folders"][row]
        name = entry.get("name") or entry.get("path", "")
        if QMessageBox.question(self, "削除確認", f"「{name}」を削除しますか？") \
                == QMessageBox.StandardButton.Yes:
            self.settings["folders"].pop(row)
            save_settings(self.settings)
            self._refresh_list()


# ---- タイルグリッド（幅に応じて折り返し）-----------------------------------

class TileGrid(QWidget):
    _GAP = 10
    _MARGIN = 12

    def __init__(self, tiles: list, empty_text: str = ""):
        super().__init__()
        self.setAutoFillBackground(True)
        _pal = self.palette()
        _pal.setColor(QPalette.ColorRole.Window, QColor(BG))
        self.setPalette(_pal)
        self._tiles = tiles
        for t in tiles:
            t.setParent(self)
        if not tiles:
            self._ph = QLabel(empty_text)
            self._ph.setParent(self)
            self._ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ph.setStyleSheet("color: #9E9E9E; font-size: 12px;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        if not self._tiles:
            if hasattr(self, '_ph'):
                self._ph.setGeometry(0, 0, w, 80)
            return
        avail = max(w - self._MARGIN * 2, ZONE_W)
        cols = max(1, (avail + self._GAP) // (ZONE_W + self._GAP))
        for i, tile in enumerate(self._tiles):
            r, c = divmod(i, cols)
            tile.move(
                self._MARGIN + c * (ZONE_W + self._GAP),
                self._MARGIN + r * (ZONE_H + self._GAP),
            )
            tile.show()


# ---- メインウィンドウ -------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, tray: QSystemTrayIcon):
        super().__init__()
        self.tray = tray
        self.settings = load_settings()
        self.setWindowTitle("DateFiler")
        w = self.settings.get("window_width", 500)
        h = self.settings.get("window_height", 300)
        self.resize(w, h)
        self._grid: TileGrid | None = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        central.setAutoFillBackground(True)
        _pal = central.palette()
        _pal.setColor(QPalette.ColorRole.Window, QColor(BG))
        central.setPalette(_pal)
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(8, 8, 8, 8)
        self._root.setSpacing(6)

        top = QHBoxLayout()
        top.addStretch()
        self._settings_btn = icon_button(make_settings_icon(28), "フォルダ登録", 32)
        self._settings_btn.clicked.connect(self._open_settings)
        self._tray_btn = icon_button(make_tray_icon_btn(28), "トレイに格納", 32)
        self._tray_btn.clicked.connect(self._hide_to_tray)
        top.addWidget(self._settings_btn)
        top.addWidget(self._tray_btn)
        self._root.addLayout(top)

        self._rebuild_tiles()

    def _sorted_folders(self) -> list:
        return sorted(
            self.settings["folders"],
            key=lambda e: e.get("click_count", 0) + e.get("move_count", 0),
            reverse=True,
        )

    def _rebuild_tiles(self):
        if self._grid is not None:
            self._root.removeWidget(self._grid)
            self._grid.setParent(None)

        folders = self._sorted_folders()
        tiles = []
        for entry in folders:
            tile = FolderTile(entry)
            tile.folder_opened.connect(lambda e=entry: self._on_click(e))
            tile.files_dropped.connect(lambda paths, e=entry: self._on_drop(paths, e))
            tiles.append(tile)

        self._grid = TileGrid(tiles, "右上の歯車ボタンからフォルダを追加してください")
        self._root.addWidget(self._grid, 1)

    def _on_click(self, entry: dict):
        entry["click_count"] = entry.get("click_count", 0) + 1
        save_settings(self.settings)

    def _on_drop(self, paths: list, entry: dict):
        use_date = entry.get("use_date_folder", True)
        target = entry["path"]
        errors, moved = [], 0
        for p in paths:
            if not os.path.isfile(p):
                errors.append(f"{Path(p).name} はファイルではありません")
                continue
            try:
                move_file(p, target, use_date)
                moved += 1
            except Exception as e:
                errors.append(f"{Path(p).name}: {e}")

        if moved:
            entry["move_count"] = entry.get("move_count", 0) + moved
            save_settings(self.settings)

        label = entry.get("name") or Path(target).name
        parts = []
        if moved:
            dest = f"{today_folder_name()} フォルダ" if use_date else "直接"
            parts.append(f"{moved} 個を [{label}] に{dest}移動しました。")
        if errors:
            parts.append("エラー:\n" + "\n".join(errors))
        if parts:
            self.tray.showMessage("DateFiler", "\n".join(parts),
                                  QSystemTrayIcon.MessageIcon.Information, 3000)

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        dlg.exec()
        self._rebuild_tiles()

    def _hide_to_tray(self):
        self.settings["window_width"] = self.width()
        self.settings["window_height"] = self.height()
        save_settings(self.settings)
        self.hide()
        self.tray.showMessage(
            "DateFiler",
            "タスクバー右下の「^」→「D」アイコンをクリックすると再表示できます。",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )

    def closeEvent(self, event):
        self.settings["window_width"] = self.width()
        self.settings["window_height"] = self.height()
        save_settings(self.settings)
        event.ignore()
        self.hide()


# ---- タイトルバー色（Windows 11 DWM API）----------------------------------

def _set_titlebar_color(window, hex_color: str):
    try:
        hwnd = int(window.winId())
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        colorref = r | (g << 8) | (b << 16)
        DWMWA_CAPTION_COLOR = 35
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR,
            ctypes.byref(ctypes.c_uint(colorref)), ctypes.sizeof(ctypes.c_uint)
        )
    except Exception:
        pass


# ---- エントリポイント -------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app.setStyleSheet("""
        QMainWindow { background-color: #F3F9FE; }
        QWidget { background-color: #F3F9FE; }
        QLineEdit, QListWidget { background-color: #FFFFFF; }
        QCheckBox { color: #1A1A1A; }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            border: 1px solid #888888;
            border-radius: 2px;
            background-color: #FFFFFF;
        }
        QCheckBox::indicator:checked {
            border: 2px solid #0078D4;
            background-color: #0078D4;
        }
    """)

    icon = make_app_icon()
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("DateFiler")

    window = MainWindow(tray)

    menu = QMenu()
    menu.addAction("DateFiler を開く").triggered.connect(window.show)
    menu.addAction("終了").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show()
        if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.show()
    window.show()
    _set_titlebar_color(window, "#E6F3FD")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
