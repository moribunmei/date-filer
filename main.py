import sys
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QDialog, QFrame,
    QScrollArea, QLineEdit, QGridLayout, QDialogButtonBox, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import (
    QIcon, QDragEnterEvent, QDropEvent, QColor, QPixmap,
    QPainter, QFont, QPen, QBrush,
)

SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"
ZONE_W = 150
ZONE_H = 100
GRID_COLS = 4

# ---- 設定の読み書き --------------------------------------------------------

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        folders = data.get("folders", [])
        if folders and isinstance(folders[0], str):
            data["folders"] = [{"path": p, "name": "", "use_date_folder": True} for p in folders]
        else:
            for entry in folders:
                entry.setdefault("use_date_folder", True)
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


# ---- アイコン生成ユーティリティ -------------------------------------------

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
    """歯車アイコン"""
    def draw(p: QPainter, s: int):
        cx, cy, r_out, r_in = s / 2, s / 2, s * 0.42, s * 0.18
        teeth = 8
        import math
        path_pts = []
        for i in range(teeth * 2):
            angle = math.radians(i * 360 / (teeth * 2))
            r = r_out if i % 2 == 0 else r_out * 0.72
            path_pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        poly = QPolygonF([QPointF(x, y) for x, y in path_pts])
        p.setBrush(QColor("#555"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(poly)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(cx, cy), r_in, r_in)
    return _make_icon(size, draw)


def make_tray_icon_btn(size: int = 28) -> QIcon:
    """下矢印（トレイ格納）アイコン"""
    def draw(p: QPainter, s: int):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#555"))
        m = s * 0.22
        w, h = s - m * 2, s * 0.14
        p.drawRect(int(m), int(s * 0.22), int(w), int(h))
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        cx = s / 2
        tip_y = s * 0.82
        arrow_w = s * 0.38
        arrow_h = s * 0.30
        poly = QPolygonF([
            QPointF(cx - arrow_w, tip_y - arrow_h),
            QPointF(cx + arrow_w, tip_y - arrow_h),
            QPointF(cx, tip_y),
        ])
        p.drawPolygon(poly)
    return _make_icon(size, draw)



# ---- アイコンボタンヘルパー -----------------------------------------------

def icon_button(icon: QIcon, tooltip: str, size: int = 36) -> QPushButton:
    btn = QPushButton()
    btn.setIcon(icon)
    btn.setIconSize(QSize(size - 8, size - 8))
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setStyleSheet("""
        QPushButton {
            border: 1px solid #ddd;
            border-radius: 6px;
            background: #f0f0f0;
        }
        QPushButton:hover { background: #e0e8f8; border-color: #4A90E2; }
        QPushButton:pressed { background: #c8d8f0; }
    """)
    return btn


# ---- ドロップゾーン --------------------------------------------------------

class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    IDLE_STYLE = """
        QFrame {
            border: 2px solid #ddd;
            border-radius: 8px;
            background: #fafafa;
        }
    """
    HOVER_STYLE = """
        QFrame {
            border: 2px solid #4A90E2;
            border-radius: 8px;
            background: #e8f0fe;
        }
    """

    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self.setAcceptDrops(True)
        self.setFixedSize(ZONE_W, ZONE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(2)

        # フォルダ名
        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet(
            "color: #222; font-size: 12px; font-weight: bold; border: none; background: transparent;"
        )

        # ドロップヒント
        self._hint_label = QLabel("ここにドロップ")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet(
            "color: #ccc; font-size: 9px; border: none; background: transparent;"
        )

        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_label.setStyleSheet(
            "color: #aaa; font-size: 9px; border: none; background: transparent;"
        )

        root.addStretch()
        root.addWidget(self._name_label)
        root.addWidget(self._hint_label)
        root.addWidget(self._date_label)
        root.addStretch()

        self.refresh()

    def refresh(self):
        entry = self.folder_entry
        name = entry.get("name", "").strip()
        path = entry.get("path", "")
        use_date = entry.get("use_date_folder", True)
        self._name_label.setText(name if name else Path(path).name)
        self._date_label.setText("日付あり" if use_date else "日付なし")
        self.setStyleSheet(self.IDLE_STYLE)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self.HOVER_STYLE)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.IDLE_STYLE)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self.IDLE_STYLE)
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
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("フォルダのパス")
        if entry:
            self._path_edit.setText(entry.get("path", ""))
        browse_btn = QPushButton("参照...")
        browse_btn.setFixedWidth(64)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._path_edit)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        layout.addWidget(QLabel("表示名（任意）:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("省略するとフォルダ名で表示されます")
        if entry:
            self._name_edit.setText(entry.get("name", ""))
        layout.addWidget(self._name_edit)

        self._date_check = QCheckBox("日付フォルダを生成する（例: 260709）")
        self._date_check.setChecked(entry.get("use_date_folder", True) if entry else True)
        layout.addWidget(self._date_check)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "フォルダを選択")
        if folder:
            self._path_edit.setText(folder)

    def _accept(self):
        path = self._path_edit.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "エラー", "有効なフォルダパスを指定してください。")
            return
        self.result_entry = {
            "path": path,
            "name": self._name_edit.text().strip(),
            "use_date_folder": self._date_check.isChecked(),
        }
        self.accept()


