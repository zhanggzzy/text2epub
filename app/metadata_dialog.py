from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.core.models import EpubMetadata


def estimate_pages(lines: list[str]) -> int:
    total_chars = sum(len(line.strip()) for line in lines if line.strip())
    if total_chars <= 0:
        return 1
    return max(1, (total_chars + 799) // 800)


class MetadataDialog(QDialog):
    def __init__(self, parent, default_title: str, lines: list[str]) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("EPUB 元数据")
        self.setModal(True)
        self.resize(520, 520)

        self.cover_path: str | None = None
        self.page_count = estimate_pages(lines)

        root = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit(default_title)
        self.author_edit = QLineEdit()
        self.page_label = QLabel(str(self.page_count))
        self.page_label.setStyleSheet("font-weight: 600;")

        form.addRow("标题:", self.title_edit)
        form.addRow("作者:", self.author_edit)
        form.addRow("页数(自动):", self.page_label)
        root.addLayout(form)

        root.addWidget(QLabel("类型（可多选，可新增/删除）:"))
        self.type_list = QListWidget()
        self.type_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for text in ["小说", "长篇", "中文", "虚构"]:
            self._add_type_item(text, checked=True)
        root.addWidget(self.type_list)

        type_actions = QHBoxLayout()
        self.btn_add_type = QPushButton("新增类型")
        self.btn_remove_type = QPushButton("删除选中类型")
        type_actions.addWidget(self.btn_add_type)
        type_actions.addWidget(self.btn_remove_type)
        root.addLayout(type_actions)

        root.addWidget(QLabel("封面:"))
        cover_row = QHBoxLayout()
        self.cover_label = QLabel("未选择（将自动生成简洁封面）")
        self.cover_label.setWordWrap(True)
        self.btn_choose_cover = QPushButton("选择图片")
        self.btn_clear_cover = QPushButton("清除")
        cover_row.addWidget(self.cover_label, 1)
        cover_row.addWidget(self.btn_choose_cover)
        cover_row.addWidget(self.btn_clear_cover)
        root.addLayout(cover_row)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.btn_ok = QPushButton("下一步")
        self.btn_cancel = QPushButton("取消")
        actions.addWidget(self.btn_ok)
        actions.addWidget(self.btn_cancel)
        root.addLayout(actions)

        self.btn_add_type.clicked.connect(self.add_type)
        self.btn_remove_type.clicked.connect(self.remove_selected_types)
        self.btn_choose_cover.clicked.connect(self.choose_cover)
        self.btn_clear_cover.clicked.connect(self.clear_cover)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def _add_type_item(self, text: str, checked: bool) -> None:
        item = QListWidgetItem(text.strip())
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEditable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.type_list.addItem(item)

    def add_type(self) -> None:
        text, ok = QInputDialog.getText(self, "新增类型", "请输入类型名称：")
        if not ok:
            return
        value = text.strip()
        if not value:
            return
        for i in range(self.type_list.count()):
            if self.type_list.item(i).text().strip() == value:
                QMessageBox.information(self, "提示", "该类型已存在。")
                return
        self._add_type_item(value, checked=True)

    def remove_selected_types(self) -> None:
        rows = sorted({index.row() for index in self.type_list.selectedIndexes()}, reverse=True)
        for row in rows:
            self.type_list.takeItem(row)

    def choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图片",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.svg)",
        )
        if not path:
            return
        self.cover_path = path
        self.cover_label.setText(path)

    def clear_cover(self) -> None:
        self.cover_path = None
        self.cover_label.setText("未选择（将自动生成简洁封面）")

    def get_metadata(self) -> EpubMetadata:
        categories: list[str] = []
        for i in range(self.type_list.count()):
            item = self.type_list.item(i)
            if item.checkState() == Qt.CheckState.Checked and item.text().strip():
                categories.append(item.text().strip())
        return EpubMetadata(
            title=self.title_edit.text().strip(),
            author=self.author_edit.text().strip(),
            page_count=self.page_count,
            categories=categories,
            cover_path=self.cover_path,
        )

    def accept(self) -> None:
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "信息不完整", "标题不能为空。")
            return
        super().accept()
