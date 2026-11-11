# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import sys
import maya.cmds as cmds

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from SourceCode.Logic import hair_tools_logic as logic
if sys.version_info[0] < 3:
    reload(logic)
else:
    __import__('importlib').reload(logic)


def update_proxy_ui_display():
    if cmds.textField("mt_proxy_textfield", exists=True):
        proxies = cmds.ls('*.isHairCardProxy', objectsOnly=True)
        if proxies:
            cmds.textField("mt_proxy_textfield", edit=True, text=proxies[0])
        else:
            # Sửa chuỗi rỗng "" thành dòng thông báo của bạn
            cmds.textField("mt_proxy_textfield", edit=True, text="Chưa Set/ Đã gỡ bỏ Proxy")


def set_proxy(*args):
    return logic.set_proxy(update_proxy_ui_display)


def clear_proxy(*args):
    return logic.clear_proxy(update_proxy_ui_display)

def snap_curve(*args, **kwargs):
    return logic.snap_curve(*args, **kwargs)

def snap_cv0(*args, **kwargs):
    return logic.snap_cv0(*args, **kwargs)

def set_guides(*args, **kwargs):
    return logic.set_guides(*args, **kwargs)

def clear_guides(*args, **kwargs):
    return logic.clear_guides(*args, **kwargs)

def distribute_curves(*args, **kwargs):
    return logic.distribute_curves(*args, **kwargs)

def randomize_curves(*args, **kwargs):
    return logic.randomize_curves(*args, **kwargs)

def random_flip_uv(*args, **kwargs):
    return logic.random_flip_uv(*args, **kwargs)

def generate_curves(*args, **kwargs):
    return logic.generate_curves(*args, **kwargs)

def align_and_deform_curves(*args, **kwargs):
    return logic.align_and_deform_curves(*args, **kwargs)

def color01(r, g, b):
    return (r/255.0, g/255.0, b/255.0)

# Kích thước cố định khít với UI (không dùng scrollLayout)
winWidth = 380 
winHeight = 730 
btn_H = 26
btn_W = 168 # Kích thước chính xác cho 2 nút đứng cạnh nhau trong cửa sổ 380px

