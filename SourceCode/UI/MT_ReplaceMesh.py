# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import sys
import maya.cmds as cmds
import maya.api.OpenMaya as om

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from SourceCode.Logic import replace_mesh_logic as logic
if sys.version_info[0] < 3:
    reload(logic)
else:
    __import__('importlib').reload(logic)

def color01(r, g, b):
    return (r/255.0, g/255.0, b/255.0)
# Kích thước cố định khít với UI
winWidth = 380 
winHeight = 556 
btn_H = 26
btn_W = 168 # Kích thước chính xác cho 2 nút đứng cạnh nhau trong cửa sổ 380px



class MT_ReplaceMesh(logic.ReplaceMeshLogic):
    def __init__(self):
        logic.ReplaceMeshLogic.__init__(self)
        self.build_ui()
        self.setup_scriptjob()

    def build_ui(self):
        if cmds.window(self.window_name, exists=True):
            cmds.deleteUI(self.window_name)
            
        self.window = cmds.window(self.window_name, title=self.title, widthHeight=(winWidth, winHeight), sizeable=True)
        cmds.scriptJob(uiDeleted=[self.window, self.cleanup_scriptjob])
        
        cmds.columnLayout(adjustableColumn=True, columnAttach=('both', 8), rowSpacing=6)
        
        # ==========================================
        # PHẦN 1: REPLACE MESH TO PLACE HOLDER
        # ==========================================
        cmds.separator(height=5, style='none')
        replaceMesh_frame = cmds.frameLayout(label="1. Replace Mesh To Place Holder", collapsable=True, bgc=color01(33, 41, 84), marginHeight=6, marginWidth=6)
        cmds.columnLayout(adjustableColumn=True, parent=replaceMesh_frame, rowSpacing=6)
        cmds.text(label=u"Hãy quét những Mesh muốn dùng để thay thế vị trí cho các đối\ntượng Place Holder. Sau đó ấn Select And Save Library Mesh.", align="left", font="boldLabelFont")
        
        cmds.rowColumnLayout(numberOfColumns=2, columnSpacing=[(2, 6)])
        cmds.button(label="Clear Library Mesh", w=130, h=btn_H, command=lambda *args: self.clear_library_memory())
        self.btn_load_source = cmds.button(label="Select And Save Library Mesh [0]", bgc=color01(128, 128, 128), w=winWidth-170, h=btn_H, command=lambda *args: self.load_sources_to_memory())
        cmds.setParent('..')
        
        cmds.separator(h=2, style='in')
        cmds.text(label=u"Quét chọn các đường Curve, ấn Curve Crossings để tạo Place Holder\n(locator) tại những vị trí các Curve đi qua nhau.", align="left", font="boldLabelFont")
        self.fld_cross_tol = cmds.floatSliderGrp(label=u"Tolerance:  ", columnWidth3=(70, 50, 150), adjustableColumn=3, field=True, min=0.01, max=20.0, fieldMaxValue=1000.0, value=4.0, precision=3, step=0.01)
        cmds.button(label="Create Placeholder For Curve Crossings", h=btn_H, command=lambda *args: self.find_curve_crossings())
        cmds.rowColumnLayout(numberOfColumns=4, columnWidth=[(1, 166), (2, 58), (3, 58), (4, 58)], columnSpacing=[(2, 4), (3, 4), (4, 4)])
        cmds.button(label="Mirror", h=btn_H, bgc=color01(238, 137, 38), command=lambda *args: self.run_mirror())
        self.btn_mirror_x = cmds.button(label="X", h=btn_H, bgc=color01(128, 128, 128), command=lambda *args: self.toggle_mirror_axis("x"))
        self.btn_mirror_y = cmds.button(label="Y", h=btn_H, bgc=color01(128, 128, 128), command=lambda *args: self.toggle_mirror_axis("y"))
        self.btn_mirror_z = cmds.button(label="Z", h=btn_H, bgc=color01(128, 128, 128), command=lambda *args: self.toggle_mirror_axis("z"))
        cmds.setParent('..')

        cmds.separator(h=2, style='in')
        cmds.text(label=u"Quét tất cả các đối tượng Place Holder muốn thay thế.\nSau đó ấn Replace Mesh From Library To Placeholder.", align="left", font="boldLabelFont")  
        
        # Nút bật/tắt chế độ giữ lại Placeholder
        self.btn_keep_ph = cmds.button(label="Keep Placeholder Mesh [OFF]", bgc=color01(128, 128, 128), h=btn_H, command=lambda *args: self.toggle_keep_placeholder())
        
        cmds.button(label="Replace Mesh From Library To Placeholder", bgc=color01(238, 137, 38), h=btn_H, command=lambda *args: self.apply_snap())
        cmds.text(label=u"LƯU Ý:\nNút này được thiết kế để có thể thay thế 1 cách ngẫu nhiên từ tập hợp\nnhững Mesh được chọn vào vị trí của Place Holder.\nTrong trường hợp muốn thay thế chính xác Mesh mong muốn, bạn có thể\nlựa chọn 1 Mesh và ấn Select And Save Library Mesh.\nSau đó chọn các Place Holder để thay thế chính xác bằng Mesh đó.", align="left", font="obliqueLabelFont")
        cmds.setParent('..')
        cmds.setParent('..')

        # ==========================================
        # PHẦN 2: REPLACE MESH TO CURVES & TINH CHỈNH
        # ==========================================
        replaceMeshToCurve_frame = cmds.frameLayout(label="2. Replace Mesh To Curves", collapsable=True, collapse=True, bgc=color01(33, 41, 84), marginHeight=6, marginWidth=6)
        cmds.columnLayout(adjustableColumn=True, parent=replaceMeshToCurve_frame, rowSpacing=6)
        cmds.text(label=u"Chọn Mesh và ấn Select And Save Curve Mesh.", align="left", font="boldLabelFont")
        cmds.rowColumnLayout(numberOfColumns=2, columnSpacing=[(2, 6)])
        cmds.button(label="Clear Curve Mesh", w=130, h=btn_H, command=lambda *args: self.clear_warp_memory())
        self.btn_load_warp_source = cmds.button(label="Select And Save Curve Mesh [0]", bgc=color01(128, 128, 128), w=winWidth-170, h=btn_H, command=lambda *args: self.load_warp_sources_to_memory())
        cmds.setParent('..')
        cmds.text(label=u"Quét chọn các đường Curve muốn thay thế.\nSau đó ấn Replace Mesh To Curves.", align="left", font="boldLabelFont")
        cmds.button(label=u"Replace Mesh To Curves", bgc=color01(238, 137, 38), h=btn_H, command=lambda *args: self.apply_warp())
        cmds.text(label=u"LƯU Ý:\nNút này được thiết kế để có thể thay thế 1 cách ngẫu nhiên từ tập hợp\nnhững Mesh được chọn vào vị trí của những đường Curve.\nTrong trường hợp muốn thay thế chính xác Mesh mong muốn, bạn có thể\nlựa chọn 1 Mesh và các đường Curve để thay thế chính xác bằng Mesh đó.", align="left", font="obliqueLabelFont")
        cmds.separator(height=2, style='in')

        cmds.text(label=u"Tinh chỉnh Mesh đang chọn:", align="left", font="boldLabelFont")
        self.sld_tx = cmds.floatSliderGrp(label=u"Trái/Phải (Translate X):     ", columnWidth3=(140, 50, 150), adjustableColumn=3, field=True, min=-50, max=50, value=0, precision=3, step=0.001, dragCommand=lambda *args: self.update_pmv(1, self.sld_tx), changeCommand=lambda *args: self.update_pmv(1, self.sld_tx))                                  
        self.sld_ty = cmds.floatSliderGrp(label=u"Lên/Xuống (Translate Y): ", columnWidth3=(140, 50, 150), adjustableColumn=3, field=True, min=-50, max=50, value=0, precision=3, step=0.001, dragCommand=lambda *args: self.update_pmv(2, self.sld_ty), changeCommand=lambda *args: self.update_pmv(2, self.sld_ty))
        self.sld_length_scale = cmds.floatSliderGrp(label=u"Co giãn (Length Scale):   ", columnWidth3=(140, 50, 150), adjustableColumn=3, field=True, min=0.001, max=2.0, value=1.0, precision=3, step=0.001, dragCommand=lambda *args: self.update_warp('lengthScale', self.sld_length_scale), changeCommand=lambda *args: self.update_warp('lengthScale', self.sld_length_scale))
        self.sld_scale = cmds.floatSliderGrp(label=u"Độ dày (Inflate):               ", columnWidth3=(140, 50, 150), adjustableColumn=3, field=True, min=0.1, max=5.0, value=1.0, precision=3, step=0.001, dragCommand=lambda *args: self.update_pmv_scale(self.sld_scale), changeCommand=lambda *args: self.update_pmv_scale(self.sld_scale))
        self.sld_rotation = cmds.floatSliderGrp(label=u"Xoay (Rotation):               ", columnWidth3=(140, 50, 150), adjustableColumn=3, field=True, min=-360, max=360, value=0, precision=3, step=0.001, dragCommand=lambda *args: self.update_warp('rotation', self.sld_rotation), changeCommand=lambda *args: self.update_warp('rotation', self.sld_rotation))
        cmds.setParent('..')
        cmds.setParent('..')
        
        # ==========================================
        # PHẦN 3: EXPORT (ZBRUSH PIPELINE)
        # ==========================================
        export_frame = cmds.frameLayout(label="3. Export (To ZBrush Keep Subdiv & Detail)", collapsable=True, collapse=True, bgc=color01(33, 41, 84), marginHeight=6, marginWidth=6)
        cmds.columnLayout(adjustableColumn=True, parent=export_frame, rowSpacing=6)
        cmds.text(label=u"Để có thể xuất các Mesh đã được Replace và đưa sang Zbrush mà\nvẫn có thể lấy lại được Detail.\nĐầu tiên hãy chọn 1 thư mục gốc để xuất các mesh OBJ ra đó!", align="left", font="boldLabelFont")
        self.tf_root_folder = cmds.textFieldButtonGrp(label=u"Root Folder: ", text="", buttonLabel=u"Browse...", columnWidth3=(75, 211, 60), adjustableColumn=2, buttonCommand=self.browse_root_folder)
        cmds.separator(height=2, style='in')

        cmds.text(label=u"Tiếp đó hãy chọn các Mesh Gốc đã dùng để Replace trước đó.\nSau đó ấn Export To Root Folder.", align="left", font="boldLabelFont")
        cmds.button(label=u"Export To Root Folder", bgc=color01(57, 146, 255), h=btn_H, command=lambda *args: self.export_to_zbrush())
        cmds.text(label=u"LƯU Ý:\nTrong thư mục gốc được chỉ định, mỗi Mesh Gốc xuất ra sẽ nằm trong\n1 thư mục con có tên thư mục là tên của Mesh đó.\n\nQUAN TRỌNG!!!\nTrong Zbrush, hãy CHỌN ĐÚNG SUBTOOL của Mesh được xuất ra.\nMở Zscript - Load, sau đó tìm tới thư mục con của Mesh vừa được xuất\nra. Chọn file .TXT để chạy Zscript.\nĐợi 1 chút là toàn bộ các Mesh sẽ được load vào Zbrush và vẫn\ngiữ nguyên Subdiv và Detail!", align="left", font="obliqueLabelFont") 
        cmds.setParent('..')
        cmds.setParent('..')

        self.restore_libraries_from_scene()
        cmds.showWindow(self.window)

    def setup_scriptjob(self):
        self.job_id = cmds.scriptJob(event=["SelectionChanged", self.sync_ui], parent=self.window_name)
        cmds.scriptJob(event=["SceneOpened", self.restore_libraries_from_scene], parent=self.window_name)
        cmds.scriptJob(event=["NewSceneOpened", self.restore_libraries_from_scene], parent=self.window_name)

    def cleanup_scriptjob(self):
        if self.job_id and cmds.scriptJob(exists=self.job_id):
            cmds.scriptJob(kill=self.job_id, force=True)

    def _paint_library_button(self, button, count, filled, empty):
        if not button or not cmds.button(button, exists=True):
            return
        if count:
            cmds.button(button, edit=True, label=filled.format(count), bgc=color01(118, 180, 255))
        else:
            cmds.button(button, edit=True, label=empty, bgc=color01(128, 128, 128))

    def toggle_mirror_axis(self, axis):
        self.mirror_axes[axis] = not self.mirror_axes[axis]
        buttons = {"x": self.btn_mirror_x, "y": self.btn_mirror_y, "z": self.btn_mirror_z}
        color = color01(118, 180, 255) if self.mirror_axes[axis] else color01(128, 128, 128)
        cmds.button(buttons[axis], edit=True, bgc=color)

    def toggle_keep_placeholder(self):
        self.keep_placeholder = not self.keep_placeholder
        if self.keep_placeholder:
            cmds.button(self.btn_keep_ph, edit=True, label="Keep Placeholder Mesh [ON]", bgc=color01(118, 180, 255))
            om.MGlobal.displayInfo(u"Keep Placeholder Mesh: BẬT (Giữ lại các Placeholder sau khi thay thế).")
        else:
            cmds.button(self.btn_keep_ph, edit=True, label="Keep Placeholder Mesh [OFF]", bgc=color01(128, 128, 128))
            om.MGlobal.displayInfo(u"Keep Placeholder Mesh: TẮT (Xóa các Placeholder sau khi thay thế).")

    def browse_root_folder(self):
        folder = cmds.fileDialog2(fileMode=3, caption=u"Chọn thư mục gốc để chứa các Folder Export")
        if folder:
            cmds.textFieldButtonGrp(self.tf_root_folder, edit=True, text=folder[0])

    def sync_ui(self):
        # Bỏ qua khi logic đang xử lý hàng loạt (vd Replace Mesh To Curves) để không chạy lại cho từng mesh.
        if getattr(self, "_suspend_sync_ui", False):
            return
        sel = cmds.ls(selection=True, long=True)
        if not sel: return
        obj = sel[-1] 
        
        pmv_scale, pmv_trans = self.get_pmv_nodes(obj)
        t_ax1, t_ax2, s_ax1, s_ax2 = self.get_cross_axes(obj)
        
        if pmv_trans:
            if cmds.attributeQuery(t_ax1, node=pmv_trans, exists=True):
                cmds.floatSliderGrp(self.sld_tx, edit=True, value=cmds.getAttr("{0}.{1}".format(pmv_trans, t_ax1)))
            if cmds.attributeQuery(t_ax2, node=pmv_trans, exists=True):
                cmds.floatSliderGrp(self.sld_ty, edit=True, value=cmds.getAttr("{0}.{1}".format(pmv_trans, t_ax2)))
                
        if pmv_scale:
            if cmds.attributeQuery(s_ax1, node=pmv_scale, exists=True):
                cmds.floatSliderGrp(self.sld_scale, edit=True, value=cmds.getAttr("{0}.{1}".format(pmv_scale, s_ax1)))
                
        warps = cmds.ls(cmds.listHistory(obj), type='curveWarp')
        if warps:
            warp = warps[0]
            for attr, sld in [('rotation', self.sld_rotation), ('lengthScale', self.sld_length_scale)]:
                if cmds.attributeQuery(attr, node=warp, exists=True):
                    cmds.floatSliderGrp(sld, edit=True, value=cmds.getAttr("{0}.{1}".format(warp, attr)))
