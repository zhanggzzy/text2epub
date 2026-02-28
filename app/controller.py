from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu, QMessageBox, QProgressDialog, QTreeWidgetItem

from app.core.chapter_parser import (
    check_line_for_toc,
    compile_rule_levels,
    default_rule_levels,
    parse_toc_items,
    recompute_ranges,
)
from app.core.epub_builder import build_epub
from app.core.models import RuleLevel, TocItem
from app.core.txt_loader import load_txt_lines
from app.core.utils import normalize_title
from app.metadata_dialog import MetadataDialog
from app.ui_mainwindow import AppState, MainWindow


class TxtLoadWorker(QObject):
    progress_updated = Signal(int)
    load_finished = Signal(list)
    load_failed = Signal(str)

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self.file_path = file_path

    def run(self) -> None:
        try:
            lines = load_txt_lines(self.file_path, progress_callback=lambda value: self.progress_updated.emit(value))
            self.load_finished.emit(lines)
        except Exception as exc:  # noqa: BLE001
            self.load_failed.emit(str(exc))


class AppController(QObject):
    def __init__(self, window: MainWindow) -> None:
        super().__init__()
        self.window = window
        self.lines: list[str] = []
        self.toc_items: list[TocItem] = []
        self.rule_levels: list[RuleLevel] = default_rule_levels()
        self.current_file_path: str = ""
        self.unsaved_changes = False

        self.load_thread: QThread | None = None
        self.load_worker: TxtLoadWorker | None = None
        self._rule_ui_loading = False

        self._bind_events()
        self._load_rule_levels_to_ui()
        self._set_editing_controls_enabled(False)

    def _bind_events(self) -> None:
        self.window.btn_choose_file.clicked.connect(self.choose_txt_file)
        self.window.txt_file_dropped.connect(self.handle_dropped_file)
        self.window.escape_pressed.connect(self.on_escape_pressed)
        self.window.window_close_requested.connect(self.on_close_requested)

        self.window.btn_reparse.clicked.connect(self.reparse_toc)
        self.window.btn_add_chapter.clicked.connect(self.add_toc_item_from_cursor)
        self.window.btn_delete_chapter.clicked.connect(self.delete_selected_toc_item)
        self.window.btn_move_up.clicked.connect(lambda: self.swap_selected_title(-1))
        self.window.btn_move_down.clicked.connect(lambda: self.swap_selected_title(1))
        self.window.btn_generate_epub.clicked.connect(self.generate_epub)
        self.window.btn_back_home.clicked.connect(self.back_to_home)

        self.window.toc_tree.itemChanged.connect(self.on_toc_title_changed)
        self.window.toc_tree.itemSelectionChanged.connect(self.highlight_selected_toc_in_preview)
        self.window.toc_tree.customContextMenuRequested.connect(self.show_toc_context_menu)

        self.window.rule_level_list.currentRowChanged.connect(self.on_rule_level_selected)
        self.window.btn_add_level.clicked.connect(self.add_rule_level)
        self.window.btn_remove_level.clicked.connect(self.remove_rule_level)
        self.window.btn_save_rule_level.clicked.connect(self.save_current_rule_level)
        self.window.btn_test_selected_line.clicked.connect(self.test_selected_line)

    def _load_rule_levels_to_ui(self) -> None:
        self._rule_ui_loading = True
        self.window.rule_level_list.clear()
        for idx, level in enumerate(self.rule_levels, start=1):
            self.window.rule_level_list.addItem(f"L{idx}: {level.name}")
        if self.rule_levels:
            self.window.rule_level_list.setCurrentRow(0)
            self._fill_rule_editor(0)
        else:
            self.window.rule_level_name_edit.clear()
            self.window.rule_text_edit.clear()
        self._rule_ui_loading = False

    def _fill_rule_editor(self, index: int) -> None:
        if index < 0 or index >= len(self.rule_levels):
            self.window.rule_level_name_edit.clear()
            self.window.rule_text_edit.clear()
            return
        level = self.rule_levels[index]
        self.window.rule_level_name_edit.setText(level.name)
        self.window.rule_text_edit.setPlainText("\n".join(level.rules))

    def on_rule_level_selected(self, index: int) -> None:
        if self._rule_ui_loading:
            return
        self._fill_rule_editor(index)

    def add_rule_level(self) -> None:
        if not self._try_save_current_rule_level(show_message=True):
            return
        next_no = len(self.rule_levels) + 1
        self.rule_levels.append(
            RuleLevel(
                name=f"级别{next_no}",
                rules=[r"^第([0-9一二三四五六七八九十百千万两]+)章[\s:：-]*(.*)$ => 第\1章 \2"],
            )
        )
        self._load_rule_levels_to_ui()
        self.window.rule_level_list.setCurrentRow(next_no - 1)
        self.unsaved_changes = True

    def remove_rule_level(self) -> None:
        if len(self.rule_levels) <= 1:
            QMessageBox.warning(self.window, "操作受限", "至少保留一个级别。")
            return
        index = self.window.rule_level_list.currentRow()
        if index < 0 or index >= len(self.rule_levels):
            return
        self.rule_levels.pop(index)
        self._load_rule_levels_to_ui()
        self.unsaved_changes = True

    def _try_save_current_rule_level(self, show_message: bool = False) -> bool:
        index = self.window.rule_level_list.currentRow()
        if index < 0 or index >= len(self.rule_levels):
            return True
        name = normalize_title(self.window.rule_level_name_edit.text(), f"级别{index + 1}")
        rules = [line.strip() for line in self.window.rule_text_edit.toPlainText().splitlines() if line.strip()]
        if not rules:
            QMessageBox.warning(self.window, "规则为空", "每个级别至少需要一条规则。")
            return False
        try:
            compile_rule_levels([RuleLevel(name=name, rules=rules)])
        except re.error as exc:
            QMessageBox.critical(self.window, "规则错误", f"正则编译失败：{exc}")
            return False
        except ValueError as exc:
            QMessageBox.critical(self.window, "规则错误", str(exc))
            return False

        self.rule_levels[index] = RuleLevel(name=name, rules=rules)
        self._load_rule_levels_to_ui()
        self.window.rule_level_list.setCurrentRow(index)
        self.unsaved_changes = True
        if show_message:
            QMessageBox.information(self.window, "已保存", "当前级别规则已保存。")
        return True

    def save_current_rule_level(self) -> None:
        self._try_save_current_rule_level(show_message=False)

    def choose_txt_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self.window, "选择 TXT 文件", "", "Text Files (*.txt)")
        if file_path:
            self.start_load(file_path)

    def handle_dropped_file(self, file_path: str) -> None:
        if not file_path.lower().endswith(".txt"):
            QMessageBox.warning(self.window, "文件类型错误", "仅支持 TXT 文件。")
            return
        self.start_load(file_path)

    def start_load(self, file_path: str) -> None:
        if not file_path.lower().endswith(".txt"):
            QMessageBox.warning(self.window, "文件类型错误", "仅支持 TXT 文件。")
            return

        self.current_file_path = file_path
        self.window.progress_bar.setValue(0)
        self.window.set_loading_file_name(Path(file_path).name)
        self.window.set_state(AppState.LOADING)
        self._set_editing_controls_enabled(False)

        self.load_thread = QThread()
        self.load_worker = TxtLoadWorker(file_path)
        self.load_worker.moveToThread(self.load_thread)
        self.load_thread.started.connect(self.load_worker.run)
        self.load_worker.progress_updated.connect(self.window.progress_bar.setValue)
        self.load_worker.load_finished.connect(self._on_load_finished)
        self.load_worker.load_failed.connect(self._on_load_failed)
        self.load_worker.load_finished.connect(self.load_thread.quit)
        self.load_worker.load_failed.connect(self.load_thread.quit)
        self.load_thread.finished.connect(self._cleanup_load_thread)
        self.load_thread.start()

    def _cleanup_load_thread(self) -> None:
        if self.load_worker:
            self.load_worker.deleteLater()
            self.load_worker = None
        if self.load_thread:
            self.load_thread.deleteLater()
            self.load_thread = None

    def _on_load_finished(self, lines: list[str]) -> None:
        self.lines = lines
        self.unsaved_changes = False
        self.window.preview_text.setPlainText(self._format_preview_text(lines))
        self.reparse_toc(set_unsaved=False)
        self.window.set_state(AppState.EDITING)
        self._set_editing_controls_enabled(True)

    def _on_load_failed(self, message: str) -> None:
        self.window.set_state(AppState.START)
        QMessageBox.critical(self.window, "加载失败", message)

    def _format_preview_text(self, lines: list[str]) -> str:
        return "\n".join(f"{i + 1:06d} | {line}" for i, line in enumerate(lines))

    def reparse_toc(self, set_unsaved: bool = True) -> None:
        if not self._try_save_current_rule_level(show_message=False):
            return
        self.toc_items = parse_toc_items(self.lines, self.rule_levels)
        self._refresh_toc_tree()
        if set_unsaved:
            self.unsaved_changes = True

    def _refresh_toc_tree(self) -> None:
        self.window.toc_tree.blockSignals(True)
        self.window.toc_tree.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []

        for idx, item in enumerate(self.toc_items):
            while stack and stack[-1][0] >= item.level:
                stack.pop()
            parent = stack[-1][1] if stack else None
            range_text = f"{item.start_line + 1}-{item.end_line + 1}"
            display = f"[L{item.level} {item.level_name}] {item.title}"
            node = self.window.add_toc_item(parent, display, range_text, idx)
            stack.append((item.level, node))

        self.window.toc_tree.blockSignals(False)
        self.window.toc_tree.expandAll()
        if self.window.toc_tree.topLevelItemCount() > 0:
            self.window.toc_tree.setCurrentItem(self.window.toc_tree.topLevelItem(0))

    def _selected_flat_index(self) -> int:
        node = self.window.toc_tree.currentItem()
        if node is None:
            return -1
        value = node.data(0, Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else -1

    def _set_editing_controls_enabled(self, enabled: bool) -> None:
        for button in (
            self.window.btn_reparse,
            self.window.btn_add_chapter,
            self.window.btn_delete_chapter,
            self.window.btn_move_up,
            self.window.btn_move_down,
            self.window.btn_generate_epub,
            self.window.btn_add_level,
            self.window.btn_remove_level,
            self.window.btn_save_rule_level,
            self.window.btn_test_selected_line,
        ):
            button.setEnabled(enabled)
        self.window.toc_tree.setEnabled(enabled)
        self.window.rule_level_list.setEnabled(enabled)
        self.window.rule_level_name_edit.setEnabled(enabled)
        self.window.rule_text_edit.setEnabled(enabled)

    def on_toc_title_changed(self, node: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        idx = node.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        flat_index = int(idx)
        if flat_index < 0 or flat_index >= len(self.toc_items):
            return
        text = re.sub(r"^\[L\d+\s+[^\]]+\]\s*", "", node.text(0).strip())
        fallback = f"{self.toc_items[flat_index].level_name}{flat_index + 1}"
        self.toc_items[flat_index].title = normalize_title(text, fallback)
        self.unsaved_changes = True
        self._refresh_toc_tree()

    def highlight_selected_toc_in_preview(self) -> None:
        row = self._selected_flat_index()
        if row < 0 or row >= len(self.toc_items):
            return
        block_num = self.toc_items[row].start_line
        cursor = self.window.preview_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.MoveAnchor, block_num)
        self.window.preview_text.setTextCursor(cursor)
        self.window.preview_text.centerCursor()

    def test_selected_line(self) -> None:
        if not self.lines:
            self.window.rule_test_result.setText("测试结果：未加载文本")
            return
        if not self._try_save_current_rule_level(show_message=False):
            return
        compiled = compile_rule_levels(self.rule_levels)
        if not compiled:
            self.window.rule_test_result.setText("测试结果：当前规则为空")
            return

        line_no = self.window.preview_text.textCursor().blockNumber()
        line_no = max(0, min(line_no, len(self.lines) - 1))
        line = self.lines[line_no]
        checked = check_line_for_toc(line, compiled)
        if not checked.accepted or checked.matched is None:
            self.window.rule_test_result.setText(f"测试结果：第 {line_no + 1} 行未被纳入目录（{checked.reason}）")
            return
        matched = checked.matched
        self.window.rule_test_result.setText(
            f"测试结果：第 {line_no + 1} 行 -> L{matched.level_no}（{matched.level_name}），输出标题：{matched.rendered_title}，规则：{matched.rule.raw_rule}"
        )

    def add_toc_item_from_cursor(self) -> None:
        if not self.lines:
            return
        if not self._try_save_current_rule_level(show_message=False):
            return
        level_choices = [f"L{idx + 1} - {level.name}" for idx, level in enumerate(self.rule_levels)]
        choice, ok = QInputDialog.getItem(self.window, "目录级别", "请选择目录类型：", level_choices, editable=False)
        if not ok:
            return
        level_index = level_choices.index(choice)
        level_no = level_index + 1
        level_name = self.rule_levels[level_index].name

        cursor = self.window.preview_text.textCursor()
        start_line = max(0, min(cursor.blockNumber(), len(self.lines) - 1))
        default_title = f"{level_name}{len([i for i in self.toc_items if i.level == level_no]) + 1}"
        title, ok = QInputDialog.getText(self.window, "添加目录项", f"请输入从第 {start_line + 1} 行开始的目录标题：", text=default_title)
        if not ok:
            return

        self.toc_items.append(
            TocItem(
                title=normalize_title(title, default_title),
                start_line=start_line,
                end_line=len(self.lines) - 1,
                level=level_no,
                level_name=level_name,
            )
        )
        self.toc_items = recompute_ranges(self.toc_items, len(self.lines))
        self._refresh_toc_tree()
        self.unsaved_changes = True

    def delete_selected_toc_item(self) -> None:
        idx = self._selected_flat_index()
        if idx < 0 or idx >= len(self.toc_items):
            QMessageBox.information(self.window, "提示", "请先选择要删除的目录项。")
            return
        if len(self.toc_items) <= 1:
            QMessageBox.warning(self.window, "操作受限", "至少保留一个目录项。")
            return
        self.toc_items.pop(idx)
        self.toc_items = recompute_ranges(self.toc_items, len(self.lines))
        self._refresh_toc_tree()
        self.unsaved_changes = True

    def swap_selected_title(self, direction: int) -> None:
        idx = self._selected_flat_index()
        target = idx + direction
        if idx < 0 or target < 0 or target >= len(self.toc_items):
            return
        if self.toc_items[idx].level != self.toc_items[target].level:
            QMessageBox.information(self.window, "提示", "仅支持在相同层级间上移/下移。")
            return
        self.toc_items[idx].title, self.toc_items[target].title = self.toc_items[target].title, self.toc_items[idx].title
        self._refresh_toc_tree()
        self.unsaved_changes = True

    def show_toc_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        node = self.window.toc_tree.itemAt(pos)
        if node is None:
            return
        menu = QMenu(self.window.toc_tree)
        action_rename = QAction("重命名", menu)
        action_delete = QAction("删除", menu)
        action_rename.triggered.connect(lambda: self.window.toc_tree.editItem(node, 0))
        action_delete.triggered.connect(self.delete_selected_toc_item)
        menu.addAction(action_rename)
        menu.addAction(action_delete)
        menu.exec(self.window.toc_tree.mapToGlobal(pos))

    def generate_epub(self) -> None:
        if not self.lines:
            QMessageBox.warning(self.window, "无法生成", "未加载文本内容。")
            return
        if not self.toc_items:
            QMessageBox.warning(self.window, "无法生成", "没有可用目录项。")
            return

        default_name = Path(self.current_file_path).stem if self.current_file_path else "output"
        meta_dialog = MetadataDialog(self.window, default_title=default_name, lines=self.lines)
        if meta_dialog.exec() != MetadataDialog.DialogCode.Accepted:
            return
        metadata = meta_dialog.get_metadata()

        output_path, _ = QFileDialog.getSaveFileName(self.window, "保存 EPUB", f"{default_name}.epub", "EPUB Files (*.epub)")
        if not output_path:
            return

        progress = QProgressDialog("正在生成 EPUB...", "", 0, 0, self.window)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.show()
        try:
            build_epub(lines=self.lines, toc_items=self.toc_items, output_path=output_path, metadata=metadata, language="zh")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self.window, "生成失败", str(exc))
        else:
            self.unsaved_changes = False
            QMessageBox.information(self.window, "完成", f"EPUB 已生成：\n{output_path}")
        finally:
            progress.close()

    def on_escape_pressed(self) -> None:
        if self.window.state != AppState.START:
            self.back_to_home()

    def back_to_home(self) -> None:
        if self.unsaved_changes:
            result = QMessageBox.question(
                self.window,
                "返回首页",
                "当前有未保存变更，确认返回首页吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result != QMessageBox.StandardButton.Yes:
                return
        self.window.set_state(AppState.START)
        self._set_editing_controls_enabled(False)

    def on_close_requested(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self.unsaved_changes:
            event.accept()
            return
        result = QMessageBox.question(
            self.window,
            "确认退出",
            "存在未保存变更，确定要退出吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()