def show_ui():
    win_name = "MTHairToolsUI"
    if cmds.window(win_name, exists=True): 
        cmds.deleteUI(win_name)
        
    window = cmds.window(win_name, title="MT Hair Tools", widthHeight=(winWidth, winHeight), sizeable=True)
    
    # Căn lề padding hai bên cực kỳ sạch sẽ
    column_main = cmds.columnLayout(adjustableColumn=True, columnAttach=('both', 8), rowSpacing=6)
    
    cmds.separator(height=5, style='none')
    
    # ----------------------------------------
    # 1. Nhóm Proxy Mesh Tools
    # ----------------------------------------
    proxy_frame = cmds.frameLayout(label=" 1. Proxy Mesh ", collapsable=True, parent=column_main, bgc=color01(33, 41, 84), font="boldLabelFont", marginHeight=6, marginWidth=6)
    cmds.columnLayout(adjustableColumn=True, parent=proxy_frame, rowSpacing=6)
    
    cmds.text(label="Đầu tiên hãy chọn 1 Object và Set Proxy Mesh\n(LƯU Ý: Object cần phải được Freeze Transform trước!!!)", align="center", font="boldLabelFont")
    
    # Giải pháp linh hoạt không đè: Nút có width cứng, TextField tự co giãn
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2, columnAlign=(1, 'center'))
    cmds.button(label="Set Proxy Mesh", w=130, h=btn_H,bgc=color01(238, 137, 38), annotation="Chỉ cần chọn Set Proxy 1 lần và Save File\nLần sau mở lại Maya không cần chọn lại nữa",command=lambda _: set_proxy())
    cmds.textField("mt_proxy_textfield", editable=False, text="", h=btn_H)
    cmds.setParent('..')
    cmds.button(label="Clear Proxy Mesh", h=btn_H, annotation="Loại bỏ mesh Proxy",command=lambda _: clear_proxy())
    cmds.setParent('..')

    cmds.separator(h=2, style='in')
    cmds.text(label="Sau khi đã chọn Mesh Proxy\nCó thể thực hiện Snap Curve theo bề mặt Proxy", align="left", font="boldLabelFont") 
    # Hai nút chia đôi chính xác
    cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, btn_W), (2, btn_W)], columnSpacing=[(2, 6)])
    cmds.button(label="Snap Cur2Prx", h=btn_H,annotation="Snap cả đường Curve", command=lambda _: snap_curve())
    cmds.button(label="Snap cv[0]2Prx", h=btn_H, annotation="Chỉ Snap điểm gốc của Curve", command=lambda _: snap_cv0())
    cmds.setParent('..')
    
    cmds.text(label="Phím tắt mặc định (có thể gán lại phím tắt khác trong Hotkeys):\nAlt + 3 (Snap Cur2Prx)\nAlt + 4 (Snap cv[0]2Prx)", align="left", font="obliqueLabelFont")
    cmds.setParent('..')
    
    # ----------------------------------------
    # 2. Nhóm Flip Curves
    # ----------------------------------------
    flip_frame = cmds.frameLayout(label=" 2. Flip Curves Keep Form", collapsable=True, parent=column_main, bgc=color01(33, 41, 84), font="boldLabelFont", marginHeight=6, marginWidth=6)
    cmds.columnLayout(adjustableColumn=True, parent=flip_frame, rowSpacing=6)
    cmds.text(
        label="Chọn Curve, bật các trục cần lật rồi nhấn Flip Keep Form.",
        align="left",
        font="boldLabelFont"
    )

    flip_axes = {"X": False, "Y": False, "Z": False}
    flip_axis_buttons = {}

    def toggle_flip_axis(axis):
        flip_axes[axis] = not flip_axes[axis]
        color = color01(118, 180, 255) if flip_axes[axis] else color01(128, 128, 128)
        cmds.button(flip_axis_buttons[axis], edit=True, bgc=color)

    def make_toggle_command(axis):
        # Dùng hàm tạo closure thay cho "lambda *args, axis=axis" vì Python 2.7 không hỗ trợ cú pháp đó.
        return lambda *args: toggle_flip_axis(axis)

    def run_flip_keep_form(*args):
        axes = [axis for axis in ("X", "Y", "Z") if flip_axes[axis]]
        logic.flip_keep_form(axes)

    def run_mirror(*args):
        axes = [axis for axis in ("X", "Y", "Z") if flip_axes[axis]]
        logic.mirror_curves(axes)

    cmds.rowColumnLayout(numberOfColumns=3, columnWidth=[(1, 109), (2, 109), (3, 109)], columnSpacing=[(2, 6), (3, 6)])
    for axis in ("X", "Y", "Z"):
        flip_axis_buttons[axis] = cmds.button(
            label=axis,
            h=btn_H,
            bgc=color01(128, 128, 128),
            command=make_toggle_command(axis)
        )
    cmds.setParent('..')
    # Hai nút Mirror (trái) và Flip Keep Form (phải) chia đôi bề rộng, dùng chung 3 nút trục X/Y/Z ở trên.
    flip_button_row = cmds.formLayout(height=btn_H)
    btn_flip = cmds.button(
        label="Flip Keep Form",
        h=btn_H,
        bgc=color01(238, 137, 38),
        command=run_flip_keep_form
    )
    btn_mirror = cmds.button(
        label="Mirror",
        h=btn_H,
        bgc=color01(57, 146, 255),
        annotation="Đẩy các CV của Curve sang vị trí đối xứng qua các trục đang bật",
        command=run_mirror
    )
    cmds.formLayout(
        flip_button_row,
        edit=True,
        attachForm=[(btn_mirror, "left", 0), (btn_mirror, "top", 0), (btn_mirror, "bottom", 0),
                    (btn_flip, "right", 0), (btn_flip, "top", 0), (btn_flip, "bottom", 0)],
        attachPosition=[(btn_mirror, "right", 3, 50), (btn_flip, "left", 3, 50)],
    )
    cmds.setParent('..')
    cmds.text(label=u"LƯU Ý:\nNút này được thiết kế để có thể lật một đường Curve theo trục nhưng\nvẫn cố gắng giữ lại hình dạng của đường Curve.\nNếu đã Set Proxy Mesh, đường Curve sau khi lật sẽ được điều chỉnh để\nkhông đâm vào Proxy Mesh.", align="left", font="obliqueLabelFont")
    cmds.setParent('..')

    # ----------------------------------------
    # 3. Nhóm Guides & Generation
    # ----------------------------------------
    guides_frame = cmds.frameLayout(label=" 3. Guides & Generation ", collapsable=True, collapse=True, parent=column_main, bgc=color01(33, 41, 84), font="boldLabelFont", marginHeight=6, marginWidth=6)
    cmds.columnLayout(adjustableColumn=True, parent=guides_frame, rowSpacing=6)
    
    cmds.text(label="Hãy chọn các đường Curve muốn dùng làm Guide", align="left", font="boldLabelFont")
    
    cmds.rowColumnLayout(numberOfColumns=2, columnWidth=[(1, btn_W), (2, btn_W)], columnSpacing=[(2, 6)])
    cmds.button(label="Set Guides", h=btn_H, bgc=color01(238, 137, 38),annotation="Các đường Guide sau khi được set\nsẽ không cần set lại mỗi lần mở file", command=lambda _: set_guides())
    cmds.button(label="Clear Guides", h=btn_H,annotation="Loại bỏ đường Curve để nó\nkhông còn là Guide nữa", command=lambda _: clear_guides())
    cmds.setParent('..')
    
    cmds.separator(h=2, style='in')
    cmds.text(label="Chọn các mặt (Faces) trên Mesh Proxy để tạo Curve\nCác đường Curve sinh ra sẽ định hướng theo Guide", align="left", font="boldLabelFont")
    
    # Đã đổi sang 2 dòng Slider và căn lề (85, 45, 150) cho thẳng hàng với các slider bên dưới
    cmds.intSliderGrp('mt_hair_count', label='Curve Count    ', field=True, minValue=10, maxValue=1000, value=100, step=1, columnWidth3=(85, 45, 150))
    cmds.floatSliderGrp('mt_hair_len', label='Curve Length   ', field=True, minValue=0.1, maxValue=50.0, value=10.0, step=0.1, columnWidth3=(85, 45, 150))

    # Nút bấm đã được cập nhật logic lấy giá trị v=True để phù hợp với SliderGrp
    cmds.button(label="GENERATE CURVES", h=32,annotation="Tạo các đường Curve từ mặt được chọn\nCác đường Curve sẽ đi theo hướng của Guide", bgc=color01(57, 146, 255), command=lambda _: generate_curves(cmds.intSliderGrp('mt_hair_count', q=True, v=True), cmds.floatSliderGrp('mt_hair_len', q=True, v=True), 6))
    cmds.setParent('..')
    
    # ----------------------------------------
    # 4. Nhóm Groom Modifiers
    # ----------------------------------------
    modifiers_frame = cmds.frameLayout(label=" 4. Groom Modifiers ", collapsable=True, collapse=True, parent=column_main, bgc=color01(33, 41, 84), font="boldLabelFont", marginHeight=6, marginWidth=6)
    cmds.columnLayout(adjustableColumn=True, parent=modifiers_frame, rowSpacing=6)
    cmds.text(label="Có thể chọn các đường Curve để phân bố lại cho đồng đều\n(LƯU Ý: Nên chọn từng vùng nhỏ để tốc độ xử lý được trơn tru!!!)", align="left", font="boldLabelFont")
    cmds.button(label="Distribute / Relax Curves", h=btn_H, annotation="Phân bố lại khoảng cách\ncác đường curve đồng đều", command=lambda _: distribute_curves(iterations=15))
    
    cmds.separator(h=2, style='in')
    
    # Khối Randomize - Bọc trong rowLayout tự co giãn
    cmds.text(label="Đảo UV ngẫu nhiên của các thẻ tóc đang có UV giống nhau\nHãy quét chọn Curve, sau đó dùng Random Flip UV", align="left", font="boldLabelFont")
    cmds.button(label="Random Flip UV", h=btn_H,annotation="Đảo UV ngẫu nhiên của các\nthẻ tóc được chọn", command=lambda _: random_flip_uv())
    cmds.text(label="Nếu muốn các đường Curve xoay và xê dịch 1 chút cho ngẫu nhiên\nHãy sử dụng Random Transform", align="left", font="boldLabelFont")
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2)
    cmds.button(label="Random Transform\n(Rot and Move)", w=130, h=52,annotation="Ngẫu nhiên xoay và dịch chuyển\ncác đường Curve 1 khoảng nhỏ", command=lambda _: randomize_curves(cmds.floatSliderGrp('mt_hair_rand_rot', q=True, v=True), cmds.floatSliderGrp('mt_hair_rand_move', q=True, v=True)))
    
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.floatSliderGrp('mt_hair_rand_rot', label='Rotation ', field=True, minValue=0.0, maxValue=2.0, value=0.3, step=0.1, columnWidth3=(80, 45, 70))
    cmds.floatSliderGrp('mt_hair_rand_move', label='Position ', field=True, minValue=0.0, maxValue=2.0, value=0.1, step=0.05, columnWidth3=(80, 45, 70))
    cmds.setParent('..')
    cmds.setParent('..')
    # Khối Align - Bọc trong rowLayout tự co giãn
    cmds.separator(h=2, style='in')
    cmds.text(label="Nếu muốn các đường Curve xoay lại hướng theo Guide\nHãy sử dụng Align To Guide", align="left", font="boldLabelFont")
    cmds.checkBox('mt_hair_match', label="Deform to Guide Shape",annotation="Tuỳ chọn bẻ hình dáng của đường Curve theo Guide", value=True)
    cmds.checkBox('mt_hair_pres_len', label="Preserve Hair Length",annotation="Tuỳ chọn giữ cố định chiều dài của đường Curve", value=False)
    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2)
    cmds.button(label="Align To Guides", w=130, h=52,annotation="Định hướng lại các đường Curve\ntheo các đường Guide", command=lambda _: align_and_deform_curves(cmds.checkBox('mt_hair_match', q=True, v=True), cmds.checkBox('mt_hair_pres_len', q=True, v=True), cmds.floatSliderGrp('mt_hair_blend', q=True, v=True), cmds.floatSliderGrp('mt_hair_lift', q=True, v=True)))
    cmds.columnLayout(adjustableColumn=True, rowSpacing=2)
    cmds.floatSliderGrp('mt_hair_blend', label='Blend Falloff  ', field=True, minValue=1.0, maxValue=5.0, value=2.0, columnWidth3=(80, 45, 70))
    cmds.floatSliderGrp('mt_hair_lift', label='Min Lift Angle', field=True, minValue=0.0, maxValue=90.0, value=15.0, columnWidth3=(80, 45, 70))
    
    cmds.setParent('..')
    
    cmds.showWindow(window)
    update_proxy_ui_display()