# ---- 登録フォルダ管理ダイアログ --------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フォルダ登録設定")
        self.setMinimumSize(520, 340)
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
            use_date = entry.get("use_date_folder", True)
            mark = "📅" if use_date else "📂"
            display = f"{mark}  {name}  [{path}]" if name else f"{mark}  {path}"
            self._list.addItem(display)

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
        if QMessageBox.question(self, "削除確認", f"「{name}」を削除しますか？") == QMessageBox.StandardButton.Yes:
            self.settings["folders"].pop(row)
            save_settings(self.settings)
            self._refresh_list()


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
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ドロップゾーングリッド（スクロール）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._drop_container = QWidget()
        self._drop_layout = QGridLayout(self._drop_container)
        self._drop_layout.setSpacing(10)
        self._drop_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._drop_container)
        root.addWidget(scroll)

        # ボトムバー（右寄せアイコンボタン）
        bottom = QHBoxLayout()
        bottom.addStretch()

        self._settings_btn = icon_button(make_settings_icon(28), "フォルダ登録", 36)
        self._settings_btn.clicked.connect(self._open_settings)

        self._tray_btn = icon_button(make_tray_icon_btn(28), "トレイに格納", 36)
        self._tray_btn.clicked.connect(self._hide_to_tray)

        bottom.addWidget(self._settings_btn)
        bottom.addWidget(self._tray_btn)
        root.addLayout(bottom)

        self._rebuild_drop_zones()

    def _rebuild_drop_zones(self):
        while self._drop_layout.count():
            item = self._drop_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        folders = self.settings["folders"]
        if not folders:
            placeholder = QLabel("右下の歯車ボタンからフォルダを追加してください")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #bbb; font-size: 12px; padding: 40px;")
            self._drop_layout.addWidget(placeholder, 0, 0)
            return

        for i, entry in enumerate(folders):
            zone = DropZone(entry)
            zone.files_dropped.connect(lambda paths, e=entry: self._on_drop(paths, e))
            self._drop_layout.addWidget(zone, i // GRID_COLS, i % GRID_COLS)

    def _on_drop(self, paths: list, entry: dict):
        use_date = entry.get("use_date_folder", True)
        target = entry["path"]
        errors = []
        moved_count = 0
        for p in paths:
            if not os.path.isfile(p):
                errors.append(f"{Path(p).name} はファイルではありません")
                continue
            try:
                move_file(p, target, use_date)
                moved_count += 1
            except Exception as e:
                errors.append(f"{Path(p).name}: {e}")

        label = entry.get("name") or Path(target).name
        msg_parts = []
        if moved_count:
            dest_desc = f"{today_folder_name()} フォルダ" if use_date else "直接"
            msg_parts.append(f"{moved_count} 個を [{label}] に{dest_desc}移動しました。")
        if errors:
            msg_parts.append("エラー:\n" + "\n".join(errors))
        self.tray.showMessage("DateFiler", "\n".join(msg_parts),
                              QSystemTrayIcon.MessageIcon.Information, 3000)

    def _hide_to_tray(self):
        self.hide()
        self.tray.showMessage(
            "DateFiler",
            "タスクバー右下の「^」→「D」アイコンをクリックすると再表示できます。",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        dlg.exec()
        self._rebuild_drop_zones()

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
