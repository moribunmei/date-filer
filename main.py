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
    QLineEdit, QDialogButtonBox, QCheckBox, QSizeGrip,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPointF
from PyQt6.QtGui import (
    QIcon, QDragEnterEvent, QDropEvent, QColor, QPixmap,
    QPainter, QPen, QPalette, QPolygonF,
)

SETTINGS_PATH = Path(os.environ.get("APPDATA", ".")) / "DateFiler" / "settings.json"
TILE_W = 120
TILE_H = 110
FAB_SIZE = 44
BG_NORMAL = "#FFFFFF"
BG_EDIT = "#FFF8E1"
FOLDER_YELLOW = "#FFBB33"
FOLDER_SHADOW = "#CC8800"


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

def make_app_icon() -> QIcon:
    size = 32
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#005A9E"))
    p.drawRoundedRect(int(size * 0.06), int(size * 0.18),
                      int(size * 0.38), int(size * 0.14), 3, 3)
    p.setBrush(QColor("#0078D4"))
    p.drawRoundedRect(int(size * 0.06), int(size * 0.28),
                      int(size * 0.88), int(size * 0.58), 3, 3)
    p.setBrush(QColor("white"))
    cy = size * 0.57
    x1, x2 = size * 0.20, size * 0.75
    sh, hw, hh = size * 0.11, size * 0.20, size * 0.28
    p.drawRect(int(x1), int(cy - sh / 2), int(x2 - x1 - hw * 0.5), int(sh))
    p.drawPolygon(QPolygonF([
        QPointF(x2 - hw, cy - hh / 2),
        QPointF(x2, cy),
        QPointF(x2 - hw, cy + hh / 2),
    ]))
    p.end()
    return QIcon(px)


