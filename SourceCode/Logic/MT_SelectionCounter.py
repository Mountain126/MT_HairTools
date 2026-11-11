# -*- coding: utf-8 -*-
# Chạy được trên Maya 2018–2020 (Python 2.7) và Maya 2022 trở lên (Python 3).
# Không dùng unicode_literals: Maya 2018 cần byte string cho tên event/flag.
import sys
import maya.cmds as cmds
import maya.OpenMaya as om
import maya.OpenMayaUI as omui

if sys.version_info[0] >= 3:
    from importlib import reload as _reload
else:
    _reload = reload     # Python 2: reload là hàm có sẵn

# Thanh Transform Type-In (giao diện Qt). Reload cùng file này để mở lại tool là nhận code mới;
# file UI tự reload logic transform_typein.
from SourceCode.UI import MT_TransformTypeIn as typein_ui
_reload(typein_ui)

def color01(r, g, b):
    return (r/255.0, g/255.0, b/255.0)

# Chiều rộng nội dung được căn chỉnh để cửa sổ có tổng bề rộng 380 px.
WINDOW_WIDTH = 380
SIDE_MARGIN = 10
POLY_LABEL_WIDTH = 54
POLY_VALUE_WIDTH = 142
POLY_TABLE_WIDTH = POLY_LABEL_WIDTH + (POLY_VALUE_WIDTH * 2) + 12
CONTENT_MIN_WIDTH = WINDOW_WIDTH - 16
TITLE_BG = "#212954"
ROW_SPACING = 6
TEXT_HEIGHT = 26
# Khung kích thước: hàng X/Y/Z chia 3 phần đều nhau theo bề rộng cửa sổ.
SIZE_AXIS_LABEL_WIDTH = 16
SIZE_LABEL_GAP = 4      # khoảng cách giữa chữ trục và ô số
SIZE_GROUP_GAP = 6      # nửa khoảng cách giữa 2 nhóm trục liền nhau
SIZE_UNIT_PAD = 6       # khoảng cách từ đơn vị tới mép phải ô kích thước
# Số đối tượng tối đa được gắn scriptJob theo dõi rotate/scale, tránh tạo quá nhiều job.
SIZE_WATCH_LIMIT = 50
# Phần Transform Type-In: thanh Qt xếp dọc 4 hàng (World/Move, X, Y, Z).
TYPEIN_HEIGHT = typein_ui.TYPEIN_EMBED_HEIGHT
# 7 separator + 3 dòng chữ + bảng polycount 6 dòng + bảng kích thước 2 dòng
# + phần Type-In + 2 hàng nút + khoảng cách giữa 15 phần tử
KNOWN_MIN_HEIGHT = (
    (4 * 7)
    + (TEXT_HEIGHT * 3)
    + ((TEXT_HEIGHT * 6) + (4 * 5))
    + ((TEXT_HEIGHT * 2) + 4)
    + TYPEIN_HEIGHT
    + 28
    + 28
    + (ROW_SPACING * 14)
    + 2
)

SIZE_AXES = ("X", "Y", "Z")

POLY_ROWS = (
    ("vertex", "Verts:"),
    ("edge", "Edges:"),
    ("face", "Faces:"),
    ("triangle", "Tris:"),
    ("uvcoord", "UVs:"),
)

