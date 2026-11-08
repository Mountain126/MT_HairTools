# -*- coding: utf-8 -*-
# Maya 2018 (Python 2.7) va Maya 2020+ (Python 3).
# Khong dung unicode_literals: Maya 2018 can byte string cho ten event/flag.
import sys
import maya.cmds as cmds
import maya.OpenMaya as om
import maya.OpenMayaUI as omui

def color01(r, g, b):
    return (r/255.0, g/255.0, b/255.0)

# Chieu rong noi dung duoc can chinh de cua so co tong be rong 380 px.
WINDOW_WIDTH = 380
SIDE_MARGIN = 10
POLY_LABEL_WIDTH = 54
POLY_VALUE_WIDTH = 142
POLY_TABLE_WIDTH = POLY_LABEL_WIDTH + (POLY_VALUE_WIDTH * 2) + 12
CONTENT_MIN_WIDTH = WINDOW_WIDTH - 16
TITLE_BG = "#212954"
ROW_SPACING = 6
TEXT_HEIGHT = 26
# 5 separator + 3 dong chu + bang 6 dong + 2 hang nut + khoang cach giua 11 phan tu
KNOWN_MIN_HEIGHT = (
    (4 * 5)
    + (TEXT_HEIGHT * 3)
    + ((TEXT_HEIGHT * 6) + (4 * 5))
    + 28
    + 28
    + (ROW_SPACING * 10)
    + 2
)

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
        self.build_ui()
        self.setup_scriptjob()

    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
        if cmds.workspaceControl(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)

        # workspaceControl chan minimumWidth/Height that su, cmds.window thi khong.
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

        # Hai cot: mesh dang hien trong scene / mesh dang chon.
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
        
        # Các nút hỗ trợ chọn lọc nhanh
        # formLayout chia 50/50 de hai nut luon lap day be rong cua so.
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
        # Chạy cập nhật ngay lần đầu mở, rồi khoa kich thuoc toi thieu
        self.update_counter()
        cmds.evalDeferred(self._style_readouts, lowestPriority=True)
        cmds.evalDeferred(self._fit_and_lock_size, lowestPriority=True)

    def setup_scriptjob(self):
        # SelectionChanged khi đổi vùng chọn; Undo/Redo khi hình học đổi mà selection giữ nguyên
        for event in ("SelectionChanged", "Undo", "Redo"):
            job_id = cmds.scriptJob(event=[event, self.update_counter], parent=self.main_layout)
            self.job_ids.append(job_id)
        # Maya van cho keo floating panel nho hon minimum trong mot so ban, nen kep lai khi idle.
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

    def _ui_exists(self):
        return cmds.workspaceControl(self.window_name, exists=True)

    def _qt_modules(self):
        try:
            from PySide2 import QtCore, QtWidgets
        except ImportError:
            from PySide6 import QtCore, QtWidgets
        return QtCore, QtWidgets

    def _wrap(self, ptr, widget_cls):
        if not ptr:
            return None
        try:
            from shiboken2 import wrapInstance
        except ImportError:
            from shiboken6 import wrapInstance
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
        """Chu trang, dam, nen o rieng cho so de tach khoi nen xam cua Maya."""
        if not control or not cmds.control(control, exists=True):
            return
        try:
            from PySide2 import QtCore, QtWidgets
        except ImportError:
            from PySide6 import QtCore, QtWidgets
        widget = self._wrap(omui.MQtUtil.findControl(control), QtWidgets.QLabel)
        if widget is None:
            return
        widget.setAttribute(QtCore.Qt.WA_StyledBackground, True)
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
        self._watch_display_layers()
        self._style_readouts()
        self._base_min_w = self._label_min_width()
        self._clamp_if_smaller()

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
        """Cap nhat lai khi bat/tat visibility cua display layer."""
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
        """Mesh nam trong layer dang tat, ke ca layer gan tren group cha.

        Outliner van hien visibility cua chinh mesh, nhung viewport khong ve
        khi display layer cua group bi an.
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
        """Group cha cao nhat, di nguoc tu node len den khi het parent."""
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
        """Lay moi mesh hoac curve nam duoi group cha cuoi cung cua cac seed."""
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
        """Cuon Outliner toi selection, cung lenh phim F (fitPanel)."""
        def _scroll():
            panels = cmds.getPanel(type="outlinerPanel") or []
            for panel in panels:
                try:
                    cmds.outlinerEditor(panel, edit=True, showSelected=True)
                except Exception:
                    pass
        # Cho Outliner cap nhat highlight roi moi cuon.
        cmds.evalDeferred(_scroll)

# Hàm gọi nhanh tool
def show_counter():
    MT_SelectionCounter()

if __name__ == "__main__":
    show_counter()