def make_tile_folder_pixmap(size: int = 52, has_plus: bool = False) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)

    # フォルダタブ（左上の出っ張り）
    tab_w = int(size * 0.42)
    tab_h = int(size * 0.16)
    tab_x = int(size * 0.06)
    tab_y = int(size * 0.16)
    p.setBrush(QColor(FOLDER_YELLOW))
    p.drawRoundedRect(tab_x, tab_y, tab_w, tab_h + 6, 5, 5)

    # フォルダ本体
    body_x = int(size * 0.06)
    body_y = int(size * 0.27)
    body_w = int(size * 0.88)
    body_h = int(size * 0.60)
    p.setBrush(QColor(FOLDER_YELLOW))
    p.drawRoundedRect(body_x, body_y, body_w, body_h, 5, 5)

    if has_plus:
        # 小さな円バッジ（日付フォルダ有効を表す）を左上に表示
        br = int(size * 0.20)
        bcx = int(size * 0.30)
        bcy = int(size * 0.30)
        p.setBrush(QColor("#E07800"))
        p.drawEllipse(bcx - br, bcy - br, br * 2, br * 2)
        # バッジ内の白い "+"
        p.setBrush(QColor("white"))
        bl = int(br * 0.56)
        bt = max(2, int(br * 0.22))
        p.drawRect(bcx - bl, bcy - bt // 2, bl * 2, bt)
        p.drawRect(bcx - bt // 2, bcy - bl, bt, bl * 2)

    p.end()
    return px


def make_header_folder_pixmap(size: int = 18) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#333333"))
    p.drawRoundedRect(int(size * 0.06), int(size * 0.16),
                      int(size * 0.38), int(size * 0.14), 2, 2)
    p.drawRoundedRect(int(size * 0.06), int(size * 0.26),
                      int(size * 0.88), int(size * 0.60), 3, 3)
    p.end()
    return px


def _fab_symbol_icon(kind: str, color: str = "white") -> QIcon:
    size = 20
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    cx, cy = size / 2.0, size / 2.0

    if kind == "plus":
        p.setBrush(QColor(color))
        bar = size * 0.38
        th = max(2, int(size * 0.12))
        p.drawRect(int(cx - bar), int(cy - th / 2), int(bar * 2), th)
        p.drawRect(int(cx - th / 2), int(cy - bar), th, int(bar * 2))

    elif kind == "close":
        cross = size * 0.30
        pen = QPen(QColor(color), max(2, size // 9),
                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(int(cx - cross), int(cy - cross),
                   int(cx + cross), int(cy + cross))
        p.drawLine(int(cx + cross), int(cy - cross),
                   int(cx - cross), int(cy + cross))

    elif kind == "pencil":
        angle = math.radians(-42)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        hw = size * 0.13

        def rot(dx, dy):
            return QPointF(cx + dx * cos_a - dy * sin_a,
                           cy + dx * sin_a + dy * cos_a)

        body_top, body_bot = -size * 0.34, size * 0.16
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([
            rot(-hw, body_top), rot(hw, body_top),
            rot(hw, body_bot), rot(-hw, body_bot),
        ]))
        p.setBrush(QColor(200, 200, 200))
        p.drawPolygon(QPolygonF([
            rot(-hw, body_bot), rot(hw, body_bot), rot(0, size * 0.38),
        ]))
        eh = size * 0.11
        p.setBrush(QColor(170, 170, 200))
        p.drawPolygon(QPolygonF([
            rot(-hw, body_top - eh), rot(hw, body_top - eh),
            rot(hw, body_top), rot(-hw, body_top),
        ]))

    p.end()
    return QIcon(px)


# ---- タイルスタイル定数 ----------------------------------------------------

_TILE_NORMAL = (
    "QFrame { border: none; background: transparent; border-radius: 10px; }"
)
_TILE_NORMAL_HOVER = (
    "QFrame { border: none; background: #F0F0F0; border-radius: 10px; }"
)
_TILE_LINK_NORMAL = (
    "QFrame { border: 1px solid #E8E8E8; background: #F8F8F8; border-radius: 10px; }"
)
_TILE_LINK_NORMAL_HOVER = (
    "QFrame { border: 1px solid #E8E8E8; background: #EEEEEE; border-radius: 10px; }"
)
_TILE_EDIT = (
    "QFrame { border: 1px solid #EEEEEE; background: #FFFFFF; border-radius: 10px; }"
)
_TILE_EDIT_HOVER = (
    "QFrame { border: 1px solid #EEEEEE; background: rgba(255,152,0,0.18); border-radius: 10px; }"
)


# ---- フォルダタイル --------------------------------------------------------

class FolderTile(QFrame):
    edit_requested = pyqtSignal(dict)
    files_dropped = pyqtSignal(list)
    folder_opened = pyqtSignal()

    def __init__(self, folder_entry: dict):
        super().__init__()
        self.folder_entry = folder_entry
        self._allow_filemove = folder_entry.get("allow_filemove", True)
        self._use_date_folder = folder_entry.get("use_date_folder", True)
        self._edit_mode = False
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._normal_style())
        if self._allow_filemove:
            self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        layout.addStretch()

        if self._allow_filemove:
            icon_lbl = QLabel()
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("border: none; background: transparent;")
            icon_lbl.setPixmap(make_tile_folder_pixmap(44, self._use_date_folder))
            layout.addWidget(icon_lbl)

        name_lbl = QLabel()
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            "color: #1A1A1A; font-size: 11px; font-weight: 600;"
            " border: none; background: transparent;"
        )
        name = folder_entry.get("name", "").strip()
        path = folder_entry.get("path", "")
        name_lbl.setText(name if name else Path(path).name)
        layout.addWidget(name_lbl)
        layout.addStretch()

    def _normal_style(self) -> str:
        return _TILE_LINK_NORMAL if not self._allow_filemove else _TILE_NORMAL

    def _normal_hover_style(self) -> str:
        return _TILE_LINK_NORMAL_HOVER if not self._allow_filemove else _TILE_NORMAL_HOVER

    def set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        self.setAcceptDrops(self._allow_filemove and not enabled)
        self.setStyleSheet(_TILE_EDIT if enabled else self._normal_style())

    def enterEvent(self, event):
        self.setStyleSheet(_TILE_EDIT_HOVER if self._edit_mode else self._normal_hover_style())

    def leaveEvent(self, event):
        self.setStyleSheet(_TILE_EDIT if self._edit_mode else self._normal_style())

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._normal_hover_style())

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style())

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self._normal_style())
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._edit_mode:
                self.edit_requested.emit(self.folder_entry)
            else:
                path = self.folder_entry.get("path", "")
                if path and os.path.isdir(path):
                    self.folder_opened.emit()
                    os.startfile(path)


# ---- 追加モードオーバーレイ ------------------------------------------------

