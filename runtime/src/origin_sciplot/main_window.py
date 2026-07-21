"""Single-window PySide6 GUI."""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QToolButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .project_paths import resources_dir
from .template_registry import TemplateManifest, TemplateRegistry, TemplateRegistryError
from .template_service import (
    PreparedTemplate,
    TemplateServiceError,
    TemplateServiceRegistry,
)
from .workers.process_launcher import build_worker_command
from .xps_workflow import XpsPreparation


OUTPUT_ROWS = (
    ("opju", "Origin 项目 (*.opju)", "result.opju"),
    ("png", "PNG 图像 (*.png)", "result.png"),
    ("pdf", "PDF 文件 (*.pdf)", "result.pdf"),
    ("tif", "TIFF 图像 (*.tif)", "result.tif"),
)

STAGE_PROGRESS = {
    "load_template": 12,
    "create_output_dir": 24,
    "validate_csv": 42,
    "launch_origin": 72,
    "export": 92,
}

ENERGY_KIND_LABELS = {
    "binding": "结合能",
    "kinetic": "动能",
    "unknown": "未知能量类型",
}

MODE_LABELS = {
    "scan": "扫描谱",
    "fit": "拟合谱",
    "fit_with_residual": "含残差拟合谱",
}

WARNING_LABELS = {
    "empty_rows_ignored": "已忽略全空数据行",
    "energy_kind_unknown": "未能确定结合能或动能",
    "spectrum_region_unknown": "未能确定谱区",
    "raw_series_missing": "未识别到原始计数列",
    "raw_role_inferred": "原始计数列按位置推断，请核对",
    "component_basis_unresolved": "分峰基线语义尚不确定，预览不填充峰面积",
    "scatter_density_medium": "散点较密，已同步减小预览和 Origin 符号",
    "scatter_density_high": "散点非常密，已同步使用更小符号",
    "series_count_high": "系列较多，建议检查颜色和图例可读性",
    "series_count_excessive": "系列超过 12 个，建议拆分或改用矩阵图",
    "category_count_high": "类别超过 20 个，建议筛选或改用水平条形/热图",
    "category_labels_long": "类别名称较长，建议使用水平条形图",
    "display_percent_normalized": "仅在显示层按行归一化为 100%，源数据未修改",
    "pie_category_count_high": "饼图类别超过 8 个，建议检查标签或改用条形图",
    "pie_category_count_excessive": "饼图类别超过 12 个，强烈建议改用条形图",
    "sankey_node_count_high": "桑基节点较多，建议检查标签可读性",
    "sankey_link_count_high": "桑基连接较多，建议拆分为多个流程图",
}


def _named_label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    return label


