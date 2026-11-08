# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import sys
import maya.cmds as cmds
import maya.mel as mel

def onMayaDroppedPythonFile(*args, **kwargs):
    """Hàm đặc biệt để tự động chạy khi người dùng kéo thả file này vào màn hình Maya"""
    install_to_shelf()

def get_clean_command(module_name, func_name, tool_dir):
    tool_dir_safe = tool_dir.replace("\\", "/")
    return (
        "import sys\n"
        "if '{0}' not in sys.path:\n"
        "    sys.path.insert(0, '{0}')\n"
        "import {1}\n"
        "if sys.version_info[0] < 3:\n"
        "    reload({1})\n"
        "else:\n"
        "    __import__('importlib').reload({1})\n"
        "{1}.{2}()"
    ).format(tool_dir_safe, module_name, func_name)

def install_to_shelf():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        document_dir = cmds.internalVar(userScriptDir=True)
        current_dir = os.path.join(document_dir, "MT_HairTools")
        
    # 1. Thiết lập đường dẫn Icon cho cả 2 bộ công cụ
    hair_icon_path = os.path.join(current_dir, "icons", "MT_HairTools_icon.png").replace("\\", "/")
    if not os.path.exists(hair_icon_path):
        hair_icon_path = "pythonFamily.png"

    replace_icon_path = os.path.join(current_dir, "icons", "MT_ReplaceMesh_icon.png").replace("\\", "/")
    if not os.path.exists(replace_icon_path):
        replace_icon_path = "pythonFamily.png"

    # 2. Đăng ký RunTimeCommands & Hotkeys cho MT_HairTools
    commands = {
        "MT_SetProxy_RTC": "set_proxy",
        "MT_SnapCurve_RTC": "snap_curve",
        "MT_SnapCV0_RTC": "snap_cv0",
        "MT_SetGuides_RTC": "set_guides",
        "MT_GenerateHair_RTC": "generate_curves",
        "MT_Distribute_RTC": "distribute_curves",
        "MT_Randomize_RTC": "randomize_curves",
        "MT_AlignHair_RTC": "align_and_deform_curves",
        "MT_SelectionCounterUI_RTC": "show_counter"
    }

    category = "CustomHairTools"
    for rtc_name, func_name in commands.items():
        if cmds.runTimeCommand(rtc_name, exists=True):
            cmds.runTimeCommand(rtc_name, edit=True, delete=True)
            
        module_name = (
            "SourceCode.Logic.MT_SelectionCounter"
            if rtc_name == "MT_SelectionCounterUI_RTC"
            else "SourceCode.UI.MT_HairTools"
        )
        cmds.runTimeCommand(rtc_name, 
                            annotation="Custom Hair Tool command", 
                            command=get_clean_command(module_name, func_name, current_dir),
                            commandLanguage="python", 
                            category=category)
        
        name_cmd = rtc_name + "_NameCmd"
        cmds.nameCommand(name_cmd, annotation=rtc_name, command=rtc_name)

    try:
        cmds.hotkey(keyShortcut='3', altModifier=True, name="MT_SnapCurve_RTC_NameCmd")
        cmds.hotkey(keyShortcut='4', altModifier=True, name="MT_SnapCV0_RTC_NameCmd")
        cmds.hotkey(keyShortcut='0', name="MT_SelectionCounterUI_RTC_NameCmd")
    except Exception:
        pass

    # 3. Kiểm tra Shelf hiện tại và dọn các nút cũ (tránh nhân đôi nút khi cài lại)
    gShelfTopLevel = mel.eval('$tmpVar=$gShelfTopLevel')
    if not cmds.tabLayout(gShelfTopLevel, exists=True):
        return cmds.warning(u"Không tìm thấy giao diện Shelf của Maya.")

    current_shelf = cmds.tabLayout(gShelfTopLevel, query=True, selectTab=True)
    shelf_path = gShelfTopLevel + '|' + current_shelf
    
    hair_annotation = "MT Hair Grooming Tools"
    replace_annotation = "MT Replace Mesh Tool"

    children = cmds.shelfLayout(shelf_path, query=True, childArray=True) or []
    for child in children:
        if cmds.objectTypeUI(child) == 'shelfButton':
            ann = cmds.shelfButton(child, query=True, annotation=True)
            if ann in [hair_annotation, replace_annotation]:
                cmds.deleteUI(child)

    # 4. Tạo 2 nút bấm trên Shelf
    cmds.setParent(shelf_path)
    
    # Nút 1: MT_HairTools
    cmds.shelfButton(
        annotation=hair_annotation,
        image1=hair_icon_path,
        command=get_clean_command("SourceCode.UI.MT_HairTools", "show_ui", current_dir),
        sourceType="python"
    )
    
    # Nút 2: MT_ReplaceMesh
    cmds.shelfButton(
        annotation=replace_annotation,
        image1=replace_icon_path,
        command=get_clean_command("SourceCode.UI.MT_ReplaceMesh", "MT_ReplaceMesh", current_dir),
        sourceType="python"
    )

    # # 5. Khởi chạy thử UI sau khi cài đặt
    # current_dir_safe = current_dir.replace("\\", "/")
    # if current_dir_safe not in sys.path:
    #     sys.path.insert(0, current_dir_safe)
        
    # from SourceCode.UI import MT_HairTools
    # if sys.version_info[0] < 3:
    #     reload(MT_HairTools)
    # else:
    #     __import__('importlib').reload(MT_HairTools)
    # MT_HairTools.show_ui()
    
    # Hộp thoại xác nhận hoàn tất
    cmds.confirmDialog(title="Installation", 
                       message=u"Cài đặt thành công MT_HairTools và MT_ReplaceMesh", 
                       button=["OK"])

if __name__ == "__main__":
    install_to_shelf()