class AddModeOverlay(QWidget):
    folder_dropped = pyqtSignal(str)
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(0)

        # 中央カードエリア
        center = QWidget()
        center_lyt = QVBoxLayout(center)
        center_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._card = QFrame()
        self._card.setFixedSize(260, 130)
        self._card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._set_card_hover(False)

        card_lyt = QVBoxLayout(self._card)
        card_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lyt.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        icon_lbl.setPixmap(self._make_overlay_icon(40))
        card_lyt.addWidget(icon_lbl)

        main_lbl = QLabel("フォルダをここにドロップして追加")
        main_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_lbl.setStyleSheet(
            "color: #1A1A1A; font-size: 13px; font-weight: bold;"
            " border: none; background: transparent;"
        )
        card_lyt.addWidget(main_lbl)

        center_lyt.addWidget(self._card)
        lyt.addWidget(center, 1)

        # 下部エリア：右に白い×ボタン
        bottom = QWidget()
        bottom.setFixedHeight(68)
        b_lyt = QHBoxLayout(bottom)
        b_lyt.setContentsMargins(16, 12, 16, 12)
        b_lyt.setSpacing(0)
        b_lyt.addStretch()

        r = FAB_SIZE // 2
        close_btn = QPushButton()
        close_btn.setFixedSize(FAB_SIZE, FAB_SIZE)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setIcon(_fab_symbol_icon("close", "#333333"))
        close_btn.setIconSize(QSize(FAB_SIZE - 12, FAB_SIZE - 12))
        close_btn.setStyleSheet(
            f"QPushButton {{ background: white; border-radius: {r}px; border: none; }}"
            f"QPushButton:hover {{ background: #EEEEEE; }}"
            f"QPushButton:pressed {{ background: #CCCCCC; }}"
        )
        close_btn.clicked.connect(self.close_requested.emit)
        b_lyt.addWidget(close_btn)

        lyt.addWidget(bottom)

    @staticmethod
    def _make_overlay_icon(size: int) -> QPixmap:
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#CCCCCC"))
        tab_w = int(size * 0.42)
        tab_h = int(size * 0.16)
        p.drawRoundedRect(int(size * 0.06), int(size * 0.16),
                          tab_w, tab_h + 5, 4, 4)
        p.drawRoundedRect(int(size * 0.06), int(size * 0.27),
                          int(size * 0.88), int(size * 0.60), 4, 4)
        p.end()
        return px

    def _set_card_hover(self, hover: bool):
        bg = "#F0F0F0" if hover else "#FFFFFF"
        self._card.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-radius: 14px;
                border: 1px solid #E0E0E0;
            }}
        """)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(20, 20, 20, 210))
        p.end()

    def dragEnterEvent(self, event: QDragEnterEvent):
        for url in event.mimeData().urls():
            if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                event.acceptProposedAction()
                self._set_card_hover(True)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_card_hover(False)

    def dropEvent(self, event: QDropEvent):
        self._set_card_hover(False)
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self.folder_dropped.emit(path)
                    break


# ---- グリッド＋オーバーレイコンテナ ----------------------------------------

class GridContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid: "TileGrid | None" = None

    def set_grid(self, grid: "TileGrid"):
        if self._grid is not None:
            self._grid.setParent(None)
        self._grid = grid
        grid.setParent(self)
        grid.setGeometry(self.rect())
        grid.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._grid is not None:
            self._grid.setGeometry(self.rect())


# ---- チェックマーク付きチェックボックス ------------------------------------

class _CheckBox(QCheckBox):
    _IND = 16

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sz = self._IND
        y0 = (self.height() - sz) // 2
        checked = self.isChecked()

        # インジケータ背景
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#333333" if checked else "#FFFFFF"))
        p.drawRoundedRect(0, y0, sz, sz, 3, 3)

        # 枠線（未チェック時のみ）
        if not checked:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#AAAAAA"), 1.5))
            p.drawRoundedRect(0, y0, sz, sz, 3, 3)

        # チェックマーク
        if checked:
            pen = QPen(QColor("white"), 2.0,
                       Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(int(sz * 0.19), int(y0 + sz * 0.50),
                       int(sz * 0.43), int(y0 + sz * 0.75))
            p.drawLine(int(sz * 0.43), int(y0 + sz * 0.75),
                       int(sz * 0.81), int(y0 + sz * 0.26))

        # ラベルテキスト
        fm = p.fontMetrics()
        ty = (self.height() + fm.ascent() - fm.descent()) // 2
        p.setPen(QColor("#1A1A1A"))
        p.setFont(self.font())
        p.drawText(sz + 8, ty, self.text())
        p.end()


# ---- フォルダ追加・編集ダイアログ ------------------------------------------

class FolderEditDialog(QDialog):
    def __init__(self, entry: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        is_edit = entry is not None
        self.setWindowTitle("フォルダの編集" if is_edit else "フォルダの追加")
        self.setFixedWidth(420)
        self.result_entry: dict | None = None

        self.setStyleSheet("""
            QDialog { background: #FFFFFF; border: 1px solid #DDDDDD; }
            QLabel#field_label {
                color: #555555; font-size: 11px; font-weight: 600;
            }
            QLabel#section_label {
                color: #888888; font-size: 10px; font-weight: 600;
                letter-spacing: 0.5px;
            }
            QLineEdit {
                border: 1px solid #D8D8D8;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                background: #FFFFFF;
                color: #1A1A1A;
            }
            QLineEdit:focus { border-color: #333333; }
            QCheckBox { color: #1A1A1A; font-size: 12px; spacing: 6px; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1.5px solid #AAAAAA;
                border-radius: 3px;
                background: #FFFFFF;
            }
            QCheckBox::indicator:checked {
                border: 1.5px solid #333333;
                background: #333333;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)

        # ---- タイトル ----
        title = QLabel("フォルダの編集" if is_edit else "フォルダの追加")
        title.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #1A1A1A;"
            " background: transparent; border: none;"
        )
        root.addWidget(title)
        root.addSpacing(20)

        # ---- フォルダパス ----
        lbl_path = QLabel("フォルダパス：")
        lbl_path.setObjectName("field_label")
        root.addWidget(lbl_path)
        root.addSpacing(4)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self._path = QLineEdit()
        self._path.setPlaceholderText("フォルダのパスを入力")
        if entry:
            self._path.setText(entry.get("path", ""))
        browse = QPushButton("参照")
        browse.setFixedWidth(52)
        browse.setFixedHeight(34)
        browse.setStyleSheet("""
            QPushButton {
                background: #F0F0F0; border: 1px solid #D0D0D0;
                border-radius: 6px; font-size: 12px; color: #333333;
            }
            QPushButton:hover { background: #E0E0E0; }
        """)
        browse.clicked.connect(self._browse)
        path_row.addWidget(self._path)
        path_row.addWidget(browse)
        root.addLayout(path_row)
        root.addSpacing(14)

        # ---- 表示名 ----
        lbl_name = QLabel("表示名（任意）：")
        lbl_name.setObjectName("field_label")
        root.addWidget(lbl_name)
        root.addSpacing(4)

        self._name = QLineEdit()
        self._name.setPlaceholderText("省略するとフォルダ名で表示されます")
        if entry:
            self._name.setText(entry.get("name", ""))
        root.addWidget(self._name)
        root.addSpacing(18)

        # ---- オプション ----
        lbl_opt = QLabel("オプション")
        lbl_opt.setObjectName("section_label")
        root.addWidget(lbl_opt)
        root.addSpacing(8)

        self._date_check = _CheckBox("日付フォルダを自動生成する。（例：260709）")
        self._date_check.setChecked(entry.get("use_date_folder", True) if entry else True)
        root.addWidget(self._date_check)
        root.addSpacing(6)

        self._filemove_check = _CheckBox("ファイル移動を有効にする。")
        self._filemove_check.setChecked(entry.get("allow_filemove", True) if entry else True)
        root.addWidget(self._filemove_check)
        root.addSpacing(24)

        # ---- ボタン ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        save_btn = QPushButton("保存する")
        save_btn.setFixedHeight(40)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #1A1A1A; color: white;
                border: none; border-radius: 8px;
                font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #333333; }
            QPushButton:pressed { background: #000000; }
        """)
        save_btn.clicked.connect(self._accept)

        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #FFFFFF; color: #333333;
                border: 1.5px solid #CCCCCC; border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover { background: #F5F5F5; }
        """)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

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


# ---- タイルグリッド --------------------------------------------------------

class TileGrid(QWidget):
    _GAP = 12
    _MARGIN = 16
    _SECTION_GAP = 28  # ファイル移動セクションとリンクセクションの間隔

    def __init__(self, tiles_move: list, tiles_link: list = None,
                 bg_color: str = BG_NORMAL, empty_text: str = ""):
        super().__init__()
        self.setAutoFillBackground(True)
        self._tiles_move = tiles_move
        self._tiles_link = tiles_link or []
        self._all_tiles = tiles_move + self._tiles_link
        self.set_bg(bg_color)
        for t in self._all_tiles:
            t.setParent(self)
        if not self._all_tiles:
            self._ph = QLabel(empty_text)
            self._ph.setParent(self)
            self._ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ph.setStyleSheet("color: #9E9E9E; font-size: 12px; background: transparent;")

    def set_bg(self, color: str):
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(color))
        self.setPalette(pal)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        if not self._all_tiles:
            if hasattr(self, "_ph"):
                self._ph.setGeometry(0, 0, w, 80)
            return
        avail = max(w - self._MARGIN * 2, TILE_W)
        cols = max(1, (avail + self._GAP) // (TILE_W + self._GAP))
        y = self._MARGIN

        # 上セクション：ファイル移動可のタイル
        for i, tile in enumerate(self._tiles_move):
            r, c = divmod(i, cols)
            tile.move(
                self._MARGIN + c * (TILE_W + self._GAP),
                y + r * (TILE_H + self._GAP),
            )
            tile.show()
        if self._tiles_move:
            rows = math.ceil(len(self._tiles_move) / cols)
            y += rows * (TILE_H + self._GAP) - self._GAP + self._SECTION_GAP

        # 下セクション：リンクのみのタイル
        for i, tile in enumerate(self._tiles_link):
            r, c = divmod(i, cols)
            tile.move(
                self._MARGIN + c * (TILE_W + self._GAP),
                y + r * (TILE_H + self._GAP),
            )
            tile.show()


# ---- カスタムタイトルバー ---------------------------------------------------

class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
        self.setPalette(pal)

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(14, 0, 4, 0)
        lyt.setSpacing(7)

        folder_lbl = QLabel()
        folder_lbl.setPixmap(make_header_folder_pixmap(18))
        folder_lbl.setStyleSheet("border: none; background: transparent;")
        lyt.addWidget(folder_lbl)

        title_lbl = QLabel("FOLDER")
        title_lbl.setStyleSheet(
            "color: #1A1A1A; font-size: 13px; font-weight: 700;"
            " border: none; background: transparent; letter-spacing: 1px;"
        )
        lyt.addWidget(title_lbl)
        lyt.addStretch()

        _btn_base = (
            "QPushButton { background: transparent; border: none;"
            " color: #444444; font-size: 14px;"
            " min-width: 36px; max-width: 36px;"
            " min-height: 36px; max-height: 36px; }"
        )

        self._min_btn = QPushButton("−")
        self._min_btn.setStyleSheet(_btn_base + " QPushButton:hover { background: #DADADA; }")
        self._min_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._min_btn.clicked.connect(lambda: self.window().showMinimized())
        lyt.addWidget(self._min_btn)

        self._max_btn = QPushButton("□")
        self._max_btn.setStyleSheet(_btn_base + " QPushButton:hover { background: #DADADA; }")
        self._max_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._max_btn.clicked.connect(self._toggle_maximize)
        lyt.addWidget(self._max_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setStyleSheet(
            _btn_base + " QPushButton:hover { background: #E81123; color: white; }"
        )
        self._close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._close_btn.clicked.connect(lambda: self.window().close())
        lyt.addWidget(self._close_btn)

        self._drag_pos = None

    def _toggle_maximize(self):
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            w = self.window()
            delta = event.globalPosition().toPoint() - self._drag_pos
            w.move(w.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()


# ---- メインウィンドウ -------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, tray: QSystemTrayIcon):
        super().__init__()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.tray = tray
        self.settings = load_settings()
        self.setWindowTitle("DateFiler")
        w = self.settings.get("window_width", 520)
        h = self.settings.get("window_height", 380)
        self.resize(w, h)
        self._grid: TileGrid | None = None
        self._tiles: list[FolderTile] = []
        self._in_edit_mode = False
        self._in_add_mode = False
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        central.setAutoFillBackground(True)
        self._central = central
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- カスタムタイトルバー ----
        self._title_bar = CustomTitleBar()
        root.addWidget(self._title_bar)

        # ---- グリッド領域 ----
        self._container = GridContainer()
        root.addWidget(self._container, 1)

        # ---- ボトムバー ----
        self._bottom = QWidget()
        self._bottom.setFixedHeight(68)
        self._bottom.setAutoFillBackground(True)

        b_lyt = QHBoxLayout(self._bottom)
        b_lyt.setContentsMargins(16, 12, 16, 12)
        b_lyt.setSpacing(0)

        self._edit_fab = QPushButton()
        self._edit_fab.setFixedSize(FAB_SIZE, FAB_SIZE)
        self._edit_fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_fab.clicked.connect(self._edit_fab_clicked)
        b_lyt.addWidget(self._edit_fab)

        b_lyt.addStretch()

        self._edit_label = QLabel("ただいま編集モードです")
        self._edit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit_label.setStyleSheet(
            "color: #FF8C00; font-size: 11px; font-weight: 600;"
            " border: none; background: transparent;"
        )
        self._edit_label.setVisible(False)
        b_lyt.addWidget(self._edit_label)

        b_lyt.addStretch()

        self._add_fab = QPushButton()
        self._add_fab.setFixedSize(FAB_SIZE, FAB_SIZE)
        self._add_fab.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_fab.clicked.connect(self._add_fab_clicked)
        b_lyt.addWidget(self._add_fab)

        root.addWidget(self._bottom)

        # ---- 追加モードオーバーレイ（central全体を覆う） ----
        self._add_overlay = AddModeOverlay(central)
        self._add_overlay.folder_dropped.connect(self._on_folder_dropped_for_add)
        self._add_overlay.close_requested.connect(self._exit_add_mode)
        self._add_overlay.hide()

        # リサイズグリップ（フレームレスウィンドウ用）
        self._grip = QSizeGrip(central)
        self._grip.setFixedSize(16, 16)
        self._grip.setStyleSheet("QSizeGrip { background: transparent; }")

        self._apply_mode_ui()
        self._rebuild_tiles()

    def _fab_ss(self, bg: str, hover: str) -> str:
        r = FAB_SIZE // 2
        return (
            f"QPushButton {{ background: {bg}; border-radius: {r}px; border: none; }}"
            f"QPushButton:hover {{ background: {hover}; }}"
            f"QPushButton:pressed {{ background: #555555; }}"
        )

    def _apply_mode_ui(self):
        if self._in_add_mode:
            # FABはオーバーレイ下に隠れるので通常状態のまま
            edit_kind, edit_bg, edit_hov = "pencil", "#2D2D2D", "#444444"
            add_kind, add_bg, add_hov = "plus", "#2D2D2D", "#444444"
            self._edit_fab.setEnabled(True)
        elif self._in_edit_mode:
            edit_kind, edit_bg, edit_hov = "pencil", "#FF8C00", "#E07000"
            add_kind, add_bg, add_hov = "plus", "#2D2D2D", "#444444"
            self._edit_fab.setEnabled(True)
        else:
            edit_kind, edit_bg, edit_hov = "pencil", "#2D2D2D", "#444444"
            add_kind, add_bg, add_hov = "plus", "#2D2D2D", "#444444"
            self._edit_fab.setEnabled(True)

        icon_sz = QSize(FAB_SIZE - 12, FAB_SIZE - 12)

        self._edit_fab.setIcon(_fab_symbol_icon(edit_kind))
        self._edit_fab.setIconSize(icon_sz)
        self._edit_fab.setStyleSheet(self._fab_ss(edit_bg, edit_hov))

        self._add_fab.setIcon(_fab_symbol_icon(add_kind))
        self._add_fab.setIconSize(icon_sz)
        self._add_fab.setStyleSheet(self._fab_ss(add_bg, add_hov))

        bg = BG_EDIT if self._in_edit_mode else BG_NORMAL
        for widget in (self._central, self._bottom):
            pal = widget.palette()
            pal.setColor(QPalette.ColorRole.Window, QColor(bg))
            widget.setPalette(pal)

        self._edit_label.setVisible(self._in_edit_mode)

        if self._grid:
            self._grid.set_bg(bg)

    def _sorted_folders(self) -> list:
        return sorted(
            self.settings["folders"],
            key=lambda e: e.get("click_count", 0) + e.get("move_count", 0),
            reverse=True,
        )

    def _rebuild_tiles(self):
        folders = self._sorted_folders()
        self._tiles = []
        tiles_move = []   # allow_filemove=True  → 上セクション
        tiles_link = []   # allow_filemove=False → 下セクション

        for entry in folders:
            tile = FolderTile(entry)
            tile.edit_requested.connect(lambda e=entry: self._edit_tile(e))
            tile.folder_opened.connect(lambda e=entry: self._on_click(e))
            tile.files_dropped.connect(lambda paths, e=entry: self._on_drop(paths, e))
            self._tiles.append(tile)
            if entry.get("allow_filemove", True):
                tiles_move.append(tile)
            else:
                tiles_link.append(tile)

        bg = BG_EDIT if self._in_edit_mode else BG_NORMAL
        self._grid = TileGrid(
            tiles_move, tiles_link, bg,
            "右下の [+] ボタンからフォルダを追加してください"
        )
        self._container.set_grid(self._grid)

        for tile in self._tiles:
            tile.set_edit_mode(self._in_edit_mode)

    def _edit_fab_clicked(self):
        if self._in_add_mode:
            self._exit_add_mode()
        elif self._in_edit_mode:
            self._exit_edit_mode()
        else:
            self._enter_edit_mode()

    def _add_fab_clicked(self):
        if self._in_add_mode:
            self._exit_add_mode()
        else:
            if self._in_edit_mode:
                self._exit_edit_mode()
            self._enter_add_mode()

    def _enter_edit_mode(self):
        self._in_edit_mode = True
        for tile in self._tiles:
            tile.set_edit_mode(True)
        self._apply_mode_ui()

    def _exit_edit_mode(self):
        self._in_edit_mode = False
        for tile in self._tiles:
            tile.set_edit_mode(False)
        self._apply_mode_ui()

    def _enter_add_mode(self):
        self._in_add_mode = True
        self._add_overlay.setGeometry(self._central.rect())
        self._add_overlay.show()
        self._add_overlay.raise_()
        self._apply_mode_ui()

    def _exit_add_mode(self):
        self._in_add_mode = False
        self._add_overlay.hide()
        self._apply_mode_ui()

    def _edit_tile(self, entry: dict):
        dlg = FolderEditDialog(entry=entry, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            result = dlg.result_entry
            result["click_count"] = entry.get("click_count", 0)
            result["move_count"] = entry.get("move_count", 0)
            idx = next(
                (i for i, e in enumerate(self.settings["folders"])
                 if e.get("path") == entry.get("path")),
                -1,
            )
            if idx >= 0:
                self.settings["folders"][idx] = result
                save_settings(self.settings)
                self._rebuild_tiles()

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

    def _on_folder_dropped_for_add(self, path: str):
        entry = {"path": path, "name": "", "use_date_folder": True, "allow_filemove": True}
        dlg = FolderEditDialog(entry=entry, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_entry:
            result = dlg.result_entry
            result["click_count"] = 0
            result["move_count"] = 0
            self.settings["folders"].append(result)
            save_settings(self.settings)
            self._rebuild_tiles()
            self._exit_add_mode()

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, parent=self)
        dlg.exec()
        self._rebuild_tiles()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_grip"):
            c = self.centralWidget()
            if c:
                self._grip.move(c.width() - 16, c.height() - 16)
                self._grip.raise_()
        if hasattr(self, "_add_overlay") and self._add_overlay.isVisible():
            self._add_overlay.setGeometry(self._central.rect())
            self._add_overlay.raise_()

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
            ctypes.byref(ctypes.c_uint(colorref)), ctypes.sizeof(ctypes.c_uint),
        )
    except Exception:
        pass


# ---- エントリポイント -------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app.setStyleSheet("""
        QLineEdit  { background-color: #FFFFFF; }
        QListWidget { background-color: #FFFFFF; }
        QCheckBox { color: #1A1A1A; }
        QCheckBox::indicator {
            width: 14px; height: 14px;
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
    menu.addAction("設定").triggered.connect(window._open_settings)
    menu.addSeparator()
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
