from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class AppState(Enum):
    START = 1
    LOADING = 2
    EDITING = 3


class MainWindow(QMainWindow):
    txt_file_dropped = Signal(str)
    escape_pressed = Signal()
    window_close_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TXT to EPUB Converter")
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self.state = AppState.START

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.start_page = self._build_start_page()
        self.loading_page = self._build_loading_page()
        self.editing_page = self._build_editing_page()
        self.stack.addWidget(self.start_page)
        self.stack.addWidget(self.loading_page)
        self.stack.addWidget(self.editing_page)
        self.set_state(AppState.START)

    def _build_start_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("TXT to EPUB Converter")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 700;")

        self.drop_area = QFrame()
        self.drop_area.setFrameShape(QFrame.Shape.StyledPanel)
        self.drop_area.setMinimumSize(480, 240)
        self.drop_area.setStyleSheet(
            "QFrame { border: 2px dashed #7f8c8d; border-radius: 10px; background: #f7f9fb; }"
        )
        drop_layout = QVBoxLayout(self.drop_area)
        drop_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.setSpacing(12)
        drop_layout.addWidget(QLabel("拖入 TXT 文件到此区域"), alignment=Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(QLabel("或"), alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_choose_file = QPushButton("选择 TXT 文件")
        self.btn_choose_file.setMinimumWidth(200)
        drop_layout.addWidget(self.btn_choose_file, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(self.drop_area)
        return page

    def _build_loading_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        self.loading_label = QLabel("正在读取文件...")
        self.loading_label.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(420)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.loading_file_label = QLabel("文件名: -")

        layout.addWidget(self.loading_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_file_label, alignment=Qt.AlignmentFlag.AlignCenter)
        return page

    def _build_editing_page(self) -> QWidget:
        page = QWidget()
        root_layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("目录（多级）"))
        self.toc_tree = QTreeWidget()
        self.toc_tree.setHeaderLabels(["标题", "行范围"])
        self.toc_tree.setColumnWidth(0, 260)
        self.toc_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.toc_tree.setEditTriggers(QTreeWidget.EditTrigger.DoubleClicked)
        left_layout.addWidget(self.toc_tree)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.addWidget(QLabel("TXT 预览"))
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview_text.setStyleSheet("font-family: Consolas, 'Courier New', monospace;")
        center_layout.addWidget(self.preview_text)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.btn_reparse = QPushButton("重新识别目录")
        self.btn_add_chapter = QPushButton("添加目录项")
        self.btn_delete_chapter = QPushButton("删除目录项")
        self.btn_move_up = QPushButton("上移")
        self.btn_move_down = QPushButton("下移")
        self.btn_generate_epub = QPushButton("生成 EPUB")
        self.btn_back_home = QPushButton("返回首页")
        for btn in (
            self.btn_reparse,
            self.btn_add_chapter,
            self.btn_delete_chapter,
            self.btn_move_up,
            self.btn_move_down,
            self.btn_generate_epub,
            self.btn_back_home,
        ):
            btn.setMinimumHeight(32)
            right_layout.addWidget(btn)

        self.rule_box = QGroupBox("章节识别规则")
        rule_layout = QVBoxLayout(self.rule_box)

        rule_layout.addWidget(QLabel("级别列表（默认2级，可增减）"))
        self.rule_level_list = QListWidget()
        self.rule_level_list.setMinimumHeight(110)
        rule_layout.addWidget(self.rule_level_list)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("级别名称:"))
        self.rule_level_name_edit = QLineEdit()
        self.rule_level_name_edit.setPlaceholderText("例如：卷 / 章 / 节")
        name_row.addWidget(self.rule_level_name_edit)
        rule_layout.addLayout(name_row)

        rule_layout.addWidget(QLabel("规则（每行：正则匹配 => 正则替换；替换遵循 Python re 语法，如 \\1 / \\g<1>）"))
        self.rule_text_edit = QPlainTextEdit()
        self.rule_text_edit.setPlaceholderText(
            "示例：\n"
            "^([零一二三四五六七八九十]+)、\\s*(.*)$ => 第\\1章 \\2\n"
            "^第([0-9一二三四五六七八九十百千万两]+)章[\\s:：-]*(.*)$ => 第\\1章 \\2\n"
            "^(?:Chapter|CHAPTER)\\s+([IVXLCDM\\d]+)\\s*(.*)$ => Chapter \\1 \\2"
        )
        self.rule_text_edit.setMinimumHeight(160)
        rule_layout.addWidget(self.rule_text_edit)

        rule_btn_row = QHBoxLayout()
        self.btn_add_level = QPushButton("新增级别")
        self.btn_remove_level = QPushButton("删除级别")
        self.btn_save_rule_level = QPushButton("保存级别规则")
        rule_btn_row.addWidget(self.btn_add_level)
        rule_btn_row.addWidget(self.btn_remove_level)
        rule_btn_row.addWidget(self.btn_save_rule_level)
        rule_layout.addLayout(rule_btn_row)

        self.btn_test_selected_line = QPushButton("测试选中行")
        self.rule_test_result = QLabel("测试结果：-")
        self.rule_test_result.setWordWrap(True)
        rule_layout.addWidget(self.btn_test_selected_line)
        rule_layout.addWidget(self.rule_test_result)

        right_layout.addWidget(self.rule_box)
        right_layout.addStretch(1)

        splitter.addWidget(left_panel)
        splitter.addWidget(center_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([320, 650, 360])
        root_layout.addWidget(splitter)
        return page

    def set_state(self, state: AppState) -> None:
        self.state = state
        index = {AppState.START: 0, AppState.LOADING: 1, AppState.EDITING: 2}[state]
        self.stack.setCurrentIndex(index)

    def set_loading_file_name(self, file_name: str) -> None:
        self.loading_file_label.setText(f"文件名: {file_name}")

    def add_toc_item(self, parent: QTreeWidgetItem | None, title: str, range_text: str, flat_index: int) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title, range_text])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, Qt.ItemDataRole.UserRole, flat_index)
        if parent is None:
            self.toc_tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".txt"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self.txt_file_dropped.emit(urls[0].toLocalFile())
            event.acceptProposedAction()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.window_close_requested.emit(event)