class MT_SelectionCounter(object):
    def __init__(self):
        self.window_name = "MT_SelectionCounterWindow"
        self.title = "MT Selection Counter"
        self.job_ids = []
        self._floor_w = CONTENT_MIN_WIDTH + 16
        self._floor_h = KNOWN_MIN_HEIGHT + 20
        self._base_min_w = self._floor_w
        self._base_min_h = self._floor_h
        self._clamping = False
        self._layer_jobs = {}
        self._size_jobs = []
        self._size_roots = []
        self.build_ui()
        self.setup_scriptjob()

    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
        if cmds.workspaceControl(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        # workspaceControl chặn minimumWidth/Height thật sự, cmds.window thì không.
        self.window = cmds.workspaceControl(
            self.window_name,
            label=self.title,
            retain=False,
            floating=True,
            widthProperty="free",
            heightProperty="free",
            minimumWidth=self._floor_w,
            minimumHeight=self._floor_h,
            initialWidth=self._floor_w,
            initialHeight=self._floor_h,
        )
        cmds.setParent(self.window_name)
        
        self.main_layout = cmds.columnLayout(
            adjustableColumn=True,
            columnAttach=("both", SIDE_MARGIN),
            rowSpacing=ROW_SPACING,
        )
        cmds.scriptJob(uiDeleted=[self.main_layout, self.cleanup_scriptjob], parent=self.main_layout)
        
        cmds.separator(height=4, style="none")
        self.txt_title = cmds.text(
            label=u"BẢNG THỐNG KÊ ĐỐI TƯỢNG REALTIME",
            align="center",
            font="boldLabelFont",
            height=TEXT_HEIGHT,
        )
        cmds.separator(height=4, style="in")
        
        # Nhãn hiển thị số lượng realtime
        self.txt_status = cmds.text(
            label=u"Đang chọn: 0 Mesh  |  0 Curve",
            align="center",
            font="boldLabelFont",
            height=TEXT_HEIGHT,
        )
        self.txt_mesh_name = cmds.text(
            label=u" ",
            align="center",
            font="boldLabelFont",
            height=TEXT_HEIGHT,
        )

        cmds.separator(height=4, style="in")

        # Hai cột: mesh đang hiện trong scene / mesh đang chọn.
        self.poly_layout = cmds.rowColumnLayout(
            numberOfColumns=3,
            columnWidth=[(1, POLY_LABEL_WIDTH), (2, POLY_VALUE_WIDTH), (3, POLY_VALUE_WIDTH)],
            columnSpacing=[(2, 6), (3, 12)],
            rowSpacing=[(1, 4), (2, 4), (3, 4), (4, 4), (5, 4)],
        )
        cmds.text(label="", height=TEXT_HEIGHT)
        self.poly_headers = [
            cmds.text(label="Visible", align="right", font="boldLabelFont", height=TEXT_HEIGHT),
            cmds.text(label="Selected", align="right", font="boldLabelFont", height=TEXT_HEIGHT),
        ]

        self.poly_labels = []
        self.poly_cells = {}
        for key, title in POLY_ROWS:
            self.poly_labels.append(
                cmds.text(label=title, align="left", font="boldLabelFont", height=TEXT_HEIGHT)
            )
            self.poly_cells[key] = [
                cmds.text(label="0", align="right", font="boldLabelFont", height=TEXT_HEIGHT),
                cmds.text(label="0", align="right", font="boldLabelFont", height=TEXT_HEIGHT),
            ]
        cmds.setParent("..")

        cmds.separator(height=4, style="in")

        # Kích thước tổng (bounding box world space) của toàn bộ đối tượng đang chọn.
        # Hàng trên: tiêu đề Dimensions ở giữa. Hàng dưới: X [ô] Y [ô] Z [ô], đơn vị nằm trong ô.
        self.size_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        self.size_title = cmds.text(
            label="Dimensions", align="center", font="boldLabelFont", height=TEXT_HEIGHT
        )
        size_row = cmds.formLayout(numberOfDivisions=300, height=TEXT_HEIGHT)
        self.size_axis_labels = []
        self.size_cells = []
        attach_form = []
        attach_position = []
        attach_control = []
        for index, axis in enumerate(SIZE_AXES):
            label = cmds.text(
                label=axis, align="left", font="boldLabelFont",
                width=SIZE_AXIS_LABEL_WIDTH, height=TEXT_HEIGHT,
            )
            cell = cmds.text(label="-", align="right", font="boldLabelFont", height=TEXT_HEIGHT)
            left_gap = 0 if index == 0 else SIZE_GROUP_GAP
            right_gap = 0 if index == len(SIZE_AXES) - 1 else SIZE_GROUP_GAP
            attach_form.extend([(label, "top", 0), (cell, "top", 0)])
            attach_position.extend([
                (label, "left", left_gap, index * 100),
                (cell, "right", right_gap, (index + 1) * 100),
            ])
            attach_control.append((cell, "left", SIZE_LABEL_GAP, label))
            self.size_axis_labels.append(label)
            self.size_cells.append(cell)
        cmds.formLayout(
            size_row,
            edit=True,
            attachForm=attach_form,
            attachPosition=attach_position,
            attachControl=attach_control,
        )
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.separator(height=4, style="in")

        # Transform Type-In giống panel MT Tools: ô nhập + spinner, tự đổi theo tool Move/Rotate/Scale.
        self.typein_holder = typein_ui.embed_typein(self.main_layout, on_changed=self.update_size)
        cmds.setParent(self.main_layout)

        cmds.separator(height=4, style="in")

        # Các nút hỗ trợ chọn lọc nhanh
        # formLayout chia 50/50 để hai nút luôn lấp đầy bề rộng cửa sổ.
        self.button_layout = cmds.formLayout(height=28)
        btn_mesh = cmds.button(
            label=u"Select All Meshes In Group",
            h=28,
            bgc=color01(57, 146, 255),
            command=lambda *args: self.select_all_meshes(),
        )
        btn_curve = cmds.button(
            label=u"Select All Curves In Group",
            h=28,
            bgc=color01(238, 137, 38),
            command=lambda *args: self.select_all_curves(),
        )
        cmds.formLayout(
            self.button_layout,
            edit=True,
            attachForm=[(btn_mesh, "left", 0), (btn_mesh, "top", 0), (btn_mesh, "bottom", 0),
                        (btn_curve, "right", 0), (btn_curve, "top", 0), (btn_curve, "bottom", 0)],
            attachPosition=[(btn_mesh, "right", 0, 49), (btn_curve, "left", 0, 51)],
        )
        cmds.setParent("..")
        cmds.button(
            label=u"Select Group From Mesh Or Curve",
            h=28,
            command=lambda *args: self.select_top_groups(),
        )
        cmds.separator(height=4, style="none")
        
        cmds.workspaceControl(
            self.window_name,
            edit=True,
            restore=True,
            floating=True,
            minimumWidth=self._floor_w,
            minimumHeight=self._floor_h,
            resizeWidth=self._floor_w,
            resizeHeight=self._floor_h,
        )
        # Chạy cập nhật ngay lần đầu mở, rồi khóa kích thước tối thiểu
        self.update_counter()
        cmds.evalDeferred(self._style_readouts, lowestPriority=True)
        cmds.evalDeferred(self._fit_and_lock_size, lowestPriority=True)

    def setup_scriptjob(self):
        # SelectionChanged khi đổi vùng chọn; Undo/Redo khi hình học đổi mà selection giữ nguyên
        for event in ("SelectionChanged", "Undo", "Redo"):
            job_id = cmds.scriptJob(event=[event, self.update_counter], parent=self.main_layout)
            self.job_ids.append(job_id)
        # Thả chuột sau khi kéo manipulator (move/rotate/scale object hoặc component)
        # thì tính lại kích thước, vì selection không đổi nên SelectionChanged không chạy.
        try:
            job_id = cmds.scriptJob(event=["DragRelease", self.update_size], parent=self.main_layout)
            self.job_ids.append(job_id)
        except Exception:
            pass
        # Một số bản Maya vẫn cho kéo floating panel nhỏ hơn minimum, nên kẹp lại khi idle.
        job_id = cmds.scriptJob(event=["idle", self._clamp_if_smaller], parent=self.main_layout)
        self.job_ids.append(job_id)
        
    def cleanup_scriptjob(self):
        for job_id in self.job_ids:
            if job_id and cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        self.job_ids = []
        for job_id in getattr(self, "_layer_jobs", {}).values():
            if job_id and cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        self._layer_jobs = {}
        self._kill_size_jobs()

    def _ui_exists(self):
        return cmds.workspaceControl(self.window_name, exists=True)

    def _qt_modules(self):
        # Maya 2025 trở lên dùng PySide6, Maya 2017–2024 dùng PySide2.
        try:
            from PySide6 import QtCore, QtWidgets
        except ImportError:
            from PySide2 import QtCore, QtWidgets
        return QtCore, QtWidgets

    def _wrap(self, ptr, widget_cls):
        if not ptr:
            return None
        try:
            from shiboken6 import wrapInstance
        except ImportError:
            from shiboken2 import wrapInstance
        if sys.version_info[0] < 3:
            ptr = long(ptr)
        else:
            ptr = int(ptr)
        return wrapInstance(ptr, widget_cls)

    def _qt_widget(self):
        QtCore, QtWidgets = self._qt_modules()
        ptr = omui.MQtUtil.findControl(self.window_name)
        if not ptr:
            ptr = omui.MQtUtil.findWindow(self.window_name)
        return self._wrap(ptr, QtWidgets.QWidget)

    def _label_min_width(self):
        text_w = 0
        for control in (
            getattr(self, "txt_title", None),
            getattr(self, "txt_status", None),
            getattr(self, "txt_mesh_name", None),
        ):
            text_w = max(text_w, self._text_pixel_width(control))
        if text_w < 1:
            return self._floor_w
        return max(self._floor_w, text_w + (SIDE_MARGIN * 2) + 24)

    def _clamp_if_smaller(self):
        if self._clamping or not self._ui_exists():
            return
        widget = self._qt_widget()
        if widget is None:
            return
        top = widget.window()
        if top is not None and top.objectName() == "MayaWindow":
            top = widget
        width = top.width()
        height = top.height()
        min_w = self._base_min_w
        min_h = self._base_min_h
        if width >= min_w and height >= min_h:
            self._last_small = None
            return
        key = (width, height, min_w, min_h)
        if key == getattr(self, "_last_small", None):
            return
        self._last_small = key
        self._clamping = True
        try:
            cmds.workspaceControl(
                self.window_name,
                edit=True,
                minimumWidth=min_w,
                minimumHeight=min_h,
                resizeWidth=max(width, min_w),
                resizeHeight=max(height, min_h),
            )
        except Exception:
            pass
        finally:
            self._clamping = False

    def _fit_and_lock_size(self):
        if not self._ui_exists():
            return
        self._base_min_w = self._label_min_width()
        self._base_min_h = self._floor_h
        self._clamping = True
        try:
            cmds.workspaceControl(
                self.window_name,
                edit=True,
                floating=True,
                minimumWidth=self._base_min_w,
                minimumHeight=self._base_min_h,
                resizeWidth=self._base_min_w,
                resizeHeight=self._base_min_h,
            )
        except Exception:
            pass
        finally:
            self._clamping = False
        self._clamp_if_smaller()

    def _text_pixel_width(self, control):
        if not control or not cmds.control(control, exists=True):
            return 0
        label = cmds.text(control, query=True, label=True) or ""
        if not label.strip():
            return 0
        QtCore, QtWidgets = self._qt_modules()
        widget = self._wrap(omui.MQtUtil.findControl(control), QtWidgets.QLabel)
        if widget is None:
            return 0
        metrics = widget.fontMetrics()
        if hasattr(metrics, "horizontalAdvance"):
            return metrics.horizontalAdvance(label)
        return metrics.width(label)

    def _style_label(self, control, boxed=False, background="transparent"):
        """Chữ trắng, đậm, nền ô riêng cho số để tách khỏi nền xám của Maya."""
        if not control or not cmds.control(control, exists=True):
            return
        QtCore, QtWidgets = self._qt_modules()
        widget = self._wrap(omui.MQtUtil.findControl(control), QtWidgets.QLabel)
        if widget is None:
            return
        # PySide6 bản mới chỉ chấp nhận enum đầy đủ (Qt.WidgetAttribute.WA_StyledBackground),
        # PySide2 thì dùng tên ngắn.
        widget_attr = getattr(QtCore.Qt, "WidgetAttribute", QtCore.Qt)
        widget.setAttribute(widget_attr.WA_StyledBackground, True)
        font = widget.font()
        font.setBold(True)
        if font.pointSize() > 0 and font.pointSize() < 11:
            font.setPointSize(11)
        widget.setFont(font)
        if boxed:
            widget.setStyleSheet(
                "color: #FFFFFF;"
                "background-color: #3A3A3A;"
                "border: 1px solid #6A6A6A;"
                "border-radius: 3px;"
                "padding: 1px 8px;"
            )
        else:
            widget.setStyleSheet("color: #FFFFFF; background: {0};".format(background))

    def _style_readouts(self):
        if not self._ui_exists():
            return
        self._style_label(getattr(self, "txt_title", None), background=TITLE_BG)
        for control in (
            getattr(self, "txt_status", None),
            getattr(self, "txt_mesh_name", None),
        ):
            self._style_label(control, boxed=False)
        for control in getattr(self, "poly_headers", []):
            self._style_label(control, boxed=False)
        for control in getattr(self, "poly_labels", []):
            self._style_label(control, boxed=False)
        for cells in getattr(self, "poly_cells", {}).values():
            for control in cells:
                self._style_label(control, boxed=True)
        self._style_label(getattr(self, "size_title", None), boxed=False)
        for control in getattr(self, "size_axis_labels", []):
            self._style_label(control, boxed=False)
        for control in getattr(self, "size_cells", []):
            self._style_label(control, boxed=True)
            self._make_copyable(control)
            self._apply_size_unit(control)

    def _apply_size_unit(self, control):
        """Hiện đơn vị màu xám ở mép phải ô kích thước, giống ô nhập của Transform Type-In.

        Đơn vị là QLabel con, chuột xuyên qua, nên khi bôi đen/copy chỉ lấy được phần số.
        """
        if not control or not cmds.control(control, exists=True):
            return
        QtCore, QtWidgets = self._qt_modules()
        widget = self._wrap(omui.MQtUtil.findControl(control), QtWidgets.QLabel)
        if widget is None:
            return
        unit_widget = widget.findChild(QtWidgets.QLabel, "mtSizeUnit")
        if unit_widget is None:
            widget_attr = getattr(QtCore.Qt, "WidgetAttribute", QtCore.Qt)
            align = getattr(QtCore.Qt, "AlignmentFlag", QtCore.Qt)
            # Layout tính trên toàn bộ ô, không bị padding của stylesheet đẩy vào trong.
            widget.setAttribute(widget_attr.WA_LayoutOnEntireRect, True)
            unit_widget = QtWidgets.QLabel(widget)
            unit_widget.setObjectName("mtSizeUnit")
            unit_widget.setAttribute(widget_attr.WA_TransparentForMouseEvents, True)
            unit_widget.setAlignment(align.AlignRight | align.AlignVCenter)
            unit_widget.setStyleSheet(
                "color: rgb(150, 150, 150); background: transparent; border: none; padding: 0px;"
            )
            layout = QtWidgets.QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, SIZE_UNIT_PAD, 0)
            layout.setSpacing(0)
            layout.addStretch(1)
            layout.addWidget(unit_widget)
        font = widget.font()
        font.setBold(False)
        unit_widget.setFont(font)
        text = getattr(self, "_size_unit_text", "")
        unit_widget.setText(text)
        unit_widget.setVisible(bool(text))
        # Chừa chỗ bên phải cho đơn vị để số không đè lên.
        right = 8
        if text:
            metrics = unit_widget.fontMetrics()
            if hasattr(metrics, "horizontalAdvance"):
                right = metrics.horizontalAdvance(text) + SIZE_UNIT_PAD + 4
            else:
                right = metrics.width(text) + SIZE_UNIT_PAD + 4
        widget.setStyleSheet(
            "color: #FFFFFF;"
            "background-color: #3A3A3A;"
            "border: 1px solid #6A6A6A;"
            "border-radius: 3px;"
            "padding: 1px {0}px 1px 8px;".format(right)
        )

    def _make_copyable(self, control):
        """Cho bôi đen và copy số (Ctrl+C hoặc click phải > Copy). QLabel vốn chỉ đọc nên không nhập được."""
        if not control or not cmds.control(control, exists=True):
            return
        QtCore, QtWidgets = self._qt_modules()
        widget = self._wrap(omui.MQtUtil.findControl(control), QtWidgets.QLabel)
        if widget is None:
            return
        # PySide6 bản mới chỉ nhận tên enum đầy đủ, PySide2 dùng tên ngắn.
        flag_scope = getattr(QtCore.Qt, "TextInteractionFlag", QtCore.Qt)
        cursor_scope = getattr(QtCore.Qt, "CursorShape", QtCore.Qt)
        widget.setTextInteractionFlags(
            flag_scope.TextSelectableByMouse | flag_scope.TextSelectableByKeyboard
        )
        widget.setCursor(cursor_scope.IBeamCursor)
        widget.setToolTip(u"Bôi đen hoặc double-click để chọn số, rồi Ctrl+C (hoặc click phải > Copy).")

    def _format_count(self, value):
        try:
            number = int(value or 0)
        except Exception:
            number = 0
        return "{:,}".format(number).replace(",", ".")

    def update_counter(self):
        """Hàm tự động quét và cập nhật số lượng realtime"""
        if not self._ui_exists():
            return
            
        # Object mode dùng selection. Component mode Maya chỉ highlight object cha (hilite).
        roots = []
        picked = (cmds.ls(selection=True, long=True) or []) + (cmds.ls(hilite=True, long=True) or [])
        for item in picked:
            node = item.split(".")[0]
            if node not in roots and cmds.objExists(node):
                roots.append(node)
        
        # Đếm Mesh (bao gồm cả trong group con)
        shapes = []
        if roots:
            shapes = cmds.listRelatives(roots, allDescendents=True, type="mesh", fullPath=True) or []
        mesh_transforms = list(set([cmds.listRelatives(m, parent=True, fullPath=True)[0] for m in shapes]))
        direct_meshes = []
        for obj in roots:
            if cmds.nodeType(obj) == "mesh":
                parents = cmds.listRelatives(obj, parent=True, fullPath=True) or []
                if parents:
                    direct_meshes.append(parents[0])
            elif cmds.listRelatives(obj, shapes=True, type="mesh", fullPath=True):
                direct_meshes.append(obj)
        self.total_meshes = list(set(mesh_transforms + direct_meshes))
        
        # Đếm Curve
        curve_shapes = []
        if roots:
            curve_shapes = cmds.listRelatives(roots, allDescendents=True, type=("nurbsCurve", "bezierCurve"), fullPath=True) or []
        curve_transforms = list(set([cmds.listRelatives(c, parent=True, fullPath=True)[0] for c in curve_shapes]))
        direct_curves = []
        for obj in roots:
            if cmds.nodeType(obj) in ("nurbsCurve", "bezierCurve"):
                parents = cmds.listRelatives(obj, parent=True, fullPath=True) or []
                if parents:
                    direct_curves.append(parents[0])
            elif cmds.listRelatives(obj, shapes=True, type=("nurbsCurve", "bezierCurve"), fullPath=True):
                direct_curves.append(obj)
        self.total_curves = list(set(curve_transforms + direct_curves))
        
        # Cập nhật text trên UI
        if hasattr(self, 'txt_status') and cmds.control(self.txt_status, exists=True):
            status_str = u"Đang chọn: {0} Mesh  |  {1} Curve".format(len(self.total_meshes), len(self.total_curves))
            cmds.text(self.txt_status, edit=True, label=status_str)

        if hasattr(self, 'txt_mesh_name') and cmds.control(self.txt_mesh_name, exists=True):
            if len(self.total_meshes) == 1:
                mesh_name = self.total_meshes[0].split("|")[-1]
                cmds.text(self.txt_mesh_name, edit=True, label=u"Mesh: {0}".format(mesh_name))
            else:
                cmds.text(self.txt_mesh_name, edit=True, label=u" ")

        self._update_polycount()
        self._size_roots = roots
        self.update_size()
        self._watch_size_roots(roots)
        self._watch_display_layers()
        self._style_readouts()
        self._base_min_w = self._label_min_width()
        self._clamp_if_smaller()

    def _unit_label(self):
        """Đơn vị chiều dài đang dùng trong scene (cm, m, mm, in...)."""
        try:
            unit = cmds.currentUnit(query=True, linear=True) or "cm"
        except Exception:
            unit = "cm"
        return unit

    def _format_size(self, value):
        """Định dạng giống phần đếm polycount: dấu chấm ngăn hàng nghìn, dấu phẩy thập phân."""
        try:
            number = float(value)
        except Exception:
            return "-"
        text = "{0:,.2f}".format(number)
        return text.replace(",", "_").replace(".", ",").replace("_", ".")

    def _bounding_box(self, nodes):
        """Bounding box world space gộp của các node, trả về (xmin, ymin, zmin, xmax, ymax, zmax).

        exactWorldBoundingBox bám sát hình học (không bị phồng như bounding box
        của transform khi xoay). Nếu lệnh lỗi thì lùi về xform cho từng node rồi gộp lại.
        """
        nodes = [node for node in nodes if cmds.objExists(node)]
        if not nodes:
            return None
        try:
            box = cmds.exactWorldBoundingBox(nodes)
            if box and len(box) == 6:
                return tuple(box)
        except Exception:
            pass
        merged = None
        for node in nodes:
            try:
                box = cmds.xform(node, query=True, boundingBox=True, worldSpace=True)
            except Exception:
                continue
            if not box or len(box) != 6:
                continue
            if merged is None:
                merged = list(box)
                continue
            for index in range(3):
                merged[index] = min(merged[index], box[index])
                merged[index + 3] = max(merged[index + 3], box[index + 3])
        return tuple(merged) if merged else None

    def update_size(self):
        """Cập nhật kích thước tổng theo 3 trục X, Y, Z của vùng chọn."""
        if not self._ui_exists() or not hasattr(self, "size_cells"):
            return
        box = self._bounding_box(getattr(self, "_size_roots", []))
        # Chỉ ghi số vào ô; đơn vị vẽ riêng (xem _apply_size_unit) để copy không dính đơn vị.
        self._size_unit_text = "" if box is None else self._unit_label()
        for index, ctrl in enumerate(self.size_cells):
            if not cmds.control(ctrl, exists=True):
                continue
            if box is None:
                label = "-"
            else:
                label = self._format_size(abs(box[index + 3] - box[index]))
            cmds.text(ctrl, edit=True, label=label)
            self._apply_size_unit(ctrl)

    def _kill_size_jobs(self):
        for job_id in getattr(self, "_size_jobs", []):
            if job_id and cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        self._size_jobs = []

    def _watch_size_roots(self, roots):
        """Tính lại kích thước khi gõ giá trị rotate/scale trong Channel Box.

        Kéo manipulator đã có event DragRelease lo. Chỉ gắn job khi số đối tượng
        ít, vì mỗi đối tượng cần 2 scriptJob.
        """
        self._kill_size_jobs()
        if not cmds.layout(self.main_layout, exists=True):
            return
        if len(roots) > SIZE_WATCH_LIMIT:
            return
        for node in roots:
            if not cmds.objExists(node) or not cmds.objectType(node, isAType="transform"):
                continue
            for attr in ("rotate", "scale"):
                try:
                    job_id = cmds.scriptJob(
                        attributeChange=[node + "." + attr, self.update_size],
                        allChildren=True,
                        parent=self.main_layout,
                    )
                except Exception:
                    continue
                self._size_jobs.append(job_id)

    def _as_int(self, value):
        if isinstance(value, dict):
            for key in ("vertex", "edge", "face", "triangle", "uvcoord"):
                if key in value:
                    return self._as_int(value[key])
            return 0
        if isinstance(value, (list, tuple)):
            return self._as_int(value[0]) if value else 0
        try:
            return int(value or 0)
        except Exception:
            return 0

    def _poly_stats(self, nodes):
        stats = {"vertex": 0, "edge": 0, "face": 0, "triangle": 0, "uvcoord": 0}
        if not nodes:
            return stats
        try:
            result = cmds.polyEvaluate(
                list(nodes),
                vertex=True,
                edge=True,
                face=True,
                triangle=True,
                uvcoord=True,
            )
        except Exception:
            return stats
        if isinstance(result, dict):
            for key in stats:
                stats[key] = self._as_int(result.get(key, 0))
        return stats

    def _watch_display_layers(self):
        """Cập nhật lại khi bật/tắt visibility của display layer."""
        if not hasattr(self, "_layer_jobs"):
            self._layer_jobs = {}
        if not cmds.layout(self.main_layout, exists=True):
            return
        layers = cmds.ls(type="displayLayer") or []
        alive = set(layers)
        for layer, job_id in list(self._layer_jobs.items()):
            if layer not in alive:
                if job_id and cmds.scriptJob(exists=job_id):
                    cmds.scriptJob(kill=job_id, force=True)
                del self._layer_jobs[layer]
        for layer in layers:
            if layer in self._layer_jobs:
                continue
            plug = layer + ".visibility"
            if not cmds.attributeQuery("visibility", node=layer, exists=True):
                continue
            job_id = cmds.scriptJob(
                attributeChange=[plug, self.update_counter],
                parent=self.main_layout,
            )
            self._layer_jobs[layer] = job_id

    def _shapes_hidden_by_display_layer(self):
        """Mesh nằm trong layer đang tắt, kể cả layer gắn trên group cha.

        Outliner vẫn hiện visibility của chính mesh, nhưng viewport không vẽ
        khi display layer của group bị ẩn.
        """
        hidden = set()
        layers = cmds.ls(type="displayLayer") or []
        for layer in layers:
            try:
                if cmds.getAttr(layer + ".visibility"):
                    continue
            except Exception:
                continue
            members = cmds.editDisplayLayerMembers(layer, query=True) or []
            if not members:
                continue
            members = cmds.ls(members, long=True) or members
            for member in members:
                if not cmds.objExists(member):
                    continue
                if cmds.nodeType(member) == "mesh":
                    hidden.add(member)
                shapes = cmds.listRelatives(
                    member, allDescendents=True, type="mesh", fullPath=True
                ) or []
                for shape in shapes:
                    hidden.add(shape)
        return hidden

    def _selected_mesh_shapes(self):
        shapes = []
        for node in self.total_meshes:
            if not cmds.objExists(node):
                continue
            if cmds.nodeType(node) == "mesh":
                shapes.append(node)
                continue
            found = cmds.listRelatives(
                node, shapes=True, type="mesh", noIntermediate=True, fullPath=True
            ) or []
            shapes.extend(found)
        return shapes

    def _update_polycount(self):
        if not hasattr(self, "poly_cells"):
            return

        visible = cmds.ls(type="mesh", noIntermediate=True, visible=True, long=True) or []
        hidden_by_layer = self._shapes_hidden_by_display_layer()
        if hidden_by_layer:
            visible = [shape for shape in visible if shape not in hidden_by_layer]
        scene_stats = self._poly_stats(visible)
        selected_stats = self._poly_stats(self._selected_mesh_shapes())

        columns = (scene_stats, selected_stats)
        for key, cells in self.poly_cells.items():
            for index, ctrl in enumerate(cells):
                if cmds.control(ctrl, exists=True):
                    cmds.text(ctrl, edit=True, label=self._format_count(columns[index].get(key, 0)))

    def _is_render_mesh(self, node):
        shapes = cmds.listRelatives(node, shapes=True, type="mesh", fullPath=True) or []
        for shp in shapes:
            try:
                if not cmds.getAttr(shp + ".intermediateObject"):
                    return True
            except Exception:
                pass
        return False

    def _is_curve(self, node):
        return bool(cmds.listRelatives(
            node, shapes=True, type=("nurbsCurve", "bezierCurve"), fullPath=True
        ))

    def _top_group(self, node):
        """Group cha cao nhất, đi ngược từ node lên đến khi hết parent."""
        if not node or not cmds.objExists(node):
            return None
        current = node.split(".")[0]
        if cmds.objectType(current, isAType="shape"):
            parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
            if not parents:
                return None
            current = parents[0]
        while True:
            parents = cmds.listRelatives(current, parent=True, fullPath=True) or []
            if not parents:
                return current
            current = parents[0]

    def _collect_under_top_groups(self, seeds, kind):
        """Lấy mọi mesh hoặc curve nằm dưới group cha cuối cùng của các seed."""
        tops = []
        for node in seeds:
            top = self._top_group(node)
            if top and top not in tops:
                tops.append(top)

        found = []
        for top in tops:
            candidates = [top]
            candidates.extend(
                cmds.listRelatives(top, allDescendents=True, type="transform", fullPath=True) or []
            )
            for candidate in candidates:
                if kind == "mesh" and self._is_render_mesh(candidate):
                    found.append(candidate)
                elif kind == "curve" and self._is_curve(candidate):
                    found.append(candidate)
        return list(set(found))

    def _select_under_top_groups(self, seeds, kind, empty_warning):
        if not seeds:
            cmds.warning(empty_warning)
            return

        targets = self._collect_under_top_groups(seeds, kind)
        if not targets:
            cmds.warning(empty_warning)
            return

        cmds.select(targets, replace=True)
        self._reveal_in_outliner()
        if kind == "mesh":
            om.MGlobal.displayInfo(
                u"Đã chọn {0} mesh.".format(len(targets))
            )
        else:
            om.MGlobal.displayInfo(
                u"Đã chọn {0} curve.".format(len(targets))
            )

    def select_all_meshes(self):
        seeds = self.total_meshes if hasattr(self, "total_meshes") else []
        self._select_under_top_groups(seeds, "mesh", u"Không có mesh nào được chọn.")

    def select_all_curves(self):
        seeds = self.total_curves if hasattr(self, "total_curves") else []
        self._select_under_top_groups(seeds, "curve", u"Không có đường curve được chọn.")

    def select_top_groups(self):
        meshes = self.total_meshes if hasattr(self, "total_meshes") else []
        curves = self.total_curves if hasattr(self, "total_curves") else []
        seeds = list(meshes) + list(curves)
        if not seeds:
            cmds.warning(u"Hãy chọn mesh hoặc curve.")
            return

        groups = []
        for node in seeds:
            top = self._top_group(node)
            if top and top not in groups:
                groups.append(top)
        if not groups:
            cmds.warning(u"Không tìm thấy group.")
            return

        cmds.select(groups, replace=True)
        self._reveal_in_outliner()
        om.MGlobal.displayInfo(
            u"Đã chọn {0} group.".format(len(groups))
        )

    def _reveal_in_outliner(self):
        """Cuộn Outliner tới selection, cùng lệnh phím F (fitPanel)."""
        def _scroll():
            panels = cmds.getPanel(type="outlinerPanel") or []
            for panel in panels:
                try:
                    cmds.outlinerEditor(panel, edit=True, showSelected=True)
                except Exception:
                    pass
        # Chờ Outliner cập nhật highlight rồi mới cuộn.
        cmds.evalDeferred(_scroll)

# Hàm gọi nhanh tool
def show_counter():
    MT_SelectionCounter()

if __name__ == "__main__":
    show_counter()