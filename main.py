import sys
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QDialog, QListWidgetItem, QFrame,
    QScrollArea, QLineEdit, QSizePolicy, QGridLayout, QDialogButtonBox,
    QSpacerItem,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QColor, QPixmap, QPainter, QFont


SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"

# ---- 設定の読み書き --------------------------------------------------------

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # 旧形式（文字列リスト）を新形式に変換
        folders = data.get("folders", [])
        if folders and isinstance(folders[0], str):
            data["folders"] = [{"path": p, "name": ""} for p in folders]
        return data
    return {"folders": []}


def save_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ---- ファイル移動ロジック --------------------------------------------------

def today_folder_name() -> str:
    return datetime.now().strftime("%y%m%d")


def move_file_to_dated_folder(src: str, dest_folder: str) -> str:
    date_subfolder = Path(dest_folder) / today_folder_name()
    date_subfolder.mkdir(parents=True, exist_ok=True)
    dest_path = date_subfolder / Path(src).name
    if dest_path.exists():
        stem = Path(src).stem
        suffix = Path(src).suffix
        n = 1
        while dest_path.exists():
            dest_path = date_subfolder / f"{stem}_{n}{suffix}"
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
    font = QFont("Arial", 12, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "D")
    p.end()
    return QIcon(px)


# ---- ドロップゾーン --------------------------------------------------------

class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    IDLE_STYLE = """
        QFrame {
            border: 2px dashed #aaa;
            border-radius: 10px;
            background: #f5f5f5;
        }
    """
    HOVER_STYLE = """
        QFrame {
            border: 2px dashed #4A90E2;
            border-radius: 10px;
            background: #e8f0fe;
        }
    """

    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self.setAcceptDrops(True)
        self.setMinimumSize(160, 130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet("color: #222; font-size: 14px; font-weight: bold; border: none; background: transparent;")

        self._path_label = QLabel()
        self._path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("color: #888; font-size: 10px; border: none; background: transparent;")

        self._hint_label = QLabel("ここにドロップ")
        self._hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint_label.setStyleSheet("color: #aaa; font-size: 11px; border: none; background: transparent;")

        layout.addWidget(self._name_label)
        layout.addWidget(self._path_label)
        layout.addWidget(self._hint_label)

        self.refresh()

    def refresh(self):
        entry = self.folder_entry
        name = entry.get("name", "").strip()
        path = entry.get("path", "")
        self._name_label.setText(name if name else Path(path).name)
        self._path_label.setText(path if name else "")
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
        self.setMinimumWidth(420)
        self.result_entry: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # フォルダパス
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("フォルダのパス")
        if entry:
            self._path_edit.setText(entry.get("path", ""))
        browse_btn = QPushButton("参照...")
        browse_btn.setFixedWidth(60)
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self._path_edit)
        path_layout.addWidget(browse_btn)
        layout.addWidget(QLabel("フォルダ:"))
        layout.addLayout(path_layout)

        # 固有名
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("省略するとフォルダ名で表示されます")
        if entry:
            self._name_edit.setText(entry.get("name", ""))
        layout.addWidget(QLabel("表示名（任意）:"))
        layout.addWidget(self._name_edit)

        # ボタン
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
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
        self.result_entry = {"path": path, "name": self._name_edit.text().strip()}
        self.accept()


# ---- 登録フォルダ管理ダイアログ --------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("フォルダ登録設定")
        self.setMinimumSize(500, 320)
        self.settings = settings

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("登録フォルダ一覧"))

        self._list = QListWidget()
        self._refresh_list()
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("追加")
        add_btn.clicked.connect(self._add)
        edit_btn = QPushButton("編集")
        edit_btn.clicked.connect(self._edit)
        remove_btn = QPushButton("削除")
        remove_btn.clicked.connect(self._remove)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)

        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _refresh_list(self):
        self._list.clear()
        for entry in self.settings["folders"]:
            name = entry.get("name", "").strip()
            path = entry.get("path", "")
            display = f"{name}  [{path}]" if name else path
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
        reply = QMessageBox.question(self, "削除確認", f"「{name}」を削除しますか？")
        if reply == QMessageBox.StandardButton.Yes:
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
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ツールバー行
        top = QHBoxLayout()
        title = QLabel("DateFiler")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        top.addWidget(title)
        top.addStretch()
        settings_btn = QPushButton("⚙ フォルダ登録")
        settings_btn.clicked.connect(self._open_settings)
        top.addWidget(settings_btn)
        root.addLayout(top)

        # スクロールエリア（ドロップゾーンを並べる）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._drop_container = QWidget()
        self._drop_layout = QGridLayout(self._drop_container)
        self._drop_layout.setSpacing(10)
        scroll.setWidget(self._drop_container)
        root.addWidget(scroll)

        # 最小化ボタン
        hide_btn = QPushButton("トレイに格納")
        hide_btn.clicked.connect(self.hide)
        root.addWidget(hide_btn)

        self._rebuild_drop_zones()

    def _rebuild_drop_zones(self):
        # 既存ウィジェットをクリア
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

        cols = 2
        for i, entry in enumerate(folders):
            zone = DropZone(entry)
            zone.files_dropped.connect(lambda paths, e=entry: self._on_drop(paths, e))
            self._drop_layout.addWidget(zone, i // cols, i % cols)

        # グリッドの余白を詰める
        self._drop_layout.setRowStretch(len(folders) // cols + 1, 1)

    def _on_drop(self, paths: list, entry: dict):
        target = entry["path"]
        errors = []
        moved_count = 0
        for p in paths:
            if not os.path.isfile(p):
                errors.append(f"{Path(p).name} はファイルではありません")
                continue
            try:
                move_file_to_dated_folder(p, target)
                moved_count += 1
            except Exception as e:
                errors.append(f"{Path(p).name}: {e}")

        label = entry.get("name") or Path(target).name
        date_dir = today_folder_name()
        msg_parts = []
        if moved_count:
            msg_parts.append(f"{moved_count} 個を [{label}] → {date_dir} に移動しました。")
        if errors:
            msg_parts.append("エラー:\n" + "\n".join(errors))
        self.tray.showMessage("DateFiler", "\n".join(msg_parts),
                              QSystemTrayIcon.MessageIcon.Information, 3000)

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
    show_action = menu.addAction("DateFiler を開く")
    show_action.triggered.connect(window.show)
    quit_action = menu.addAction("終了")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.show()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
