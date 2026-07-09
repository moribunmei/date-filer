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
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QColor, QPixmap, QPainter, QFont


SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"
ZONE_SIZE = 200  # ドロップゾーンの固定サイズ (px)
GRID_COLS = 3    # グリッドの列数

# ---- 設定の読み書き --------------------------------------------------------

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        folders = data.get("folders", [])
        # 旧形式（文字列リスト）→ 新形式
        if folders and isinstance(folders[0], str):
            data["folders"] = [{"path": p, "name": "", "use_date_folder": True} for p in folders]
        else:
            # use_date_folder が無いエントリを補完
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


# ---- システムトレイアイコン生成 -------------------------------------------

def make_app_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#4A90E2"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 28, 28, 6, 6)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 12, QFont.Weight.Bold))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "D")
    p.end()
    return QIcon(px)


# ---- ドロップゾーン --------------------------------------------------------

class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    IDLE_STYLE = """
        QFrame {
            border: 2px dashed #aaa;
            border-radius: 12px;
            background: #f5f5f5;
        }
    """
    HOVER_STYLE = """
        QFrame {
            border: 2px dashed #4A90E2;
            border-radius: 12px;
            background: #e8f0fe;
        }
    """

    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self.setAcceptDrops(True)
        self.setFixedSize(ZONE_SIZE, ZONE_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(6)

        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet(
            "color: #222; font-size: 13px; font-weight: bold; border: none; background: transparent;"
        )

        self._path_label = QLabel()
        self._path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet(
            "color: #888; font-size: 9px; border: none; background: transparent;"
        )

        self._hint_label = QLabel("ここにドロップ")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet(
            "color: #bbb; font-size: 11px; border: none; background: transparent;"
        )

        self._date_label = QLabel()
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._date_label.setStyleSheet(
            "color: #4A90E2; font-size: 9px; border: none; background: transparent;"
        )

        layout.addStretch()
        layout.addWidget(self._name_label)
        layout.addWidget(self._path_label)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._date_label)
        layout.addStretch()

        self.refresh()

    def refresh(self):
        entry = self.folder_entry
        name = entry.get("name", "").strip()
        path = entry.get("path", "")
        use_date = entry.get("use_date_folder", True)
        self._name_label.setText(name if name else Path(path).name)
        self._path_label.setText(path if name else "")
        self._date_label.setText("日付フォルダあり" if use_date else "直接移動")
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


# ---- フォルダ追加・編集ダイアログ ------------------------------------------

class FolderEditDialog(QDialog):
    def __init__(self, entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フォルダの追加" if entry is None else "フォルダの編集")
        self.setMinimumWidth(440)
        self.result_entry: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # フォルダパス
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

        # 表示名
        layout.addWidget(QLabel("表示名（任意）:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("省略するとフォルダ名で表示されます")
        if entry:
            self._name_edit.setText(entry.get("name", ""))
        layout.addWidget(self._name_edit)

        # 日付フォルダの生成
        self._date_check = QCheckBox("日付フォルダを生成する（例: 260709）")
        self._date_check.setChecked(entry.get("use_date_folder", True) if entry else True)
        layout.addWidget(self._date_check)

        # ボタン
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
            date_mark = "[日付あり]" if use_date else "[直接]"
            display = f"{date_mark}  {name}  [{path}]" if name else f"{date_mark}  {path}"
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
        root.setSpacing(10)

        # ヘッダー行
        top = QHBoxLayout()
        title = QLabel("DateFiler")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        top.addWidget(title)
        top.addStretch()
        settings_btn = QPushButton("⚙ フォルダ登録")
        settings_btn.clicked.connect(self._open_settings)
        top.addWidget(settings_btn)
        root.addLayout(top)

        # スクロール可能なドロップゾーングリッド
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._drop_container = QWidget()
        self._drop_layout = QGridLayout(self._drop_container)
        self._drop_layout.setSpacing(12)
        self._drop_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._drop_container)
        root.addWidget(scroll)

        hide_btn = QPushButton("トレイに格納")
        hide_btn.clicked.connect(self._hide_to_tray)
        root.addWidget(hide_btn)

        self._rebuild_drop_zones()

    def _rebuild_drop_zones(self):
        while self._drop_layout.count():
            item = self._drop_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        folders = self.settings["folders"]
        if not folders:
            placeholder = QLabel("⚙ フォルダ登録 からフォルダを追加してください")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("color: #aaa; font-size: 13px; padding: 40px;")
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
            "タスクバー右下の「^」→「D」アイコンをクリックすると再表示できます。\n"
            "常に表示したい場合はアイコンをドラッグしてトレイ外に移動してください。",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
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
