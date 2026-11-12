# -*- coding: utf-8 -*-
"""
Sinh file stub (.pyi) cho thư viện Maya để Pylance trong VS Code hiểu maya.cmds, maya.mel và maya.api.*.

Maya chỉ nạp các hàm của maya.cmds khi đang chạy, còn maya.api.OpenMaya được viết bằng C++ (.pyd),
nên Pylance đọc file thật sẽ báo lỗi giả kiểu '"button" is not a known attribute of module "maya.cmds"'.
Script này chạy trong mayapy, đọc trực tiếp danh sách hàm, tham số và lớp từ Maya rồi ghi ra stub.

Cách chạy (PowerShell hoặc Git Bash):
    $env:PYTHONIOENCODING = "utf-8"
    & "C:\\Program Files\\Autodesk\\Maya2023\\bin\\mayapy.exe" gen_maya_stubs.py C:\\Users\\<user>\\maya-typings
"""
import importlib
import inspect
import keyword
import os
import re
import sys

import maya.standalone
maya.standalone.initialize(name="python")
import maya.cmds as cmds
import maya.mel as mel

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "maya-typings")
HEADER = ["# File stub tự sinh từ Maya %s bằng mayapy, phục vụ Pylance." % cmds.about(version=True),
          "from typing import Any"]
API_MODULES = ["OpenMaya", "OpenMayaAnim", "OpenMayaFX", "OpenMayaRender", "OpenMayaUI"]
# API 1.0 (maya.OpenMaya...): Maya chỉ cài file .pyc và .pyd, Pylance không đọc được nên cũng cần stub.
API1_MODULES = ["OpenMaya", "OpenMayaAnim", "OpenMayaFX", "OpenMayaMPx", "OpenMayaRender", "OpenMayaUI"]
FLAG_RE = re.compile(r"^\s+-(\w+)\s+-(\w+)", re.M)


def valid(name):
    return name.isidentifier() and not keyword.iskeyword(name)


def write(relative_path, lines):
    path = os.path.join(OUT, *relative_path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------- maya.cmds / maya.mel
def flags_of(name):
    """Lấy tên cờ dài và ngắn của một lệnh từ cmds.help."""
    try:
        text = cmds.help(name) or ""
    except Exception:
        return []
    names = []
    for short, long in FLAG_RE.findall(text):
        for flag in (long, short):
            if flag not in names and valid(flag) and flag not in ("args", "kwargs"):
                names.append(flag)
    return names


def build_cmds():
    lines = HEADER + [""]
    count = 0
    for name in sorted(dir(cmds)):
        if name.startswith("_") or not valid(name) or not callable(getattr(cmds, name)):
            continue
        # Giữ **kwargs để không bao giờ báo lỗi giả với cờ mà cmds.help không liệt kê.
        params = ["*args: Any"] + ["%s: Any = ..." % f for f in flags_of(name)] + ["**kwargs: Any"]
        lines.append("def %s(%s) -> Any: ..." % (name, ", ".join(params)))
        count += 1
    write("maya/cmds/__init__.pyi", lines)

    mel_lines = HEADER + [""]
    for name in sorted(dir(mel)):
        if not name.startswith("_") and valid(name) and callable(getattr(mel, name)):
            mel_lines.append("def %s(*args: Any, **kwargs: Any) -> Any: ..." % name)
    write("maya/mel/__init__.pyi", mel_lines)
    print("maya.cmds: %d hàm" % count)


# ---------------------------------------------------------------- maya.api.*
KEPT_DUNDERS = ("__init__", "__getitem__", "__setitem__", "__len__", "__iter__", "__add__", "__sub__",
                "__mul__", "__neg__", "__eq__", "__ne__", "__call__")


def qualified_base(base, current, package, siblings):
    """Tên lớp cha để ghi vào stub, kèm tên module nếu lớp cha nằm ở module API khác cùng package."""
    if base is object:
        return None
    # So theo tên ngắn: lớp API 2.0 có thể mang __module__ là "OpenMaya" thay vì "maya.api.OpenMaya".
    short = (getattr(base, "__module__", "") or "").split(".")[-1]
    if short == current:
        return base.__name__
    if short in siblings:
        return "%s.%s" % (short, base.__name__)
    return None


def class_lines(cls, indent="    "):
    lines = []
    for name, value in sorted(cls.__dict__.items()):
        if (name.startswith("__") and name not in KEPT_DUNDERS) or not valid(name):
            continue
        type_name = type(value).__name__
        if type_name in ("builtin_function_or_method", "staticmethod"):
            lines += [indent + "@staticmethod",
                      indent + "def %s(*args: Any, **kwargs: Any) -> Any: ..." % name]
        elif type_name == "classmethod_descriptor" or isinstance(value, classmethod):
            lines += [indent + "@classmethod",
                      indent + "def %s(cls, *args: Any, **kwargs: Any) -> Any: ..." % name]
        elif callable(value) or type_name in ("method_descriptor", "wrapper_descriptor"):
            lines.append(indent + "def %s(self, *args: Any, **kwargs: Any) -> Any: ..." % name)
        elif isinstance(value, bool):
            lines.append(indent + "%s: bool" % name)
        elif isinstance(value, (int, float, str)):
            lines.append(indent + "%s: %s" % (name, type(value).__name__))
        else:
            lines.append(indent + "%s: Any" % name)
    return lines or [indent + "..."]


def build_api_module(short, package="maya.api", siblings=API_MODULES):
    """Sinh stub cho 1 module API. package: "maya.api" (API 2.0) hoặc "maya" (API 1.0)."""
    module = importlib.import_module("%s.%s" % (package, short))
    lines = HEADER + ["from %s import %s" % (package, m) for m in siblings if m != short] + [""]

    classes = [(n, v) for n, v in vars(module).items() if inspect.isclass(v) and valid(n)]
    classes.sort(key=lambda item: (len(item[1].__mro__), item[0]))
    for name, cls in classes:
        bases = [b for b in (qualified_base(b, short, package, siblings) for b in cls.__bases__) if b]
        lines.append("class %s(%s):" % (name, ", ".join(bases)) if bases else "class %s:" % name)
        lines += class_lines(cls)
        lines.append("")

    for name, value in sorted(vars(module).items()):
        if name.startswith("_") or not valid(name) or inspect.isclass(value) or inspect.ismodule(value):
            continue
        if callable(value):
            lines.append("def %s(*args: Any, **kwargs: Any) -> Any: ..." % name)
        elif isinstance(value, (int, float, str)):
            lines.append("%s: %s" % (name, type(value).__name__))
    write("%s/%s.pyi" % (package.replace(".", "/"), short), lines)
    print("%s.%s: %d lớp" % (package, short, len(classes)))


def build_api():
    # Có __init__.pyi thì Pylance coi maya.api là package thường và ưu tiên stub hơn module thật.
    write("maya/api/__init__.pyi", ["# File stub tự sinh, đánh dấu maya.api là package thường."])
    for short in API_MODULES:
        try:
            build_api_module(short)
        except ImportError:
            print("Bỏ qua maya.api.%s (bản Maya này không có)." % short)


def build_api1():
    for short in API1_MODULES:
        try:
            build_api_module(short, package="maya", siblings=API1_MODULES)
        except ImportError:
            print("Bỏ qua maya.%s (bản Maya này không có)." % short)


build_cmds()
build_api()
build_api1()
print("Đã ghi stub vào:", OUT)
maya.standalone.uninitialize()