class CsvDropLineEdit(QLineEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setPlaceholderText("拖拽 CSV / TXT / XLS / XLSX 到这里，或点击右侧按钮选择")

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        urls = event.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"EditaPlot v{__version__}")
        self.resize(1360, 900)
        self.setMinimumSize(880, 640)
        self.registry = TemplateRegistry()
        self.template_services = TemplateServiceRegistry(self.registry)
        self.process: QProcess | None = None
        self.last_output_dir: Path | None = None
        self.xps_preparation: XpsPreparation | None = None
        self.prepared_template: PreparedTemplate | None = None
        self._mapping_role_combos: dict[str, QComboBox] = {}
        self._preview_pixmap: QPixmap | None = None
        self._stdout_buffer = b""
        self._run_started_at: float | None = None
        self._compact_mode: bool | None = None
        self._toolbar_buttons: list[QToolButton] = []
        self._build_ui()
        self._load_templates()
        self._apply_responsive_mode(force=True)
        self.statusBar().showMessage("就绪")

    def _build_ui(self) -> None:
        self._build_menus()

        central = QWidget()
        central.setObjectName("AppSurface")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        workspace = QFrame()
        workspace.setObjectName("Workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)
        workspace_layout.addWidget(self.menu_strip)
        workspace_layout.addWidget(self._build_toolbar())

        self.content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter.setObjectName("ContentSplitter")
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setHandleWidth(8)

        left_widget = QWidget()
        left_widget.setObjectName("ColumnSurface")
        left_column = QVBoxLayout(left_widget)
        left_column.setContentsMargins(14, 14, 8, 14)
        left_column.setSpacing(12)
        left_column.addWidget(self._build_input_panel())
        left_column.addWidget(self._build_template_panel())
        left_column.addWidget(self._build_log_panel(), 1)

        bottom_metrics = QHBoxLayout()
        bottom_metrics.setSpacing(12)
        bottom_metrics.addWidget(self._build_status_panel(), 3)
        bottom_metrics.addWidget(self._build_result_panel(), 2)
        left_column.addLayout(bottom_metrics)

        right_widget = QWidget()
        right_widget.setObjectName("ColumnSurface")
        right_column = QVBoxLayout(right_widget)
        right_column.setContentsMargins(8, 14, 16, 14)
        right_column.setSpacing(12)
        right_column.addWidget(self._build_preview_panel(), 1)
        right_column.addWidget(self._build_output_panel())

        self.left_scroll = self._column_scroll("LeftWorkspaceScroll", left_widget)
        self.right_scroll = self._column_scroll("RightWorkspaceScroll", right_widget)
        self.content_splitter.addWidget(self.left_scroll)
        self.content_splitter.addWidget(self.right_scroll)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        self.content_splitter.setSizes([760, 520])
        workspace_layout.addWidget(self.content_splitter, 1)

        root.addWidget(workspace, 1)
        self.setCentralWidget(central)

    def _column_scroll(self, object_name: str, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName(object_name)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(widget)
        return scroll

    def _build_menus(self) -> None:
        menu = QMenuBar()
        menu.setObjectName("MenuStrip")
        menu.setMinimumHeight(40)
        self.menu_strip = menu

        file_menu = menu.addMenu("文件(&F)")
        self.new_action = QAction("新建任务", self)
        self.new_action.triggered.connect(self._new_task)
        file_menu.addAction(self.new_action)

        self.choose_csv_action = QAction("选择数据文件...", self)
        self.choose_csv_action.triggered.connect(self._choose_csv)
        file_menu.addAction(self.choose_csv_action)

        self.open_output_action = QAction("打开输出文件夹", self)
        self.open_output_action.triggered.connect(self._open_output_dir)
        self.open_output_action.setEnabled(False)
        file_menu.addAction(self.open_output_action)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)

        edit_menu = menu.addMenu("编辑(&E)")
        self.clear_log_action = QAction("清空日志", self)
        self.clear_log_action.triggered.connect(self._clear_log)
        edit_menu.addAction(self.clear_log_action)

        view_menu = menu.addMenu("视图(&V)")
        view_menu.addAction("刷新预览", self._reanalyze_preview)

        tools_menu = menu.addMenu("工具(&T)")
        tools_menu.addAction("载入模板示例", self._open_example)

        help_menu = menu.addMenu("帮助(&H)")
        help_menu.addAction("关于", self._show_about)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(168)
        sidebar.setMaximumWidth(210)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setSpacing(20)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("BrandIcon")
        logo.setFixedSize(36, 36)
        icon_path = resources_dir() / "app_icon.png"
        if icon_path.is_file():
            logo_pixmap = QPixmap(str(icon_path)).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo.setPixmap(logo_pixmap)
        brand_text = QLabel("EDITA\nPLOT")
        brand_text.setObjectName("BrandText")
        brand.addWidget(logo)
        brand.addWidget(brand_text, 1)
        layout.addLayout(brand)

        layout.addSpacing(18)
        for index, title, subtitle, active in (
            ("1", "模板", "选择 Origin 模板", False),
            ("2", "输入", "加载科研数据文件", True),
            ("3", "运行", "处理并生成图形", False),
            ("4", "输出", "导出结果文件", False),
        ):
            layout.addWidget(self._build_step(index, title, subtitle, active))

        layout.addStretch(1)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        version = QLabel(f"v{__version__}")
        version.setObjectName("SidebarFooter")
        footer.addWidget(version)
        footer.addStretch(1)
        for text in ("设置", "信息"):
            label = QLabel(text[:1])
            label.setObjectName("SidebarRoundButton")
            label.setAlignment(Qt.AlignCenter)
            label.setToolTip(text)
            footer.addWidget(label)
        layout.addLayout(footer)
        return sidebar

    def _build_step(self, index: str, title: str, subtitle: str, active: bool) -> QWidget:
        row = QFrame()
        row.setObjectName("StepItemActive" if active else "StepItem")
        row.setMinimumHeight(78)
        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        badge = QLabel(index)
        badge.setObjectName("StepBadgeActive" if active else "StepBadge")
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignCenter)
        layout.addWidget(badge, 0, Qt.AlignTop)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("StepTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("StepSubtitle")
        subtitle_label.setWordWrap(True)
        text_box.addWidget(title_label)
        text_box.addWidget(subtitle_label)
        text_box.addStretch(1)
        layout.addLayout(text_box, 1)
        return row

    def _build_toolbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setObjectName("Toolbar")
        toolbar.setMinimumHeight(58)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(8)

        layout.addWidget(self._toolbar_button("新建任务", QStyle.SP_FileIcon, self._new_task))
        layout.addWidget(self._toolbar_button("选择数据", QStyle.SP_DirOpenIcon, self._choose_csv))
        layout.addWidget(self._toolbar_button("打开示例", QStyle.SP_DialogOpenButton, self._open_example))
        self.run_btn = self._toolbar_button(
            "运行", QStyle.SP_MediaPlay, self._start_worker, primary=True
        )
        layout.addWidget(self.run_btn)
        self.stop_btn = self._toolbar_button("停止", QStyle.SP_BrowserStop, self._stop_worker)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)

        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setObjectName("ToolbarSeparator")
        layout.addWidget(separator)

        layout.addWidget(self._toolbar_button("清空日志", QStyle.SP_DialogResetButton, self._clear_log))
        layout.addWidget(self._toolbar_button("打开输出", QStyle.SP_DirOpenIcon, self._open_output_dir))
        layout.addStretch(1)

        self.language_label = QLabel("界面语言")
        self.language_label.setObjectName("ToolbarMeta")
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("LanguageCombo")
        self.language_combo.addItem("简体中文")
        self.language_combo.setMinimumWidth(104)
        self.language_combo.setMaximumWidth(132)
        layout.addWidget(self.language_label)
        layout.addWidget(self.language_combo)
        return toolbar

    def _toolbar_button(
        self,
        text: str,
        icon: QStyle.StandardPixmap,
        slot,
        *,
        primary: bool = False,
    ) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setIcon(self.style().standardIcon(icon))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setObjectName("ToolbarPrimaryButton" if primary else "ToolbarButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(text)
        self._toolbar_buttons.append(button)
        if slot is not None:
            button.clicked.connect(slot)
        return button

    def _build_input_panel(self) -> QWidget:
        box = self._panel("输入数据（CSV / TXT / Excel）")
        box.setMinimumHeight(132)
        layout = QGridLayout(box)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        input_label = QLabel("数据文件：")
        input_label.setObjectName("FieldLabel")
        self.csv_path = CsvDropLineEdit()
        self.csv_path.textChanged.connect(self._update_file_info)

        browse_btn = QPushButton("浏览(B)...")
        browse_btn.setObjectName("SecondaryButton")
        browse_btn.clicked.connect(self._choose_csv)

        example_btn = QPushButton("打开样例")
        example_btn.setObjectName("GhostButton")
        example_btn.clicked.connect(self._open_example)

        self.file_info = QLabel("等待选择数据文件")
        self.file_info.setObjectName("InlineInfo")
        self.file_info.setWordWrap(True)

        self.keep_origin = QCheckBox("完成后保留 Origin 可编辑窗口")
        self.keep_origin.setObjectName("KeepOriginCheckBox")
        self.keep_origin.setChecked(True)
        self.keep_origin.setCursor(Qt.PointingHandCursor)
        self.keep_origin.setToolTip("勾选后任务完成时保留 Origin 窗口，便于继续手工编辑图页。")

        layout.addWidget(input_label, 0, 0)
        layout.addWidget(self.csv_path, 0, 1)
        layout.addWidget(browse_btn, 0, 2)
        layout.addWidget(example_btn, 0, 3)
        layout.addWidget(_named_label("文件信息：", "FieldLabel"), 1, 0)
        layout.addWidget(self.file_info, 1, 1, 1, 3)
        layout.addWidget(self.keep_origin, 2, 1, 1, 3)
        layout.setColumnStretch(1, 1)
        return box

    def _build_template_panel(self) -> QWidget:
        box = self._panel("模板与数据识别")
        box.setMinimumHeight(210)
        layout = QGridLayout(box)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        self.template_thumb = QLabel()
        self.template_thumb.setObjectName("TemplateThumb")
        self.template_thumb.setFixedSize(78, 78)
        self.template_thumb.setAlignment(Qt.AlignCenter)

        self.template_combo = QComboBox()
        self.template_combo.currentIndexChanged.connect(self._template_changed)
        self.template_combo.setEnabled(True)
        self.template_combo.setToolTip("选择通用科研模板；程序将按模板自动识别列角色和绘图 Profile。")

        self.edit_mapping_btn = QPushButton("检查/修改列映射")
        self.edit_mapping_btn.setObjectName("GhostButton")
        self.edit_mapping_btn.clicked.connect(self._edit_column_mapping)
        self.edit_mapping_btn.setVisible(False)

        self.template_details = QLabel()
        self.template_details.setWordWrap(True)
        self.template_details.setTextFormat(Qt.RichText)
        self.template_details.setObjectName("TemplateDetails")
        self.template_details.setMinimumHeight(112)

        layout.addWidget(self.template_thumb, 0, 0, 2, 1)
        layout.addWidget(_named_label("科研模板：", "FieldLabel"), 0, 1)
        layout.addWidget(self.template_combo, 0, 2)
        layout.addWidget(self.edit_mapping_btn, 0, 3)
        layout.addWidget(self.template_details, 1, 1, 1, 3)

        self.data_guide_panel = QFrame()
        self.data_guide_panel.setObjectName("DataGuidePanel")
        guide_layout = QVBoxLayout(self.data_guide_panel)
        guide_layout.setContentsMargins(10, 10, 10, 10)
        guide_layout.setSpacing(8)

        guide_header = QHBoxLayout()
        guide_header.setSpacing(8)
        guide_header.addWidget(_named_label("数据样例与格式：", "FieldLabel"))
        self.example_combo = QComboBox()
        self.example_combo.setObjectName("ExampleCombo")
        self.example_combo.currentIndexChanged.connect(self._update_example_description)
        guide_header.addWidget(self.example_combo, 1)
        self.open_example_btn = QPushButton("载入所选样例")
        self.open_example_btn.setObjectName("SecondaryButton")
        self.open_example_btn.clicked.connect(self._open_example)
        guide_header.addWidget(self.open_example_btn)
        self.save_blank_btn = QPushButton("另存空白模板")
        self.save_blank_btn.setObjectName("GhostButton")
        self.save_blank_btn.clicked.connect(self._save_blank_template)
        guide_header.addWidget(self.save_blank_btn)
        guide_layout.addLayout(guide_header)

        self.data_guide_label = QLabel()
        self.data_guide_label.setObjectName("DataGuideText")
        self.data_guide_label.setTextFormat(Qt.RichText)
        self.data_guide_label.setWordWrap(True)
        self.data_guide_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        guide_layout.addWidget(self.data_guide_label)
        layout.addWidget(self.data_guide_panel, 2, 0, 1, 4)

        self.mapping_panel = QFrame()
        self.mapping_panel.setObjectName("MappingPanel")
        mapping_layout = QVBoxLayout(self.mapping_panel)
        mapping_layout.setContentsMargins(10, 10, 10, 10)
        mapping_layout.setSpacing(8)

        mapping_header = QHBoxLayout()
        self.mapping_reason_label = QLabel()
        self.mapping_reason_label.setObjectName("InlineInfo")
        self.mapping_reason_label.setWordWrap(True)
        mapping_header.addWidget(self.mapping_reason_label, 1)
        self.mapping_context_label = _named_label("能量类型：", "FieldLabel")
        mapping_header.addWidget(self.mapping_context_label)
        self.mapping_energy_combo = QComboBox()
        mapping_header.addWidget(self.mapping_energy_combo)
        mapping_layout.addLayout(mapping_header)

        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["源数据列", "绘图角色"])
        self.mapping_table.verticalHeader().setVisible(False)
        self.mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.mapping_table.setMaximumHeight(190)
        mapping_layout.addWidget(self.mapping_table)

        mapping_actions = QHBoxLayout()
        mapping_actions.addStretch(1)
        self.confirm_mapping_btn = QPushButton("确认列映射并生成预览")
        self.confirm_mapping_btn.setObjectName("SecondaryButton")
        self.confirm_mapping_btn.clicked.connect(self._confirm_column_mapping)
        mapping_actions.addWidget(self.confirm_mapping_btn)
        mapping_layout.addLayout(mapping_actions)
        self.mapping_panel.setVisible(False)
        layout.addWidget(self.mapping_panel, 3, 0, 1, 4)
        layout.setColumnStretch(2, 1)
        return box

    def _build_log_panel(self) -> QWidget:
        box = self._panel("运行日志")
        box.setMinimumHeight(214)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setSpacing(8)

        log_top = QHBoxLayout()
        log_top.addWidget(_named_label("任务事件", "SectionHint"))
        log_top.addStretch(1)
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setObjectName("GhostButton")
        self.clear_log_btn.clicked.connect(self._clear_log)
        log_top.addWidget(self.clear_log_btn)

        self.log = QPlainTextEdit()
        self.log.setObjectName("RunLog")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(126)

        layout.addLayout(log_top)
        layout.addWidget(self.log, 1)
        return box

    def _build_preview_panel(self) -> QWidget:
        self.preview_panel = self._panel("真实数据预览（等待识别）")
        self.preview_panel.setMinimumHeight(420)
        layout = QVBoxLayout(self.preview_panel)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setSpacing(10)

        self.preview_label = QLabel("选择科研数据文件后生成与实际绘图规则一致的预览")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(320, 240)
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setScaledContents(False)
        self.preview_label.setObjectName("PreviewBox")

        controls = QHBoxLayout()
        controls.setSpacing(6)
        refresh_btn = self._icon_button("刷新预览", QStyle.SP_BrowserReload, self._reanalyze_preview)
        export_btn = QPushButton("导出预览(P)...")
        export_btn.setObjectName("SecondaryButton")
        export_btn.clicked.connect(self._export_preview)
        fit_btn = QPushButton("适应窗口")
        fit_btn.setObjectName("GhostButton")
        fit_btn.clicked.connect(self._refresh_preview)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        controls.addWidget(fit_btn)
        controls.addWidget(export_btn)

        layout.addWidget(self.preview_label, 1)
        layout.addLayout(controls)
        return self.preview_panel

    def _build_status_panel(self) -> QWidget:
        box = self._panel("运行状态")
        box.setMinimumHeight(138)
        layout = QGridLayout(box)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("StatusReady")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedSize(88, 32)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")

        self.elapsed_value = QLabel("--")
        self.elapsed_value.setObjectName("MetricValue")

        layout.addWidget(_named_label("状态：", "FieldLabel"), 0, 0)
        layout.addWidget(self.status_label, 0, 1)
        layout.addWidget(_named_label("进度：", "FieldLabel"), 1, 0)
        layout.addWidget(self.progress, 1, 1)
        layout.addWidget(_named_label("耗时：", "FieldLabel"), 2, 0)
        layout.addWidget(self.elapsed_value, 2, 1)
        layout.setColumnStretch(1, 1)
        return box

    def _build_result_panel(self) -> QWidget:
        box = self._panel("结果摘要")
        box.setMinimumHeight(138)
        layout = QGridLayout(box)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        self.result_values: dict[str, QLabel] = {}
        for row, (key, label, value) in enumerate(
            (
                ("rows", "数据点：", "--"),
                ("peaks", "系列数：", "--"),
                ("origin", "Origin：", "--"),
                ("verify", "轴校验：", "待运行"),
            )
        ):
            value_label = QLabel(value)
            value_label.setObjectName("MetricValue")
            self.result_values[key] = value_label
            layout.addWidget(_named_label(label, "FieldLabel"), row, 0)
            layout.addWidget(value_label, row, 1)
        layout.setColumnStretch(1, 1)
        return box

    def _build_output_panel(self) -> QWidget:
        box = self._panel("输出文件")
        box.setMinimumHeight(198)
        layout = QGridLayout(box)
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        layout.addWidget(_named_label("", "TableHeader"), 0, 0)
        layout.addWidget(_named_label("文件路径", "TableHeader"), 0, 2)
        layout.addWidget(_named_label("状态", "TableHeader"), 0, 3)

        self.output_path_labels: dict[str, QLabel] = {}
        self.output_state_labels: dict[str, QLabel] = {}
        for row, (key, label, filename) in enumerate(OUTPUT_ROWS, start=1):
            check = QCheckBox(label)
            check.setChecked(True)
            check.setEnabled(False)
            path_label = QLabel(filename)
            path_label.setObjectName("OutputPath")
            path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            state_label = QLabel("待生成")
            state_label.setObjectName("OutputPending")
            self.output_path_labels[key] = path_label
            self.output_state_labels[key] = state_label
            layout.addWidget(check, row, 0, 1, 2)
            layout.addWidget(path_label, row, 2)
            layout.addWidget(state_label, row, 3)

        button_row = QHBoxLayout()
        self.open_output_btn = QPushButton("打开输出文件夹(O)")
        self.open_output_btn.setObjectName("SecondaryButton")
        self.open_output_btn.setEnabled(False)
        self.open_output_btn.clicked.connect(self._open_output_dir)
        export_options_btn = QPushButton("全部导出选项(E)...")
        export_options_btn.setObjectName("GhostButton")
        export_options_btn.setEnabled(False)
        button_row.addWidget(self.open_output_btn)
        button_row.addWidget(export_options_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row, len(OUTPUT_ROWS) + 1, 0, 1, 4)
        layout.setColumnStretch(2, 1)
        return box

    def _panel(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setObjectName("Panel")
        return box

    def _icon_button(self, tooltip: str, icon: QStyle.StandardPixmap, slot) -> QToolButton:
        button = QToolButton()
        button.setObjectName("IconButton")
        button.setIcon(self.style().standardIcon(icon))
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def _load_templates(self) -> None:
        previous = self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for service in self.template_services.implemented():
            self.template_combo.addItem(service.manifest.name, service.manifest.id)
        self.template_combo.blockSignals(previous)
        self.template_details.setText(
            "<p style='margin:0; color:#526070;'>选择通用科研模板并上传数据。程序会自动识别"
            "列角色、坐标语义和绘图结构；低置信度数据需确认列映射后再预览。</p>"
        )
        self._update_manifest_guide()
        self._set_run_available(False)

    def _set_template_route(self, template_id: str | None) -> TemplateManifest | None:
        target = template_id or (str(self.template_combo.itemData(0)) if self.template_combo.count() else None)
        if target is None:
            return None
        index = self.template_combo.findData(target)
        if index >= 0:
            previous = self.template_combo.blockSignals(True)
            self.template_combo.setCurrentIndex(index)
            self.template_combo.blockSignals(previous)
        return self.registry.get(target)

    def _current_manifest(self) -> TemplateManifest:
        template_id = self.template_combo.currentData()
        if template_id is not None:
            return self.registry.get(str(template_id))
        implemented = self.registry.implemented()
        if not implemented:
            raise TemplateRegistryError("no implemented scientific template is available")
        return implemented[0]

    def _current_service(self):
        return self.template_services.get(self._current_manifest().id)

    def _template_changed(self) -> None:
        self._update_manifest_guide()
        if self.csv_path.text().strip():
            self._update_file_info()
            return
        self._update_template_details()

    def _update_manifest_guide(self) -> None:
        try:
            manifest = self._current_manifest()
        except TemplateRegistryError:
            self.example_combo.clear()
            self.data_guide_label.setText("暂无模板数据说明。")
            self.save_blank_btn.setEnabled(False)
            return

        previous = self.example_combo.blockSignals(True)
        self.example_combo.clear()
        for example in manifest.examples:
            self.example_combo.addItem(example.name, example.id)
            index = self.example_combo.count() - 1
            self.example_combo.setItemData(index, example.description, Qt.ToolTipRole)
        self.example_combo.blockSignals(previous)
        self.open_example_btn.setEnabled(bool(manifest.examples))
        self.save_blank_btn.setEnabled(
            manifest.blank_template_path is not None and manifest.blank_template_path.is_file()
        )
        self._update_example_description()

    def _selected_example(self):
        manifest = self._current_manifest()
        selected_id = self.example_combo.currentData()
        return next(
            (example for example in manifest.examples if example.id == selected_id),
            manifest.examples[0] if manifest.examples else None,
        )

    def _update_example_description(self) -> None:
        try:
            manifest = self._current_manifest()
        except TemplateRegistryError:
            return
        guide = manifest.data_guide
        example = self._selected_example()

        def joined(values: tuple[str, ...], fallback: str = "无") -> str:
            return "、".join(html.escape(value) for value in values) or fallback

        example_text = (
            f"<b>{html.escape(example.name)}</b>：{html.escape(example.description)}"
            if example is not None
            else "暂无内置样例"
        )
        notes = (
            "；".join(html.escape(item).rstrip("。；;") for item in guide.notes) + "。"
            if guide.notes
            else "按模板合同只读处理源文件。"
        )
        self.data_guide_label.setText(
            "<p style='margin:0 0 5px 0; color:#1f2937;'>"
            f"{html.escape(guide.headline)}</p>"
            "<p style='margin:0 0 4px 0; color:#526070;'>"
            f"必需：<span style='color:#111827;'>{joined(guide.required_columns)}</span>"
            f" &nbsp;·&nbsp; 可选：<span style='color:#111827;'>{joined(guide.optional_columns)}</span>"
            f" &nbsp;·&nbsp; 布局：<span style='color:#111827;'>{joined(guide.accepted_layouts, '矩形表格')}</span></p>"
            "<p style='margin:0 0 4px 0; color:#526070;'>"
            f"常见列名：<span style='color:#111827;'>{joined(guide.aliases, '参见数据合同')}</span></p>"
            "<p style='margin:0 0 4px 0; color:#526070;'>"
            f"当前样例：<span style='color:#111827;'>{example_text}</span></p>"
            f"<p style='margin:0; color:#526070;'>注意：{notes}</p>"
        )

    def _update_template_details(self) -> None:
        if self.prepared_template is None:
            return
        manifest = self._current_manifest()
        self._show_preparation_details(self.prepared_template, manifest)

    def _show_preparation_details(
        self, prepared: PreparedTemplate, manifest: TemplateManifest
    ) -> None:
        summary = prepared.summary
        outputs = " · ".join(html.escape(item.upper()) for item in manifest.outputs)
        roles_text = " &nbsp;·&nbsp; ".join(
            f"{html.escape(label)}=<span style='color:#111827;'>{html.escape(value)}</span>"
            for label, value in summary.roles
        )
        components = ", ".join(html.escape(item) for item in summary.components) or "无"
        warnings = "；".join(
            f"{html.escape(WARNING_LABELS.get(code, code))} ({html.escape(code)})"
            for code in summary.warnings
        ) or "无"
        facts = " &nbsp;·&nbsp; ".join(
            f"{html.escape(label)}：<span style='color:#111827;'>{html.escape(value)}</span>"
            for label, value in summary.facts
        )
        confirmation = (
            "<span style='color:#9b1c1c; font-weight:600;'>需要确认列映射</span>"
            if prepared.requires_confirmation
            else "<span style='color:#166534;'>可直接运行</span>"
        )
        self.template_details.setText(
            "<p style='margin:0 0 6px 0; color:#1f2937; font-weight:600;'>"
            f"{html.escape(summary.heading)}</p>"
            f"<p style='margin:0 0 5px 0; color:#526070;'>{facts}</p>"
            f"<p style='margin:0 0 5px 0; color:#526070;'>列角色：{roles_text}</p>"
            f"<p style='margin:0 0 5px 0; color:#526070;'>Series / Components "
            f"({len(summary.components)})：<span style='color:#111827;'>{components}</span></p>"
            f"<p style='margin:0 0 5px 0; color:#526070;'>置信度："
            f"<span style='color:#111827;'>{prepared.confidence:.0%}</span>"
            f" &nbsp;·&nbsp; {confirmation}"
            f" &nbsp;·&nbsp; 警告：<span style='color:#111827;'>{warnings}</span></p>"
            f"<p style='margin:0; color:#526070;'>绘图模板："
            f"<span style='color:#111827;'>{html.escape(manifest.id)}</span>"
            f" &nbsp;·&nbsp; Renderer：<span style='color:#111827;'>"
            f"{html.escape(prepared.renderer_template_id)}</span>"
            f" &nbsp;·&nbsp; 版本：<span style='color:#111827;'>{html.escape(manifest.version)}</span>"
            f" &nbsp;·&nbsp; 输出：<span style='color:#111827;'>{outputs}</span></p>"
        )

    def _set_data_preview(self, prepared: PreparedTemplate) -> None:
        png = self._current_service().render_preview(prepared)
        pixmap = QPixmap()
        if not pixmap.loadFromData(png, "PNG") or pixmap.isNull():
            raise TemplateServiceError(
                "preview_decode_error", "Generated scientific preview is not a valid PNG."
            )
        self._preview_pixmap = pixmap
        self.preview_label.setText("")
        self.preview_label.setToolTip(
            f"真实数据预览：{prepared.source_path}\n绘图计划：{prepared.plan_digest[:12]}"
        )
        self.template_thumb.setText("")
        self.template_thumb.setPixmap(
            pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.preview_panel.setTitle(f"真实数据预览（{prepared.summary.heading}）")
        self._refresh_preview()

    def _show_mapping_editor(self, prepared: PreparedTemplate) -> None:
        request = prepared.mapping_request
        if request is None:
            return
        reason_text = "、".join(WARNING_LABELS.get(reason, reason) for reason in request.reasons)
        self.mapping_reason_label.setText(
            "请确认每一列的绘图角色。" + (f" 原因：{reason_text}" if reason_text else "")
        )
        context_options = request.context_options or request.energy_kind_options
        context_value = request.context_value or request.energy_kind
        has_context = bool(context_options)
        self.mapping_context_label.setText(f"{request.context_label or '能量类型'}：")
        self.mapping_context_label.setVisible(has_context)
        self.mapping_energy_combo.setVisible(has_context)
        self.mapping_energy_combo.clear()
        for key, label in context_options:
            self.mapping_energy_combo.addItem(label, key)
        selected_energy = context_value or (context_options[0][0] if context_options else "")
        energy_index = self.mapping_energy_combo.findData(selected_energy)
        self.mapping_energy_combo.setCurrentIndex(max(energy_index, 0))

        suggestions = dict(request.suggested_roles)
        self.mapping_table.setRowCount(len(request.columns))
        self._mapping_role_combos.clear()
        for row, column in enumerate(request.columns):
            item = QTableWidgetItem(column)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.mapping_table.setItem(row, 0, item)
            combo = QComboBox()
            for option in request.role_options:
                combo.addItem(option.label, option.key)
            suggested_index = combo.findData(suggestions[column])
            combo.setCurrentIndex(max(suggested_index, 0))
            self.mapping_table.setCellWidget(row, 1, combo)
            self._mapping_role_combos[column] = combo
        self.mapping_panel.setVisible(True)
        self.edit_mapping_btn.setVisible(False)

    def _edit_column_mapping(self) -> None:
        if self.prepared_template is not None:
            self._show_mapping_editor(self.prepared_template)

    def _confirm_column_mapping(self) -> None:
        if self.prepared_template is None:
            return
        assignments = {
            column: str(combo.currentData()) for column, combo in self._mapping_role_combos.items()
        }
        try:
            confirmed = self._current_service().confirm_mapping(
                self.prepared_template,
                assignments=assignments,
                energy_kind=(
                    str(self.mapping_energy_combo.currentData())
                    if self.mapping_energy_combo.currentData() is not None
                    else ""
                ),
            )
            self._set_data_preview(confirmed)
        except TemplateServiceError as exc:
            self.statusBar().showMessage(f"列映射无效 [{exc.code}]：{exc}", 7000)
            self.mapping_reason_label.setText(f"列映射无效 [{exc.code}]：{exc}")
            return
        self.prepared_template = confirmed
        self.xps_preparation = confirmed.payload
        self.mapping_panel.setVisible(False)
        self.edit_mapping_btn.setVisible(True)
        self._show_preparation_details(confirmed, self._current_manifest())
        self.result_values["rows"].setText(str(confirmed.row_count))
        self.result_values["peaks"].setText(str(len(confirmed.summary.components)))
        self._set_run_available(True)
        self.statusBar().showMessage("列映射已确认，真实预览与运行计划已更新", 5000)

    def _clear_preview(self, message: str, *, title: str) -> None:
        self._preview_pixmap = None
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(message)
        self.preview_label.setToolTip("")
        self.template_thumb.setPixmap(QPixmap())
        self.template_thumb.setText("等待预览")
        self.preview_panel.setTitle(title)

    def _load_preview(self, preview: Path | None) -> None:
        if preview and preview.is_file():
            pixmap = QPixmap(str(preview))
            if pixmap.isNull():
                self._preview_pixmap = None
                self.preview_label.setPixmap(QPixmap())
                self.preview_label.setText(f"无法加载预览图：{preview.name}")
                self.template_thumb.setText("无预览")
            else:
                self._preview_pixmap = pixmap
                self.preview_label.setText("")
                self.preview_label.setToolTip(str(preview))
                self.template_thumb.setText("")
                self.template_thumb.setPixmap(
                    pixmap.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self._refresh_preview()
        else:
            self._preview_pixmap = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("暂无预览图")
            self.template_thumb.setPixmap(QPixmap())
            self.template_thumb.setText("无预览")

    def _refresh_preview(self) -> None:
        if self._preview_pixmap is None or self._preview_pixmap.isNull():
            return
        target = self.preview_label.size()
        target.setWidth(max(target.width() - 12, 160))
        target.setHeight(max(target.height() - 12, 120))
        self.preview_label.setPixmap(
            self._preview_pixmap.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _reanalyze_preview(self) -> None:
        """Re-read the selected source and rebuild its shared plan and preview."""
        self._update_file_info(self.csv_path.text())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._apply_responsive_mode()
        self._refresh_preview()

    def _apply_responsive_mode(self, *, force: bool = False) -> None:
        if not hasattr(self, "content_splitter"):
            return
        compact = self.width() < 1080
        if not force and compact == self._compact_mode:
            return
        self._compact_mode = compact
        self.sidebar.setVisible(not compact)
        self.language_label.setVisible(not compact)
        self.language_combo.setVisible(not compact)
        tool_style = Qt.ToolButtonIconOnly if compact else Qt.ToolButtonTextBesideIcon
        for button in self._toolbar_buttons:
            button.setToolButtonStyle(tool_style)
        self.content_splitter.setOrientation(Qt.Vertical if compact else Qt.Horizontal)
        if compact:
            available = max(self.height() - 120, 480)
            self.content_splitter.setSizes([available // 2, available // 2])
            self.preview_label.setMinimumSize(280, 210)
        else:
            available = max(self.width() - self.sidebar.width(), 900)
            self.content_splitter.setSizes([round(available * 0.6), round(available * 0.4)])
            self.preview_label.setMinimumSize(320, 240)
        self.centralWidget().setProperty("compact", compact)
        self._refresh_style(self.centralWidget())

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_preview)
        QTimer.singleShot(150, self._refresh_preview)

    def _choose_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择科研数据文件",
            "",
            "Supported Data (*.csv *.txt *.xls *.xlsx);;CSV (*.csv);;Text (*.txt);;Excel (*.xls *.xlsx)",
        )
        if path:
            self.csv_path.setText(path)
            self.csv_path.setCursorPosition(0)

    def _open_example(self) -> None:
        manifest = self._current_manifest()
        example = self._selected_example()
        example_path = example.path if example is not None else manifest.example_path
        self.csv_path.setText(str(example_path))
        self.csv_path.setCursorPosition(0)
        self._append_log(f"已载入教学样例：{example_path}")

    def _save_blank_template(self) -> None:
        manifest = self._current_manifest()
        source = manifest.blank_template_path
        if source is None or not source.is_file():
            QMessageBox.information(self, "没有空白模板", "当前科研模板暂未提供空白数据表。")
            return
        target, _ = QFileDialog.getSaveFileName(
            self,
            "另存空白数据模板",
            source.name,
            "CSV (*.csv);;Text (*.txt);;Excel (*.xlsx *.xls);;All Files (*)",
        )
        if not target:
            return
        try:
            shutil.copyfile(source, target)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法保存空白模板：{exc}")
            return
        self.statusBar().showMessage(f"空白数据模板已保存：{target}", 5000)

    def _export_preview(self) -> None:
        if self._preview_pixmap is None or self._preview_pixmap.isNull():
            QMessageBox.information(self, "没有预览图", "当前模板没有可导出的预览图。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出预览图", "preview.png", "PNG Files (*.png)")
        if path:
            self._preview_pixmap.save(path, "PNG")
            self.statusBar().showMessage(f"预览图已导出：{path}", 5000)

    def _update_file_info(self, _text: str = "") -> None:
        path_text = self.csv_path.text().strip()
        if not path_text:
            self.xps_preparation = None
            self.prepared_template = None
            self.file_info.setText("等待选择数据文件")
            self.result_values["rows"].setText("--")
            self.result_values["peaks"].setText("--")
            self.mapping_panel.setVisible(False)
            self.edit_mapping_btn.setVisible(False)
            self.template_details.setText(
                "<p style='margin:0; color:#526070;'>选择数据文件后显示自动识别结果、"
                "列角色、置信度与警告。</p>"
            )
            self._clear_preview(
                "选择数据文件后生成与实际绘图规则一致的预览",
                title="真实数据预览（等待识别）",
            )
            self._set_run_available(False)
            return
        path = Path(path_text)
        if not path.is_file():
            self._show_analysis_error("file_not_found", "文件不存在或路径不可访问")
            return

        try:
            service = self._current_service()
            prepared = service.prepare(path)
            manifest = service.manifest
            if prepared.requires_confirmation:
                self._clear_preview(
                    "请先确认列映射，再生成真实数据预览",
                    title="真实数据预览（等待列映射确认）",
                )
                self._show_mapping_editor(prepared)
            else:
                self.mapping_panel.setVisible(False)
                self.edit_mapping_btn.setVisible(True)
                self._set_data_preview(prepared)
        except TemplateServiceError as exc:
            self._show_analysis_error(exc.code, str(exc))
            return
        except TemplateRegistryError as exc:
            self._show_analysis_error("template_unavailable", str(exc))
            return

        self.prepared_template = prepared
        self.xps_preparation = prepared.payload
        self._set_template_route(manifest.id)
        self._show_preparation_details(prepared, manifest)
        preparation = prepared.payload
        size_kb = prepared.source_size_bytes / 1024
        ignored = (
            f"    已忽略空行：{preparation.ignored_empty_rows}"
            if preparation.ignored_empty_rows
            else ""
        )
        sheet = f"    工作表：{prepared.source_sheet}" if prepared.source_sheet else ""
        self.file_info.setText(
            f"格式：{prepared.source_format.upper()}    大小：{size_kb:.1f} KB    "
            f"有效行数：{prepared.row_count}    列数：{len(prepared.source_columns)}"
            f"{ignored}{sheet}"
        )
        self.result_values["rows"].setText(str(prepared.row_count))
        self.result_values["peaks"].setText(str(len(prepared.summary.components)))
        self._set_run_available(not prepared.requires_confirmation)
        if prepared.requires_confirmation:
            self.statusBar().showMessage("自动识别存在歧义，请确认列映射", 7000)
        else:
            self.statusBar().showMessage(f"已识别 {prepared.summary.heading}，可预览并运行", 5000)

    def _show_analysis_error(self, code: str, message: str) -> None:
        self.xps_preparation = None
        self.prepared_template = None
        safe_code = html.escape(code)
        safe_message = html.escape(message)
        try:
            manifest = self._current_manifest()
            data_label = "XPS 数据" if manifest.id == "xps" else f"{manifest.name} 数据"
        except TemplateRegistryError:
            data_label = "科研数据"
        self.file_info.setText(f"无法识别 {data_label} [{code}]：{message}")
        self.result_values["rows"].setText("--")
        self.result_values["peaks"].setText("--")
        self.mapping_panel.setVisible(False)
        self.edit_mapping_btn.setVisible(False)
        self.template_details.setText(
            "<p style='margin:0 0 5px 0; color:#9b1c1c; font-weight:600;'>"
            f"{html.escape(data_label)}识别失败（{safe_code}）</p>"
            f"<p style='margin:0; color:#526070;'>{safe_message}</p>"
        )
        self._clear_preview(
            f"无法生成真实预览\n[{code}] {message}",
            title="真实数据预览（识别失败）",
        )
        self._set_run_available(False)
        self.statusBar().showMessage(f"{data_label}识别失败，请检查文件", 5000)

    def _set_run_available(self, available: bool) -> None:
        running = bool(self.process and self.process.state() != QProcess.NotRunning)
        self.run_btn.setEnabled(available and not running)

    def _append_log(self, text: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {text}")

    def _clear_log(self) -> None:
        self.log.clear()
        self.statusBar().showMessage("日志已清空", 3000)

    def _new_task(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "任务正在运行", "请等待当前任务结束，或先停止任务。")
            return
        self.csv_path.clear()
        self.xps_preparation = None
        self.prepared_template = None
        self.mapping_panel.setVisible(False)
        self.edit_mapping_btn.setVisible(False)
        self._stdout_buffer = b""
        self.log.clear()
        self.last_output_dir = None
        self._run_started_at = None
        self.open_output_btn.setEnabled(False)
        self.open_output_action.setEnabled(False)
        self._set_status("就绪", "Ready")
        self.progress.setValue(0)
        self.elapsed_value.setText("--")
        self.result_values["origin"].setText("--")
        self.result_values["verify"].setText("待运行")
        self._reset_output_rows()
        self.statusBar().showMessage("已创建新任务")

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于 EditaPlot",
            f"EditaPlot v{__version__}\n"
            "面向 XPS、XRD、PL、UV–Vis、统计与医学证据图，自动识别数据并生成数据预览与 Origin 可编辑图。",
        )

    def _start_worker(self) -> None:
        input_file = Path(self.csv_path.text().strip())
        if not input_file.is_file():
            QMessageBox.warning(self, "缺少数据", "请先选择一个存在的数据文件。")
            return
        prepared = self.prepared_template
        if (
            prepared is None
            or prepared.requires_confirmation
            or Path(prepared.source_path) != input_file.resolve()
        ):
            QMessageBox.warning(
                self,
                "绘图数据尚未就绪",
                "当前文件尚未完成识别、列映射确认与真实预览，请处理后再运行。",
            )
            return
        service = self._current_service()
        self.run_btn_set_enabled(False)
        self.open_output_btn.setEnabled(False)
        self.open_output_action.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.elapsed_value.setText("00:00:00")
        self.result_values["origin"].setText("--")
        self.result_values["verify"].setText("运行中")
        self._reset_output_rows()
        self.log.clear()
        self._set_status("运行中", "Running")
        self._run_started_at = time.monotonic()
        self._stdout_buffer = b""
        self._append_log("准备启动 Origin 绘图任务...")

        self.process = QProcess(self)
        env = self.process.processEnvironment()
        if not getattr(sys, "frozen", False):
            source_path = str(Path(__file__).resolve().parents[1])
            env.insert("PYTHONPATH", source_path + os.pathsep + env.value("PYTHONPATH", ""))
        self.process.setProcessEnvironment(env)
        program, args = build_worker_command(
            sys.executable,
            prepared.template_id,
            input_file,
            keep_origin_open=self.keep_origin.isChecked(),
            frozen=bool(getattr(sys, "frozen", False)),
            expected_plan_digest=prepared.plan_digest,
            column_mapping=service.worker_mapping(prepared),
        )
        self.process.readyReadStandardOutput.connect(self._read_worker_stdout)
        self.process.readyReadStandardError.connect(self._read_worker_stderr)
        self.process.finished.connect(self._worker_finished)
        self.process.start(program, args)

    def run_btn_set_enabled(self, enabled: bool) -> None:
        self.run_btn.setEnabled(enabled)
        self.run_action_enabled(enabled)

    def run_action_enabled(self, enabled: bool) -> None:
        # Kept as a tiny shim so the menu/toolbar state can grow without touching worker code.
        self.choose_csv_action.setEnabled(enabled)

    def _stop_worker(self) -> None:
        if self.process and self.process.state() != QProcess.NotRunning:
            self._append_log("正在请求停止当前任务...")
            self.process.kill()
            self.stop_btn.setEnabled(False)

    def _read_worker_stdout(self) -> None:
        if not self.process:
            return
        self._stdout_buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self._stdout_buffer:
            raw_line, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
            self._handle_worker_stdout_line(raw_line.rstrip(b"\r"))

    def _handle_worker_stdout_line(self, raw_line: bytes) -> None:
        if not raw_line.strip():
            return
        line = raw_line.decode("utf-8", errors="replace")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            self._append_log(line)
            return
        if not isinstance(payload, dict):
            self._append_log(line)
            return
        kind = payload.get("type")
        if kind == "progress":
            step = str(payload.get("step", ""))
            status = str(payload.get("status", ""))
            target = STAGE_PROGRESS.get(step, self.progress.value())
            self.progress.setValue(target if status == "success" else max(0, target - 5))
            self._append_log(f"[{status}] {payload.get('message')}")
        elif kind == "warning":
            self._append_log(f"[warning] {payload.get('message')}")
        elif kind == "error":
            self._append_log(f"[error] {payload.get('message')}")
            if payload.get("code") == "analysis_changed":
                QTimer.singleShot(0, self._reanalyze_preview)
        elif kind == "done":
            self._handle_done(payload)

    def _handle_done(self, payload: dict) -> None:
        self.last_output_dir = Path(payload["output_dir"])
        self._append_log("完成。输出目录：" + str(self.last_output_dir))
        self.open_output_btn.setEnabled(True)
        self.open_output_action.setEnabled(True)
        self.progress.setValue(100)
        self._set_status("已完成", "Success")
        self.result_values["origin"].setText(str(payload.get("origin_version", "--")))
        self.result_values["verify"].setText("程序反读通过")
        self._update_output_rows(payload)
        self.statusBar().showMessage("程序校验完成，请在 Origin 窗口或导出图中进行人工视觉确认")

    def _read_worker_stderr(self) -> None:
        if self.process:
            data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
            if data.strip():
                self._append_log(data.strip())

    def _worker_finished(self, exit_code: int, _status) -> None:
        self.stop_btn.setEnabled(False)
        self.run_btn_set_enabled(
            self.prepared_template is not None
            and not self.prepared_template.requires_confirmation
        )
        if self._stdout_buffer.strip():
            self._append_log("[warning] worker 输出包含未完成的协议消息，已安全丢弃。")
        self._stdout_buffer = b""
        if self._run_started_at is not None:
            elapsed = max(0, int(time.monotonic() - self._run_started_at))
            self.elapsed_value.setText(time.strftime("%H:%M:%S", time.gmtime(elapsed)))
        if exit_code == 0:
            self._append_log("worker 成功退出。")
            self.statusBar().showMessage("自动导出与程序反读已完成；请进行人工视觉确认")
        else:
            self._set_status("失败", "Error")
            self.result_values["verify"].setText("失败")
            self._append_log(f"worker 失败退出，退出码：{exit_code}")
            self.statusBar().showMessage("任务失败")

    def _set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setObjectName(f"Status{state}")
        self._refresh_style(self.status_label)

    def _reset_output_rows(self) -> None:
        for key, _label, filename in OUTPUT_ROWS:
            self.output_path_labels[key].setText(filename)
            self.output_state_labels[key].setText("待生成")
            self.output_state_labels[key].setObjectName("OutputPending")
            self._refresh_style(self.output_state_labels[key])

    def _update_output_rows(self, payload: dict) -> None:
        for key, _label, filename in OUTPUT_ROWS:
            value = payload.get(key)
            if value:
                self.output_path_labels[key].setText(str(value))
                self.output_state_labels[key].setText("已生成")
                self.output_state_labels[key].setObjectName("OutputDone")
            else:
                self.output_path_labels[key].setText(filename)
                self.output_state_labels[key].setText("未生成")
                self.output_state_labels[key].setObjectName("OutputSkipped")
            self._refresh_style(self.output_state_labels[key])

    def _refresh_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _open_output_dir(self) -> None:
        if self.last_output_dir and self.last_output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output_dir)))
        else:
            QMessageBox.information(self, "没有输出文件夹", "当前任务还没有生成输出文件夹。")
