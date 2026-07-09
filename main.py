import sys
import os
import json
import shutil
import math
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QDialog, QFrame,
    QLineEdit, QDialogButtonBox, QCheckBox,
    QTabWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import (
    QIcon, QDragEnterEvent, QDropEvent, QColor, QPixmap,
    QPainter, QFont, QPen, QBrush,
)

SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"
ZONE_W = 150
ZONE_H = 100


# ---- 設定の読み書き --------------------------------------------------------

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        folders = data.get("folders", [])
        if folders and isinstance(folders[0], str):
            folders = [{"path": p, "name": "", "use_date_folder": True,
                        "show_shortcut": True, "show_filemove": True} for p in folders]
            data["folders"] = folders
        else:
            for entry in folders:
                entry.setdefault("use_date_folder", True)
                entry.setdefault("show_shortcut", True)
                entry.setdefault("show_filemove", True)
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
        p.setBrush(QColor("#4A90E2"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(2, 2, s - 4, s - 4, 6, 6)
        p.setPen(QColor("white"))
        p.setFont(QFont("Noto Sans JP", int(s * 0.4), QFont.Weight.Bold))
        p.drawText(0, 0, s, s, Qt.AlignmentFlag.AlignCenter, "D")
    return _make_icon(32, draw)


def make_settings_icon(size: int = 28) -> QIcon:
    def draw(p: QPainter, s: int):
        import math
        cx, cy, r_out, r_in = s / 2, s / 2, s * 0.42, s * 0.18
        teeth = 8
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        pts = []
        for i in range(teeth * 2):
            angle = math.radians(i * 360 / (teeth * 2))
            r = r_out if i % 2 == 0 else r_out * 0.72
            pts.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))
        p.setBrush(QColor("#555"))
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
        p.setBrush(QColor("#555"))
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


def icon_button(icon: QIcon, tooltip: str, size: int = 36) -> QPushButton:
    btn = QPushButton()
    btn.setIcon(icon)
    btn.setIconSize(QSize(size - 8, size - 8))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setStyleSheet("""
        QPushButton {
            border: 1px solid #ccc;
            border-radius: 6px;
            background: #f0f0f0;
        }
        QPushButton:hover  { background: #e0e8f8; border-color: #4A90E2; }
        QPushButton:pressed { background: #c8d8f0; }
    """)
    return btn


# ---- タイル共通スタイル ----------------------------------------------------

_TILE_BASE = """
    QFrame {{
        border: 2px solid {border};
        border-radius: 8px;
        background: {bg};
    }}
"""
TILE_IDLE       = _TILE_BASE.format(border="#ddd",    bg="#f8f8f8")
TILE_HOVER_DARK = _TILE_BASE.format(border="#4A90E2", bg="#e8f0fe")
TILE_IDLE_LIGHT  = TILE_IDLE
TILE_HOVER_LIGHT = TILE_HOVER_DARK


# ---- ショートカットタイル（クリックでフォルダを開く）-----------------------

