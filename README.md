# txt2epub-desktop

一个离线的 Windows 桌面工具，用于将 TXT 小说快速整理并导出为 EPUB3。

- 拖拽/选择 TXT 文件并后台加载
- 自动识别多级目录（可编辑）
- 规则系统支持纯正则“匹配 => 替换”
- 导出前可填写 EPUB 元数据（标题、作者、类型、封面等）
- 无网络依赖，适合本地批量整理小说文本

## 功能亮点

- **TXT 预处理**：自动识别 UTF-8/GBK，统一换行，去除 BOM 与首尾空行。
- **目录识别**：支持多级目录（如卷/章/节），并可在 UI 中手动增删改。
- **规则可配置**：每个级别独立维护正则规则，格式为：
  - `正则匹配 => 正则替换`
  - 例如：`^第([0-9一二三四五六七八九十百千万两]+)章[\s:：-]*(.*)$ => 第\1章 \2`
- **规则测试**：可对正文选中行执行测试，查看命中级别、命中规则和输出标题。
- **EPUB 导出**：支持目录、spine、nav、样式、封面、作者、类型等元信息。
- **封面策略**：可选自定义图片；不提供时自动生成简洁封面（含书名）。

## 环境要求

- Python 3.11+
- Windows（当前 UI 与打包目标为 Windows）

## 安装

```bash
pip install -r requirements.txt
```

## 启动

```bash
python app/main.py
```

## 使用流程

1. 启动应用并拖入/选择 `.txt` 文件。
2. 等待加载与初步目录识别完成。
3. 在左侧目录树中编辑目录结构或标题。
4. 在右侧规则区调整正则规则并点击“重新识别目录”。
5. 点击“测试选中行”验证某一行的识别结果。
6. 点击“生成 EPUB”，先填写元数据，再选择保存路径。

## 规则说明（纯正则）

每条规则一行，格式如下：

```text
<regex_pattern> => <replacement>
```

说明：

- `regex_pattern` 使用 Python `re` 语法。
- `replacement` 使用 Python `re` 替换语法（如 `\1`、`\g<1>`、`\g<0>`）。
- 若不写 `=> replacement`，默认替换为整段匹配（`\g<0>`）。

示例：

```text
^([零一二三四五六七八九十]+)、\s*(.*)$ => 第\1章 \2
^第([0-9一二三四五六七八九十百千万两]+)章[\s:：-]*(.*)$ => 第\1章 \2
^(?:Chapter|CHAPTER)\s+([IVXLCDM\d]+)[\s:：-]*(.*)$ => Chapter \1 \2
```

## 导出元数据

导出 EPUB 时可填写：

- 标题
- 作者
- 页数（自动估算）
- 类型（多选，支持新增/删除）
- 封面（可选本地图片）

## 打包（PyInstaller）

```bash
pyinstaller --onefile --windowed app/main.py
```

输出路径：

```text
dist/main.exe
```

## 项目结构

```text
app/
├── main.py                # 程序入口
├── ui_mainwindow.py       # 主窗口与页面结构
├── controller.py          # UI 事件与业务编排
├── metadata_dialog.py     # 导出元数据对话框
├── core/
│   ├── txt_loader.py      # TXT 加载与编码处理
│   ├── chapter_parser.py  # 目录规则编译与识别
│   ├── epub_builder.py    # EPUB 构建与封面处理
│   ├── models.py          # 数据模型
│   └── utils.py           # 工具函数
└── resources/
    └── default_cover.jpg
```

## 常见问题

- **规则测试命中但重识别结果不一致？**
  - 当前版本测试与重识别已统一同一判定逻辑；请确认已保存当前级别规则后再重识别。
- **中文乱码？**
  - 工具已自动检测 UTF-8/GBK。若原始文本编码异常，请先用编辑器转换编码再导入。

## Roadmap

- 目录拖拽重排
- 批量转换
- 更丰富的主题封面模板
- 基础自动化测试与 CI

## License

[MIT](./LICENSE)
