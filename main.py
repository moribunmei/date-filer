import sys
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QFileDialog, QMessageBox,
    QSystemTrayIcon, QMenu, QDialog, QListWidgetItem, QFrame
)
from PyQt6.QtCore import Qt, QMimeData, pyqtSignal
from PyQt6.QtGui import QIcon, QDragEnterEvent, QDropEvent, QColor, QPalette, QPixmap, QPainter, QFont


SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"folders": []}


def save_settings(settings: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def today_folder_name() -> str:
    return datetime.now().strftime("%y%m%d")


def move_file_to_dated_folder(src: str, dest_folder: str) -> str:
    date_subfolder = Path(dest_folder) / today_folder_name()
    date_subfolder.mkdir(parents=True, exist_ok=True)
    dest_path = date_subfolder / Path(src).name
    # 同名ファイルが存在する場合は番号を付ける
    if dest_path.exists():
        stem = Path(src).stem
        suffix = Path(src).suffix
        n = 1
        while dest_path.exists():
            dest_path = date_subfolder / f"{stem}_{n}{suffix}"
            n += 1
    shutil.move(src, dest_path)
    return str(dest_path)


def make_tray_icon() -> QIcon:
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


class DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        self._label = QLabel("ここにファイルをドラッグ＆ドロップ")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(self._label)
        self._set_idle()

    def _set_idle(self):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #aaa;
                border-radius: 8px;
                background: #f9f9f9;
            }
        """)
        self._label.setText("ここにファイルをドラッグ＆ドロップ")

    def _set_hover(self):
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #4A90E2;
                border-radius: 8px;
                background: #e8f0fe;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_hover()

    def dragLeaveEvent(self, event):
        self._set_idle()

    def dropEvent(self, event: QDropEvent):
        self._set_idle()
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


class FolderSelectDialog(QDialog):
    def __init__(self, folders: list, files: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("移動先フォルダの選択")
        self.setMinimumWidth(400)
        self.selected_folder = None

        layout = QVBoxLayout(self)

        info = QLabel(f"{len(files)} 個のファイルを移動します。移動先フォルダを選択してください。")
        info.setWordWrap(True)
        layout.addWidget(info)

        self._list = QListWidget()
        for f in folders:
            self._list.addItem(f)
        self._list.setCurrentRow(0)
        layout.addWidget(self._list)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("移動")
        ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _accept(self):
        item = self._list.currentItem()
        if item:
            self.selected_folder = item.text()
            self.accept()


class MainWindow(QMainWindow):
    def __init__(self, tray: QSystemTrayIcon):
        super().__init__()
        self.tray = tray
        self.settings = load_settings()
        self.setWindowTitle("DateFiler - フォルダ登録")
        self.setMinimumWidth(500)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ドロップゾーン
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self.drop_zone)

        # 登録フォルダリスト
        folder_label = QLabel("登録フォルダ")
        folder_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(folder_label)

        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for f in self.settings["folders"]:
            self.folder_list.addItem(f)
        layout.addWidget(self.folder_list)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("フォルダを追加")
        add_btn.clicked.connect(self._add_folder)
        remove_btn = QPushButton("選択を削除")
        remove_btn.clicked.connect(self._remove_folder)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)

        hide_btn = QPushButton("最小化してトレイに格納")
        hide_btn.clicked.connect(self.hide)
        layout.addWidget(hide_btn)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "登録するフォルダを選択")
        if folder and folder not in self.settings["folders"]:
            self.settings["folders"].append(folder)
            self.folder_list.addItem(folder)
            save_settings(self.settings)

    def _remove_folder(self):
        row = self.folder_list.currentRow()
        if row >= 0:
            self.settings["folders"].pop(row)
            self.folder_list.takeItem(row)
            save_settings(self.settings)

    def _on_files_dropped(self, paths: list):
        folders = self.settings["folders"]
        if not folders:
            QMessageBox.warning(self, "フォルダ未登録", "先に移動先フォルダを登録してください。")
            return

        if len(folders) == 1:
            target = folders[0]
        else:
            dlg = FolderSelectDialog(folders, paths, self)
            if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selected_folder:
                return
            target = dlg.selected_folder

        errors = []
        moved = []
        for p in paths:
            if not os.path.isfile(p):
                errors.append(f"{p} はファイルではありません")
                continue
            try:
                dest = move_file_to_dated_folder(p, target)
                moved.append(dest)
            except Exception as e:
                errors.append(f"{p}: {e}")

        msg_parts = []
        if moved:
            date_dir = today_folder_name()
            msg_parts.append(f"{len(moved)} 個のファイルを {target}\\{date_dir} に移動しました。")
        if errors:
            msg_parts.append("エラー:\n" + "\n".join(errors))

        msg = "\n".join(msg_parts)
        self.tray.showMessage("DateFiler", msg, QSystemTrayIcon.MessageIcon.Information, 3000)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon = make_tray_icon()

    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("DateFiler")

    window = MainWindow(tray)

    menu = QMenu()
    show_action = menu.addAction("設定を開く")
    show_action.triggered.connect(window.show)
    quit_action = menu.addAction("終了")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)

    tray.activated.connect(lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