class ShortcutTile(QFrame):
    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self.setFixedSize(ZONE_W, ZONE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(TILE_IDLE_LIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        self._name = QLabel()
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(True)
        self._name.setStyleSheet(
            "color: #222; font-size: 12px; font-weight: bold;"
            " border: none; background: transparent;"
        )

        self._sub = QLabel()
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setWordWrap(True)
        self._sub.setStyleSheet(
            "color: #999; font-size: 9px; border: none; background: transparent;"
        )

        layout.addStretch()
        layout.addWidget(self._name)
        layout.addWidget(self._sub)
        layout.addStretch()

        self._refresh()

    def _refresh(self):
        name = self.folder_entry.get("name", "").strip()
        path = self.folder_entry.get("path", "")
        self._name.setText(name if name else Path(path).name)
        self._sub.setText(path if name else "")

    def enterEvent(self, event):
        self.setStyleSheet(TILE_HOVER_LIGHT)

    def leaveEvent(self, event):
        self.setStyleSheet(TILE_IDLE_LIGHT)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            path = self.folder_entry.get("path", "")
            if path and os.path.isdir(path):
                os.startfile(path)


# ---- ドロップゾーン（D&D でファイルを移動）---------------------------------

class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    DRAG_HOVER = TILE_HOVER_DARK

    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self.setAcceptDrops(True)
        self.setFixedSize(ZONE_W, ZONE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(TILE_IDLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._name = QLabel()
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(True)
        self._name.setStyleSheet(
            "color: #222; font-size: 12px; font-weight: bold;"
            " border: none; background: transparent;"
        )

        self._hint = QLabel("ここにドロップ")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet(
            "color: #bbb; font-size: 9px; border: none; background: transparent;"
        )

        self._date = QLabel()
        self._date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date.setStyleSheet(
            "color: #aaa; font-size: 9px; border: none; background: transparent;"
        )

        layout.addStretch()
        layout.addWidget(self._name)
        layout.addWidget(self._hint)
        layout.addWidget(self._date)
        layout.addStretch()

        self._refresh()

    def _refresh(self):
        name = self.folder_entry.get("name", "").strip()
        path = self.folder_entry.get("path", "")
        use_date = self.folder_entry.get("use_date_folder", True)
        self._name.setText(name if name else Path(path).name)
        self._date.setText("日付あり" if use_date else "日付なし")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self.DRAG_HOVER)

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

        layout.addWidget(QLabel("表示画面:"))
        self._sc_check = QCheckBox("ショートカット画面に表示")
        self._sc_check.setChecked(entry.get("show_shortcut", True) if entry else True)
        self._fm_check = QCheckBox("ファイル移動画面に表示")
        self._fm_check.setChecked(entry.get("show_filemove", True) if entry else True)
        layout.addWidget(self._sc_check)
        layout.addWidget(self._fm_check)

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
        if not self._sc_check.isChecked() and not self._fm_check.isChecked():
            QMessageBox.warning(self, "エラー", "表示画面をどちらか一方は選択してください。")
            return
        self.result_entry = {
            "path": path,
            "name": self._name.text().strip(),
            "use_date_folder": self._date_check.isChecked(),
            "show_shortcut": self._sc_check.isChecked(),
            "show_filemove": self._fm_check.isChecked(),
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
            sc   = "SC" if entry.get("show_shortcut", True) else "  "
            fm   = "FM" if entry.get("show_filemove", True) else "  "
            dt   = "📅" if entry.get("use_date_folder", True) else "📂"
            label = name if name else Path(path).name
            self._list.addItem(f"[{sc}][{fm}] {dt}  {label}  —  {path}")

    def _add(self):
        dlg = FolderEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            self.settings["folders"].append(dlg.result_entry)
            save_settings(self.settings)
            self._refresh_list()

    def _edit(self):
        row = self._list.currentRow()
        if row < 0:
            return
        dlg = FolderEditDialog(entry=self.settings["folders"][row], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            self.settings["folders"][row] = dlg.result_entry
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


# ---- タイルグリッド（幅に応じて折り返し、高さ自動調整）--------------------

class TileGrid(QWidget):
    _GAP = 10
    _MARGIN = 12

    def __init__(self, tiles: list, empty_text: str = ""):
        super().__init__()
        self._tiles = tiles
        for t in tiles:
            t.setParent(self)
        if not tiles:
            self._ph = QLabel(empty_text)
            self._ph.setParent(self)
            self._ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ph.setStyleSheet("color: #aaa; font-size: 12px;")

    def _layout_params(self, w: int):
        """(cols, rows, needed_height) を返す"""
        if not self._tiles:
            return 1, 0, 80
        avail = max(w - self._MARGIN * 2, ZONE_W)
        cols = max(1, (avail + self._GAP) // (ZONE_W + self._GAP))
        rows = math.ceil(len(self._tiles) / cols)
        h = self._MARGIN + rows * (ZONE_H + self._GAP) - self._GAP + self._MARGIN
        return cols, rows, h

    def needed_height(self) -> int:
        _, _, h = self._layout_params(self.width() or (ZONE_W + self._MARGIN * 2))
        return h

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        if not self._tiles:
            if hasattr(self, '_ph'):
                self._ph.setGeometry(0, 0, w, 80)
            return
        cols, _, _ = self._layout_params(w)
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
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # トップバー（タブ + 右上アイコン）
        top = QHBoxLayout()
        top.setSpacing(6)
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.currentChanged.connect(lambda _: self._fit_height())
        top.addWidget(self._tabs)

        self._settings_btn = icon_button(make_settings_icon(28), "フォルダ登録", 32)
        self._settings_btn.clicked.connect(self._open_settings)
        self._tray_btn = icon_button(make_tray_icon_btn(28), "トレイに格納", 32)
        self._tray_btn.clicked.connect(self._hide_to_tray)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        btn_col.addWidget(self._settings_btn)
        btn_col.addWidget(self._tray_btn)
        btn_col.addStretch()
        top.addLayout(btn_col)

        root.addLayout(top)

        # 高さ自動調整用（デバウンス）
        self._fitting = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._fit_height)

        self._rebuild_tabs()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fitting:
            self._fitting = False
            return
        self._resize_timer.start(0)

    def _fit_height(self):
        current = self._tabs.currentWidget()
        if not isinstance(current, TileGrid):
            return
        needed = current.needed_height()
        tab_bar_h = self._tabs.tabBar().height()
        total = needed + tab_bar_h + 16  # 16 = 上下マージン(8+8)
        if abs(self.height() - total) > 2:
            self._fitting = True
            self.resize(self.width(), total)

    def _rebuild_tabs(self):
        current_tab = self._tabs.currentIndex()
        self._tabs.clear()

        folders = self.settings["folders"]

        # ショートカットタブ
        sc_tiles = [ShortcutTile(e) for e in folders if e.get("show_shortcut", True)]
        sc_grid = TileGrid(sc_tiles, "右上の歯車ボタンからフォルダを追加してください")
        self._tabs.addTab(sc_grid, "ショートカット")

        # ファイル移動タブ
        fm_tiles = []
        for entry in folders:
            if entry.get("show_filemove", True):
                zone = DropZone(entry)
                zone.files_dropped.connect(lambda paths, e=entry: self._on_drop(paths, e))
                fm_tiles.append(zone)
        fm_grid = TileGrid(fm_tiles, "右上の歯車ボタンからフォルダを追加してください")
        self._tabs.addTab(fm_grid, "ファイル移動")

        # タブ復元 → 高さ調整
        if 0 <= current_tab < self._tabs.count():
            self._tabs.setCurrentIndex(current_tab)
        QTimer.singleShot(50, self._fit_height)

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

        label = entry.get("name") or Path(target).name
        parts = []
        if moved:
            dest = f"{today_folder_name()} フォルダ" if use_date else "直接"
            parts.append(f"{moved} 個を [{label}] に{dest}移動しました。")
        if errors:
            parts.append("エラー:\n" + "\n".join(errors))
        self.tray.showMessage("DateFiler", "\n".join(parts),
                              QSystemTrayIcon.MessageIcon.Information, 3000)

    def _hide_to_tray(self):
        self.hide()
        self.tray.showMessage(
            "DateFiler",
            "タスクバー右下の「^」→「D」アイコンをクリックすると再表示できます。",
            QSystemTrayIcon.MessageIcon.Information, 4000,
        )

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        dlg.exec()
        self._rebuild_tabs()

    def closeEvent(self, event):
        event.ignore()
        self.hide()


# ---- エントリポイント -------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    font = QFont("Noto Sans JP", 10)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    app.setFont(font)

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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
