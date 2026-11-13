# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import maya.cmds as cmds
import maya.OpenMaya as om
import maya.mel as mel
import random
import os
import math
import maya.api.OpenMaya as om2
import sys
from SourceCode.Logic import MT_MirrorMesh
if sys.version_info[0] < 3:
    reload(MT_MirrorMesh)
else:
    __import__('importlib').reload(MT_MirrorMesh)


CURVE_UUID_ATTR = "sourceCurveUUID"
# Đóng dấu trên mesh gốc. Giá trị = UUID của chính node đó.
# Duplicate copy attribute nhưng Maya cấp UUID mới, nên bản copy không khớp và không vào thư viện.
LIBRARY_MESH_ATTR = "libraryMesh"
WARP_LIBRARY_MESH_ATTR = "wrapLibraryMesh"
# Góc rotation tool tự tính cho curveWarp lúc tạo mesh wrap. Khi replace lại, phần chênh giữa rotation
# hiện tại và góc này là phần người dùng đã chỉnh tay, được cộng vào góc tính mới cho mesh thay thế.
# Các attribute của curveWarp được kế thừa khi chọn mesh wrap cũ để replace.
_WARP_INHERIT_ATTRS = ("rotation", "envelope", "twistRotation", "offset", "lengthScale", "samplingAccuracy",
                       "maxScale", "flipAxis", "loopClosedCurves", "keepLength", "alignmentMode")
_LIBRARY_NICE = {
    LIBRARY_MESH_ATTR: u"Library Mesh",
    WARP_LIBRARY_MESH_ATTR: u"Wrap Library Mesh",
}
# Tên cũ, chỉ để đọc scene đã đóng dấu trước khi đổi tên.
_LIBRARY_ATTR_ALIASES = {
    LIBRARY_MESH_ATTR: ("mtLibraryMeshUUID",),
    WARP_LIBRARY_MESH_ATTR: ("mtWarpLibraryMeshUUID",),
}

def _apply_stored_mirror(src, dst):
    """Mesh nguồn có attribute mirror thì đảo đỉnh bản replace cho đúng hướng."""
    try:
        # Đã import từ đầu
        MT_MirrorMesh.apply_stored_mirror(src, dst)
    except Exception as exc:
        cmds.warning(u"Không áp được mirror khi replace '{0}': {1}".format(src, exc))

def _apply_mirror_value(dst, value):
    try:
        # Đã import từ đầu
        MT_MirrorMesh.apply_mirror_value(dst, value)
    except Exception as exc:
        cmds.warning(u"Không áp được mirror khi replace: {0}".format(exc))

def _set_string_attr(node, name, value):
    if not cmds.attributeQuery(name, node=node, exists=True):
        cmds.addAttr(node, longName=name, dataType="string")
    cmds.setAttr("{0}.{1}".format(node, name), value, type="string")

def _get_uuid(node):
    ids = cmds.ls(node, uuid=True)
    return ids[0] if ids else None

def _resolve_uuid(uuid):
    """Trả về long path hiện tại của node theo UUID (None nếu không còn tồn tại)."""
    nodes = cmds.ls(uuid, long=True) if uuid else None
    return nodes[0] if nodes else None

def _remove_string_attr(node, name):
    if not cmds.objExists(node) or not cmds.attributeQuery(name, node=node, exists=True):
        return
    plug = "{0}.{1}".format(node, name)
    try:
        cmds.setAttr(plug, lock=False)
    except Exception:
        pass
    try:
        cmds.deleteAttr(node, attribute=name)
    except Exception:
        pass

def _library_attr_names(attr_name):
    names = [attr_name]
    names.extend(_LIBRARY_ATTR_ALIASES.get(attr_name, ()))
    return names

def _get_string_attr(node, name):
    if not cmds.objExists(node) or not cmds.attributeQuery(name, node=node, exists=True):
        return ""
    try:
        return cmds.getAttr("{0}.{1}".format(node, name)) or ""
    except Exception:
        return ""

def _set_library_value(node, attr_name, value):
    nice = _LIBRARY_NICE.get(attr_name, attr_name)
    if not cmds.attributeQuery(attr_name, node=node, exists=True):
        cmds.addAttr(node, longName=attr_name, niceName=nice, dataType="string")
    else:
        try:
            cmds.addAttr("{0}.{1}".format(node, attr_name), edit=True, niceName=nice)
        except Exception:
            pass
    cmds.setAttr("{0}.{1}".format(node, attr_name), value, type="string")

def _stamp_library_attr(node, attr_name):
    """Ghi UUID hiện tại của node. Chỉ node còn đúng UUID này mới được nhận lại sau khi mở file."""
    uuid = _get_uuid(node)
    if not uuid:
        return None
    _set_library_value(node, attr_name, uuid)
    for alias in _LIBRARY_ATTR_ALIASES.get(attr_name, ()):
        _remove_string_attr(node, alias)
    return uuid

def _clear_library_attr(attr_name):
    """Chỉ gỡ dấu trên mesh gốc. Mesh con giữ attribute để còn biết thuộc mesh gốc nào khi export."""
    for name in _library_attr_names(attr_name):
        for node in cmds.ls("*.{0}".format(name), long=True, objectsOnly=True) or []:
            stored = _get_string_attr(node, name)
            current = _get_uuid(node)
            if stored and current and stored == current:
                _remove_string_attr(node, name)

def _collect_library_uuids(attr_name):
    """Bỏ qua mesh duplicate: attribute bị copy nhưng UUID node không còn trùng giá trị đã đóng dấu."""
    found = []
    seen = set()
    nodes = []
    known = set()
    for name in _library_attr_names(attr_name):
        for node in cmds.ls("*.{0}".format(name), long=True, objectsOnly=True) or []:
            if node not in known:
                known.add(node)
                nodes.append(node)
    for node in nodes:
        stored = ""
        for name in _library_attr_names(attr_name):
            stored = _get_string_attr(node, name)
            if stored:
                break
        current = _get_uuid(node)
        if not stored or not current or stored != current or current in seen:
            continue
        seen.add(current)
        found.append(current)
        if not _get_string_attr(node, attr_name):
            try:
                _stamp_library_attr(node, attr_name)
            except Exception:
                pass
    return found

def _export_source_ids(node):
    """UUID mesh gốc. Mesh con đọc từ Library Mesh / Wrap Library Mesh; mesh gốc là UUID của chính nó."""
    ids = []
    for attr_name in (LIBRARY_MESH_ATTR, WARP_LIBRARY_MESH_ATTR):
        for name in _library_attr_names(attr_name):
            stored = _get_string_attr(node, name)
            if stored and stored not in ids:
                ids.append(stored)
    if not ids:
        own_uuid = _get_uuid(node)
        if own_uuid:
            ids.append(own_uuid)
    return ids

def _has_export_mesh(node):
    """True nếu transform còn ít nhất một mesh shape không phải intermediate (shape thật để xuất OBJ).
    Transform chỉ còn shape intermediate (vd. sau Combine/Separate có history) vẫn giữ attribute Library
    nhưng xuất ra OBJ rỗng, nên phải bỏ qua."""
    if cmds.objectType(node, isAType="mesh"):
        return not cmds.getAttr("{0}.intermediateObject".format(node))
    shapes = cmds.listRelatives(node, shapes=True, type="mesh", noIntermediate=True, fullPath=True) or []
    return bool(shapes)

def _build_zbrush_import_script(obj_paths):
    """Sinh nội dung ZScript chạy một lần để nhập lần lượt các file OBJ vào ZBrush (đã thử trên ZBrush 2021).

    Cách làm:
    1. Copy subtool đang chọn. Copy không hỏi nhân cả folder như Duplicate khi folder đang đóng
       (lúc đó ZBrush coi cả folder là mục đang chọn, và zscript không bấm được nút mở folder vì
       nút folder đóng không tồn tại với IPress).
    2. Chọn subtool cuối danh sách rồi Paste một lần làm subtool mẫu: Paste đặt subtool mới ngay dưới
       subtool đang chọn, nên mẫu nằm dưới cùng. Nếu subtool cuối nằm trong folder thì đẩy mẫu ra ngoài.
    3. Với mỗi OBJ: chọn mẫu, Duplicate (mẫu nằm ngoài folder nên không bị hỏi), bản sao nằm ngay dưới
       mẫu; hạ SDiv về 1, Import OBJ rồi nâng SDiv lên cao nhất.
    4. Xóa mẫu để không thừa subtool.

    Duplicate đặt bản sao ngay dưới mẫu, đẩy các bản sao trước xuống dưới, nên chạy OBJ theo thứ tự
    ngược để danh sách cuối cùng đúng thứ tự file.
    """
    lines = [
        "/* ZBrush Run-Once Script - MT Replace Mesh: Copy selected SubTool & Import OBJs */",
        "[VarDef, mtTplIdx, 0]",
        "[VarDef, mtTplName, \"\"]",
        "[VarDef, mtName, \"\"]",
        "[VarDef, mtOk, 1]",
        "[VarDef, mtIdx, 0]",
        "[VarDef, mtCnt, 0]",
        "[VarDef, mtPrev, 0]",
        "[VarDef, mtPrevFld, 0]",
        "",
        # Tên subtool đang chọn: Tool:Item Info có dấu chấm cuối, bỏ đi (cách macro có sẵn của ZBrush 2021 làm).
        "[RoutineDef, MT_ActiveName,",
        "  [VarSet, mtName, [IGetTitle, Tool:Item Info]]",
        "  [VarSet, mtName, [StrExtract, mtName, 0, [StrLength, mtName] - 2]]",
        "]",
        "",
        # Đẩy subtool đang chọn xuống cuối danh sách và ra khỏi mọi folder.
        # Shift + Move Down (mã 256 = Shift, theo StartupHotkeys.txt: Shift+1 = 49 + 256 = 305)
        # chỉ đưa xuống cuối folder đang chứa nó; bấm tiếp mới ra khỏi folder. Ra khỏi folder
        # có thể không làm đổi số thứ tự (folder không chiếm vị trí trong danh sách), nên phải
        # so cả số thứ tự lẫn folder để biết lần bấm có tác dụng hay không.
        "[RoutineDef, MT_MoveToBottom,",
        "  [VarSet, mtCnt, [SubToolGetCount]]",
        "  [Loop, mtCnt * 2 + 4,",
        "    [VarSet, mtPrev, [SubToolGetActiveIndex]]",
        "    [VarSet, mtPrevFld, [SubToolGetFolderIndex, mtPrev]]",
        "    [If, (mtPrev >= mtCnt - 1) && (mtPrevFld < 0), [LoopExit]]",
        "    [IKeyPress, 256, [IPress, Tool:SubTool:MoveDown]]",
        "    [VarSet, mtIdx, [SubToolGetActiveIndex]]",
        "    [If, (mtIdx == mtPrev) && ([SubToolGetFolderIndex, mtIdx] == mtPrevFld),",
        # Shift không có tác dụng: thử bấm Move Down thường một bậc.
        "      [IPress, Tool:SubTool:MoveDown]",
        "      [VarSet, mtIdx, [SubToolGetActiveIndex]]",
        "      [If, (mtIdx == mtPrev) && ([SubToolGetFolderIndex, mtIdx] == mtPrevFld), [LoopExit]]",
        "    ]",
        "  ]",
        "]",
        "",
        "[RoutineDef, MT_ImportOne,",
        "  [SubToolSelect, mtTplIdx]",
        # Chốt an toàn: subtool ở vị trí mẫu phải đúng tên mẫu, sai thì dừng chứ không Duplicate nhầm.
        "  [RoutineCall, MT_ActiveName]",
        "  [If, [StrLength, mtName] != [StrLength, mtTplName],",
        "    [VarSet, mtOk, 0]",
        "  ]",
        "  [If, mtOk,",
        "    [If, [StrFind, mtTplName, mtName] != 0, [VarSet, mtOk, 0]]",
        "  ]",
        "  [If, mtOk,",
        "    [IPress, Tool:SubTool:Duplicate]",
        "    [ISet, Tool:Geometry:SDiv, 1]",
        "    [FileNameSetNext, mtObjPath]",
        "    [IPress, Tool:Import]",
        "    [ISet, Tool:Geometry:SDiv, [IGetMax, Tool:Geometry:SDiv]]",
        "  ]",
        ", mtObjPath]",
        "",
        "[If, 1,",
        "  [IShowActions, 0]",
        # Copy 1 lần. Paste đặt subtool mới ngay dưới subtool đang chọn, nên chọn subtool cuối
        # danh sách rồi mới Paste để mẫu nằm dưới cùng, không chen vào folder của subtool gốc.
        "  [IPress, Tool:SubTool:Copy]",
        "  [SubToolSelect, [SubToolGetCount] - 1]",
        "  [IPress, Tool:SubTool:Paste]",
        "  [SubToolSelect, [SubToolGetCount] - 1]",
        # Subtool cuối nằm trong folder thì mẫu cũng vào folder đó: đẩy ra ngoài (không có folder thì bỏ qua).
        "  [RoutineCall, MT_MoveToBottom]",
        "  [VarSet, mtTplIdx, [SubToolGetActiveIndex]]",
        "  [RoutineCall, MT_ActiveName]",
        "  [VarSet, mtTplName, mtName]",
        # Chốt an toàn: mẫu còn nằm trong folder đang đóng thì Duplicate sẽ nhân cả folder, nên dừng.
        # Bit đóng (1024) nằm trên subtool đầu folder, folder index là số thứ tự của subtool đó.
        "  [VarSet, mtIdx, [SubToolGetFolderIndex, mtTplIdx]]",
        "  [If, mtIdx >= 0,",
        "    [VarSet, mtCnt, [SubToolGetStatus, mtIdx]]",
        "    [If, (INT(mtCnt / 1024) - 2 * INT(mtCnt / 2048)) == 1,",
        # Dừng hẳn bằng Exit; không tự xóa mẫu vì Delete trong folder đóng cũng có thể xóa cả folder.
        "      [Note, \"MT Replace Mesh: the template SubTool is inside a closed folder. Open that folder, delete the template and run the script again.\"]",
        "      [Exit]",
        "    ]",
        "  ]",
    ]
    for obj_file in reversed(obj_paths):
        lines.append("  [If, mtOk, [RoutineCall, MT_ImportOne, \"{0}\"]]".format(obj_file))
    lines += [
        # Xóa mẫu. Delete hỏi xác nhận nên giữ phím '2' khi bấm, đúng như macro có sẵn của ZBrush 2021 (Create Instance Subtool).
        "  [SubToolSelect, mtTplIdx]",
        "  [RoutineCall, MT_ActiveName]",
        "  [If, mtOk,",
        "    [If, [StrFind, mtTplName, mtName] == 0,",
        "      [If, [StrLength, mtName] == [StrLength, mtTplName],",
        "        [IKeyPress, '2', [IPress, Tool:SubTool:Delete]]",
        "      ]",
        "    ]",
        # Báo xong rồi tự tắt sau 2 giây (tham số thứ 3 của Note là thời gian hiển thị), để người dùng
        # biết script đã chạy hết. mtOk còn 1 nghĩa là mọi OBJ đều đã import nên số lượng biết trước từ Python.
        "    [Note, \"MT Replace Mesh: done, imported {0} OBJ.\", , 2]".format(len(obj_paths)),
        "  ,",
        # Thông báo trong ZBrush để tiếng Anh không dấu: file .txt ghi bằng encoding mặc định
        # của hệ thống nên ký tự tiếng Việt có thể làm lỗi ghi file hoặc hiện sai trong ZBrush.
        "    [Note, [StrMerge, \"MT Replace Mesh: stopped, the template SubTool was not found: \", mtTplName]]",
        "  ]",
        "]",
    ]
    return "\n".join(lines) + "\n"

def _copy_library_marks(src, dst):
    """Mesh con giữ UUID của mesh gốc trên Library Mesh / Wrap Library Mesh, không gán sourceUUID."""
    _remove_string_attr(dst, "sourceUUID")
    for attr_name in (LIBRARY_MESH_ATTR, WARP_LIBRARY_MESH_ATTR):
        value = ""
        for name in _library_attr_names(attr_name):
            value = _get_string_attr(src, name)
            if value:
                break
        if not value:
            continue
        _set_library_value(dst, attr_name, value)
        for alias in _LIBRARY_ATTR_ALIASES.get(attr_name, ()):
            _remove_string_attr(dst, alias)

def _freeze_curve_if_scale_uneven(curve):
    # Chỉ chạy khi Scale X, Y, Z lệch nhau. Scale đều (kể cả khác 1) thì bỏ qua.
    sx, sy, sz = cmds.getAttr("{0}.scale".format(curve))[0]
    if abs(sx - sy) < 1e-4 and abs(sy - sz) < 1e-4 and abs(sx - sz) < 1e-4:
        return

    # 1. Lấy danh sách các điểm CV và lưu tọa độ World Space hiện tại
    cvs = cmds.ls("{0}.cv[*]".format(curve), flatten=True)
    world_positions = [cmds.xform(cv, query=True, worldSpace=True, translation=True) for cv in cvs]

    # 2. Đưa trực tiếp Scale về 1, 1, 1 (Không dùng makeIdentity -> Không mất OUTPUTS)
    cmds.setAttr("{0}.scale".format(curve), 1.0, 1.0, 1.0, type="double3")

    # 3. Đặt các điểm CV về lại đúng tọa độ World Space ban đầu
    for cv, pos in zip(cvs, world_positions):
        cmds.xform(cv, worldSpace=True, translation=pos)

GS_GENERATOR_TYPE = "GSCT_CurveMeshGeneratorNode"
# Attribute của node GS không chép sang node đo (thuộc tính hệ thống, hoặc profile phải để 0 cho card phẳng).
_GS_PROBE_SKIP = ("caching", "frozen", "isHistoricallyInteresting", "nodeState", "profile")


def _gs_generator(curve_shape):
    """Node GSCT_CurveMeshGeneratorNode của GS CurveTools dựng card từ curve này (không có thì trả về None)."""
    for n in cmds.listConnections(curve_shape, source=False, destination=True) or []:
        if cmds.nodeType(n) == GS_GENERATOR_TYPE:
            return n
    return None


def _signed_angle_around(a, b, axis):
    """Góc có dấu (độ) quay từ a sang b quanh trục axis, sau khi chiếu cả hai lên mặt phẳng vuông góc axis."""
    a = a - axis * (a * axis)
    b = b - axis * (b * axis)
    if a.length() < 1e-8 or b.length() < 1e-8:
        return None
    a.normalize()
    b.normalize()
    return math.degrees(math.atan2((a ^ b) * axis, a * b))


class _GsOrientProbe(object):
    """Đo góc cần gán cho curveWarp.rotation để card khớp với card GS CurveTools.

    GS và curveWarp (chế độ Auto Normals) chọn khung xoay ban đầu khác nhau. Với curve có gốc nằm ngang
    thì hai khung trùng nhau, nhưng với curve có gốc gần song song trục up, khung curveWarp lệch ±90 độ
    và dấu thay đổi theo sai khác rất nhỏ của curve. Vì vậy không quy đổi bằng công thức cố định được.

    Cách đo: một node GS tạm chép thông số của node GS thật (profile = 0 để card phẳng) và một plane
    curveWarp tạm (rotation = 0), cùng nối vào curve. Góc giữa pháp tuyến hai card ở gốc curve chính là
    góc rotation để plane trùng với card GS (đã gồm Orientation, Initial Tangent Axis, Flip Frame).
    Hai node tạm được tạo một lần và dùng lại cho mọi curve, gọi cleanup() để xóa.
    """

    def __init__(self):
        self.gs_node = None
        self.plane = None
        self.warp = None

    def _ensure(self):
        if self.gs_node and cmds.objExists(self.gs_node) and self.plane and cmds.objExists(self.plane):
            return
        self.cleanup()
        self.gs_node = cmds.createNode(GS_GENERATOR_TYPE, name="MT_gsOrientProbe#", skipSelect=True)
        # Plane dài theo X, pháp tuyến +Y: curveWarp Auto chọn trục X (dài nhất) làm chiều dọc curve.
        self.plane = cmds.polyPlane(name="MT_warpOrientProbe#", width=1.0, height=0.1,
                                    subdivisionsX=4, subdivisionsY=1, constructionHistory=False)[0]
        self.warp = cmds.deformer(self.plane, type="curveWarp")[0]
        cmds.setAttr("{0}.keepLength".format(self.warp), 1)

    def cleanup(self):
        for n in (self.gs_node, self.plane):
            if n and cmds.objExists(n):
                try:
                    cmds.delete(n)
                except Exception:
                    pass
        self.gs_node = self.plane = self.warp = None

    def measure(self, curve_shape, generator):
        """Trả về góc (độ) cho curveWarp.rotation với mesh nằm dài theo X, pháp tuyến +Y; lỗi thì trả về None."""
        self._ensure()
        for attr in cmds.listAttr(generator, scalar=True, settable=True) or []:
            if attr in _GS_PROBE_SKIP:
                continue
            try:
                cmds.setAttr("{0}.{1}".format(self.gs_node, attr), cmds.getAttr("{0}.{1}".format(generator, attr)))
            except Exception:
                pass
        cmds.setAttr("{0}.profile".format(self.gs_node), 0)
        cmds.connectAttr("{0}.worldSpace[0]".format(curve_shape), "{0}.inputCurve".format(self.gs_node), force=True)
        cmds.connectAttr("{0}.worldSpace[0]".format(curve_shape), "{0}.inputCurve".format(self.warp), force=True)

        sel = om2.MSelectionList()
        sel.add(curve_shape)
        sel.add("{0}.outputMesh".format(self.gs_node))
        sel.add(self.plane)
        fc = om2.MFnNurbsCurve(sel.getDagPath(0))
        gs_mesh = om2.MFnMesh(sel.getPlug(1).asMObject())
        plane_dag = sel.getDagPath(2)
        plane_dag.extendToShape()
        plane_mesh = om2.MFnMesh(plane_dag)

        # Đo sát gốc curve (card GS dựng từ gốc, curveWarp đặt mesh từ gốc).
        u = fc.findParamFromLength(fc.length() * 0.001)
        p = fc.getPointAtParam(u, om2.MSpace.kWorld)
        t = fc.tangent(u, om2.MSpace.kWorld).normal()
        n_gs = om2.MVector(gs_mesh.getClosestNormal(p, om2.MSpace.kObject)[0])
        n_warp = om2.MVector(plane_mesh.getClosestNormal(p, om2.MSpace.kWorld)[0])
        return _signed_angle_around(n_warp, n_gs, t)


def _safe_dir_name(name):
    return "".join("_" if ch in '<>:"/\\|?*' else ch for ch in name).strip() or "_"

def _curve_fn(curve):
    sel = om2.MSelectionList()
    sel.add(curve)
    dag = sel.getDagPath(0)
    dag.extendToShape()
    return om2.MFnNurbsCurve(dag)

def _sample_curve(curve, samples):
    fn = _curve_fn(curve)
    s, e = fn.knotDomain
    out = []
    for i in range(samples + 1):
        p = fn.getPointAtParam(s + (e - s) * i / float(samples), om2.MSpace.kWorld)
        out.append((p.x, p.y, p.z))
    return out

def _refine_min_distance(fa, fb, lo, hi, iters=40):
    """Golden-section tìm param trên A sao cho khoảng cách tới B nhỏ nhất (chính xác hơn lấy mẫu rời rạc)."""
    s, e = fa.knotDomain
    lo, hi = max(s, lo), min(e, hi)

    def f(t):
        pa = fa.getPointAtParam(t, om2.MSpace.kWorld)
        pb, _ = fb.closestPoint(pa, space=om2.MSpace.kWorld)
        return pa.distanceTo(pb)

    g = 0.381966
    a, b = lo, hi
    c, d = a + g * (b - a), b - g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = a + g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = b - g * (b - a)
            fd = f(d)
    return (a + b) / 2.0

def find_crossings_cylinder(curves, radius=0.5, samples=300, min_angle=0.0, verbose=True, max_overlap=0, misses=None):
    """Mỗi curve có 1 hình trụ giả tưởng bán kính radius. Hai hình trụ giao nhau khi khoảng cách
    giữa 2 curve <= 2*radius. Mỗi vùng giao liên tục gom thành 1 điểm giao, đặt tại trung điểm
    2 điểm gần nhau nhất (đã tinh chỉnh). Bỏ qua cặp chạy song song quá dài (max_overlap) hoặc góc < min_angle.
    Trả về list (curveA, curveB, distance, MPoint, angle)."""
    fns = {c: _curve_fn(c) for c in curves}
    boxes = {}
    for c in curves:
        p = _sample_curve(c, 50)
        boxes[c] = ([min(q[k] for q in p) for k in range(3)], [max(q[k] for q in p) for k in range(3)])
    limit = radius * 2.0

    hits = []
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            ca, cb = curves[i], curves[j]
            na, nb = ca.split("|")[-1], cb.split("|")[-1]
            (amin, amax), (bmin, bmax) = boxes[ca], boxes[cb]
            if any(amin[k] - limit > bmax[k] or bmin[k] - limit > amax[k] for k in range(3)):
                continue
            fa, fb = fns[ca], fns[cb]
            s, e = fa.knotDomain
            n = int(min(3000, max(samples, fa.length() / max(limit * 0.25, 1e-6))))
            step = (e - s) / float(n)

            data = []
            for k in range(n + 1):
                pa = fa.getPointAtParam(min(e, max(s, s + step * k)), om2.MSpace.kWorld)
                pb, _ = fb.closestPoint(pa, space=om2.MSpace.kWorld)
                data.append(pa.distanceTo(pb))

            k = 0
            found_cluster = False
            pair_has_hit = False
            loose = limit * 1.5  # gom vùng rộng hơn ngưỡng, rồi so khoảng cách đã tinh chỉnh với limit
            refined_min = float("inf")
            while k <= n:
                if data[k] > loose:
                    k += 1
                    continue
                start = k
                while k <= n and data[k] <= loose:
                    k += 1
                best = min(range(start, k), key=lambda x: data[x])
                t0 = _refine_min_distance(fa, fb, s + step * max(0, best - 1), s + step * min(n, best + 1))
                t0 = min(e, max(s, t0))
                pa = fa.getPointAtParam(t0, om2.MSpace.kWorld)
                pb, tb = fb.closestPoint(pa, space=om2.MSpace.kWorld)
                d = pa.distanceTo(pb)
                refined_min = min(refined_min, d)
                if d > limit:
                    continue
                found_cluster = True
                ta = fa.tangent(t0, om2.MSpace.kWorld).normal()
                tbv = fb.tangent(tb, om2.MSpace.kWorld).normal()
                ang = math.degrees(math.acos(min(1.0, abs(ta * tbv))))
                overlap_len = (k - start) * step * fa.length() / max(e - s, 1e-9)
                if max_overlap and overlap_len > max_overlap * limit:
                    if verbose:
                        print("BỎ QUA {0} x {1}: chạy song song {2:.2f}, d={3:.3f}".format(na, nb, overlap_len, d))
                    continue
                if ang < min_angle:
                    continue
                mid = om2.MPoint((pa.x + pb.x) / 2.0, (pa.y + pb.y) / 2.0, (pa.z + pb.z) / 2.0)
                hits.append((ca, cb, d, mid, ang))
                pair_has_hit = True
            if refined_min < float("inf") and not pair_has_hit:
                if misses is not None:
                    misses.append((ca, cb))
                if verbose and not found_cluster:
                    print("KHÔNG GIAO {0} x {1}: khoảng cách nhỏ nhất {2:.4f} > 2*radius ({3:.3f}) -> cần tolerance >= {4:.3f}".format(
                        na, nb, refined_min, limit, refined_min / 2.0))
    return hits



class ReplaceMeshLogic(object):
    # Các control UI do lớp con MT_ReplaceMesh tạo ra khi dựng cửa sổ.
    # Khai báo sẵn ở đây để lớp logic tự đứng được và Pylance nhận biết thuộc tính.
    btn_load_source = None
    btn_load_warp_source = None
    fld_cross_tol = None
    tf_root_folder = None

    def __init__(self):
        self.window_name = "MT_ReplaceMeshWindow"
        self.title = "MT Replace Mesh"
        self.job_id = None
        self.source_memory = []
        self.warp_source_memory = []
        self.keep_placeholder = False
        self.mirror_axes = {"x": False, "y": False, "z": False}

    # Các hàm dưới đây do lớp UI MT_ReplaceMesh ghi đè; bản ở đây không làm gì.
    def _paint_library_button(self, button, count, filled, empty):
        """Tô màu và đổi nhãn nút Library theo số mesh đã lưu."""
        pass

    def sync_ui(self):
        """Cập nhật slider theo object đang chọn."""
        pass

    def browse_root_folder(self):
        """Mở hộp thoại chọn thư mục gốc để export."""
        pass

    def restore_libraries_from_scene(self):
        self.source_memory = _collect_library_uuids(LIBRARY_MESH_ATTR)
        self.warp_source_memory = _collect_library_uuids(WARP_LIBRARY_MESH_ATTR)
        self._paint_library_button(
            getattr(self, "btn_load_source", None),
            len(self.source_memory),
            "Select And Save Library Mesh [{0}]",
            "Select And Save Library Mesh [0]",
        )
        self._paint_library_button(
            getattr(self, "btn_load_warp_source", None),
            len(self.warp_source_memory),
            "Select And Save Curve Mesh [{0}]",
            "Select And Save Curve Mesh [0]",
        )

    def get_cross_axes(self, obj):
        t_ax1, t_ax2 = 'tx', 'tz'
        if cmds.attributeQuery("crossAxis1", node=obj, exists=True) and cmds.attributeQuery("crossAxis2", node=obj, exists=True):
            t_ax1 = cmds.getAttr("{0}.crossAxis1".format(obj))
            t_ax2 = cmds.getAttr("{0}.crossAxis2".format(obj))
            
        axis_map = {'tx': 'sx', 'ty': 'sy', 'tz': 'sz'}
        s_ax1 = axis_map.get(t_ax1, 'sx')
        s_ax2 = axis_map.get(t_ax2, 'sz')
        return t_ax1, t_ax2, s_ax1, s_ax2

    def get_pmv_nodes(self, obj):
        if cmds.attributeQuery("pmvScaleNode", node=obj, exists=True) and cmds.attributeQuery("pmvTransNode", node=obj, exists=True):
            s_conns = cmds.listConnections("{0}.pmvScaleNode".format(obj))
            t_conns = cmds.listConnections("{0}.pmvTransNode".format(obj))
            if s_conns and t_conns:
                return s_conns[0], t_conns[0]
        pmvs = cmds.ls(cmds.listHistory(obj), type='polyMoveVertex')
        if pmvs:
            return pmvs[0], pmvs[0]
        return None, None

    def load_sources_to_memory(self):
        sel = cmds.ls(selection=True, long=True) or []
        if not sel:
            cmds.warning(u"Vui lòng chọn ít nhất 1 Mesh để làm Library.")
            return
        _clear_library_attr(LIBRARY_MESH_ATTR)
        uuids = []
        for node in sel:
            try:
                uuid = _stamp_library_attr(node, LIBRARY_MESH_ATTR)
            except Exception as exc:
                cmds.warning(u"Không gắn được Library cho '{0}': {1}".format(node, exc))
                continue
            if uuid:
                uuids.append(uuid)
        self.source_memory = uuids
        self._paint_library_button(
            self.btn_load_source, len(uuids),
            "Select And Save Library Mesh [{0}]", "Select And Save Library Mesh [0]")
        om.MGlobal.displayInfo(u"Đã lưu {0} mesh vào Library. Mở lại file không cần Save Library lại.".format(len(uuids)))

    def clear_library_memory(self):
        _clear_library_attr(LIBRARY_MESH_ATTR)
        self.source_memory = []
        self._paint_library_button(
            self.btn_load_source, 0,
            "Select And Save Library Mesh [{0}]", "Select And Save Library Mesh [0]")
        om.MGlobal.displayInfo(u"Đã xóa Library Mesh và gỡ attribute khỏi mesh.")

    def load_warp_sources_to_memory(self):
        sel = [n for n in cmds.ls(selection=True, long=True) or []
               if (cmds.listRelatives(n, shapes=True, type="mesh", fullPath=True) or [])]
        if not sel:
            cmds.warning(u"Vui lòng chọn ít nhất 1 Mesh để làm Curve Mesh.")
            return
        _clear_library_attr(WARP_LIBRARY_MESH_ATTR)
        uuids = []
        for node in sel:
            try:
                uuid = _stamp_library_attr(node, WARP_LIBRARY_MESH_ATTR)
            except Exception as exc:
                cmds.warning(u"Không gắn được Curve Mesh cho '{0}': {1}".format(node, exc))
                continue
            if uuid:
                uuids.append(uuid)
        self.warp_source_memory = uuids
        self._paint_library_button(
            self.btn_load_warp_source, len(uuids),
            "Select And Save Curve Mesh [{0}]", "Select And Save Curve Mesh [0]")
        om.MGlobal.displayInfo(u"Đã lưu {0} mesh vào Curve Mesh. Mở lại file không cần Save Curve Mesh lại.".format(len(uuids)))

    def clear_warp_memory(self):
        _clear_library_attr(WARP_LIBRARY_MESH_ATTR)
        self.warp_source_memory = []
        self._paint_library_button(
            self.btn_load_warp_source, 0,
            "Select And Save Curve Mesh [{0}]", "Select And Save Curve Mesh [0]")
        om.MGlobal.displayInfo(u"Đã xóa Curve Mesh và gỡ attribute khỏi mesh.")

    def run_mirror(self):
        axes = [axis for axis in ("x", "y", "z") if self.mirror_axes[axis]]
        try:
            # Đã import từ đầu
            MT_MirrorMesh.mirror_selected(axes)
        except Exception as exc:
            cmds.warning(u"Không mirror được: {0}".format(exc))

    def apply_snap(self):
        if not self.source_memory:
            cmds.warning(u"Thư viện đang trống. Vui lòng Select And Save Library Mesh trước.")
            return
            
        placeholders = cmds.ls(selection=True, long=True)
        if not placeholders:
            cmds.warning(u"Vui lòng quét chọn các Placeholder trên màn hình.")
            return

        # --- TỰ ĐỘNG BAKE PIVOT (CHỈ LẤY ORIENTATION) CHO CÁC PLACEHOLDER ---
        try:
            cmds.optionVar(intValue=("bakeCustomPivotPos", 0)) # Tắt Bake Position
            cmds.optionVar(intValue=("bakeCustomPivotOri", 1)) # Bật Bake Orientation
            cmds.optionVar(intValue=("bakeCustomPivot", 2))    # Chế độ 2: Orientation
            mel.eval("BakeCustomPivot;")
        except Exception:
            pass
            
        replaced_meshes = []
        success_count = 0
        
        for ph in placeholders:
            try:
                if not cmds.objExists(ph):
                    continue

                # 1. Kiểm tra Group cha và Display Layer của Placeholder trước khi xử lý
                ph_parents = cmds.listRelatives(ph, parent=True, fullPath=True)
                ph_parent = ph_parents[0] if ph_parents else None

                ph_layers = cmds.listConnections(ph, type="displayLayer") or []
                ph_shapes = cmds.listRelatives(ph, shapes=True, fullPath=True) or []
                for s in ph_shapes:
                    ph_layers.extend(cmds.listConnections(s, type="displayLayer") or [])
                ph_layers = [lyr for lyr in set(ph_layers) if lyr != "defaultLayer"]

                # 2. Đưa Pivot về tâm hình học (Position) và lấy tọa độ + góc xoay (đã Bake)
                # cmds.xform(ph, centerPivots=True)
                ph_pos = cmds.xform(ph, query=True, worldSpace=True, rotatePivot=True)
                ph_rot = cmds.xform(ph, query=True, worldSpace=True, rotation=True)
                
                # 3. Nhân bản Mesh từ Library
                source_uuid = random.choice(self.source_memory)
                source_mesh = _resolve_uuid(source_uuid)
                if not source_mesh:
                    cmds.warning(u"Mesh nguồn (UUID {0}) không còn tồn tại.".format(source_uuid))
                    continue

                source_short = source_mesh.split("|")[-1]
                dup_mesh = cmds.duplicate(source_mesh, returnRootsOnly=True)[0]
                
                if cmds.listRelatives(dup_mesh, parent=True):
                    dup_mesh = cmds.parent(dup_mesh, world=True)[0]

                dup_mesh = cmds.rename(dup_mesh, "{0}_Replaced_#".format(source_short))
                _copy_library_marks(source_mesh, dup_mesh)
                
                # 4. Chuẩn hóa Mesh bản sao và khớp vào vị trí + góc xoay của Placeholder
                cmds.move(0, 0, 0, dup_mesh, absolute=True, rotatePivotRelative=True)
                cmds.makeIdentity(dup_mesh, apply=True, translate=True, rotate=True, scale=True, normal=False)
                _apply_stored_mirror(ph, dup_mesh)
                
                cmds.xform(dup_mesh, worldSpace=True, absolute=True, translation=ph_pos)
                cmds.xform(dup_mesh, worldSpace=True, absolute=True, rotation=ph_rot)

                # 5. Kế thừa Group và Display Layer của Placeholder
                if ph_parent and cmds.objExists(ph_parent):
                    dup_mesh = cmds.parent(dup_mesh, ph_parent)[0]
                else:
                    grp_name = "{0}_Group".format(source_short)
                    if not cmds.objExists(grp_name):
                        cmds.group(empty=True, name=grp_name)
                    dup_mesh = cmds.parent(dup_mesh, grp_name)[0]

                for lyr in ph_layers:
                    if cmds.objExists(lyr):
                        cmds.editDisplayLayerMembers(lyr, dup_mesh, noRecurse=True)

                replaced_meshes.append(dup_mesh)
                
                # 6. Xóa hoặc giữ lại Placeholder
                if not self.keep_placeholder:
                    cmds.delete(ph)

                success_count += 1
                
            except Exception as e:
                cmds.warning(u"Lỗi ở placeholder '{0}': {1}".format(ph, str(e)))
                
        replaced_meshes = [mesh for mesh in replaced_meshes if cmds.objExists(mesh)]
        if replaced_meshes:
            cmds.select(replaced_meshes, replace=True)
            om.MGlobal.displayInfo(u"Thành công! Đã chuẩn hóa tọa độ và thay thế {0} placeholder.".format(success_count))

    def update_pmv(self, axis_num, sld_name):
        val = cmds.floatSliderGrp(sld_name, query=True, value=True)
        for obj in cmds.ls(selection=True, long=True):
            _, pmv_trans = self.get_pmv_nodes(obj)
            if pmv_trans:
                t_ax1, t_ax2, _, _ = self.get_cross_axes(obj)
                target_attr = t_ax1 if axis_num == 1 else t_ax2
                try: cmds.setAttr("{0}.{1}".format(pmv_trans, target_attr), val)
                except: pass

    def update_pmv_scale(self, sld_name):
        val = cmds.floatSliderGrp(sld_name, query=True, value=True)
        for obj in cmds.ls(selection=True, long=True):
            pmv_scale, _ = self.get_pmv_nodes(obj)
            if pmv_scale:
                _, _, s_ax1, s_ax2 = self.get_cross_axes(obj)
                try: 
                    cmds.setAttr("{0}.{1}".format(pmv_scale, s_ax1), val)
                    cmds.setAttr("{0}.{1}".format(pmv_scale, s_ax2), val)
                except: pass

    def update_warp(self, attr, sld_name):
        val = cmds.floatSliderGrp(sld_name, query=True, value=True)
        for obj in cmds.ls(selection=True, long=True):
            warps = cmds.ls(cmds.listHistory(obj), type='curveWarp')
            if warps:
                try: cmds.setAttr("{0}.{1}".format(warps[0], attr), val)
                except: pass

    def _find_curve_orientation(self, curve, curve_shape, verbose=True):
        """Tìm giá trị orientation (số) trên curve, shape hoặc các node nối với curve (vd GS CurveTools).
        verbose=False: không in ra Script Editor (in nhiều dòng làm Maya chậm khi xử lý hàng loạt)."""
        nodes = [curve, curve_shape]
        for src in (curve, curve_shape):
            for n in (cmds.listConnections(src, source=True, destination=True) or []):
                n_full = (cmds.ls(n, long=True) or [n])[0]
                if n_full not in nodes:
                    nodes.append(n_full)
            for n in (cmds.listHistory(src) or []):
                if n not in nodes:
                    nodes.append(n)
        # Kiểu cha/con: GS CurveTools hay gắn attribute lên group/transform cha
        parent = cmds.listRelatives(curve, parent=True, fullPath=True)
        if parent:
            nodes.append(parent[0])

        numeric_types = ("double", "float", "long", "short", "doubleAngle", "doubleLinear")
        for node in nodes:
            try:
                attrs = cmds.listAttr(node) or []
            except Exception:
                continue
            for attr in attrs:
                if "orient" not in attr.lower() or "." in attr:
                    continue
                plug = "{0}.{1}".format(node, attr)
                try:
                    if cmds.getAttr(plug, type=True) not in numeric_types:
                        continue
                    val = cmds.getAttr(plug)
                except Exception:
                    continue
                if verbose:
                    om.MGlobal.displayInfo(u"Orientation lấy từ {0} = {1}".format(plug, val))
                return val

        if verbose:
            om.MGlobal.displayInfo(u"Không tìm thấy attribute Orientation trên curve '{0}'. Các node đã quét: {1}".format(curve, nodes))
        return None

    def find_curve_crossings(self):
        if not self.source_memory:
            cmds.warning(u"Thư viện đang trống. Vui lòng Select And Save Library Mesh trước.")
            return

        curves = [c for c in cmds.ls(selection=True, long=True) or []
                  if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
        if len(curves) < 2:
            cmds.warning(u"Vui lòng chọn ÍT NHẤT 2 đường Curve.")
            return

        for curve in curves:
            _freeze_curve_if_scale_uneven(curve)

        tol = cmds.floatSliderGrp(self.fld_cross_tol, query=True, value=True)
        misses = []
        hits = find_crossings_cylinder(curves, radius=tol, misses=misses)

        grp = "CurveCrossings_Group"
        if not cmds.objExists(grp):
            grp = cmds.group(empty=True, name=grp)
        locs = []
        for ca, cb, d, m, ang in hits:
            loc = cmds.spaceLocator(name="CurveCrossing_#")[0]
            cmds.xform(loc, worldSpace=True, translation=(m.x, m.y, m.z))
            locs.append(cmds.parent(loc, grp)[0])

        missed_curves = []
        for ca, cb in misses:
            for c in (ca, cb):
                if c not in missed_curves and cmds.objExists(c):
                    missed_curves.append(c)

        if locs:
            om.MGlobal.displayInfo(u"Đã tìm thấy {0} điểm giao trên {1} curve (tolerance = {2}).".format(len(locs), len(curves), tol))
            cmds.select(locs, replace=True)
            self.apply_snap()
        else:
            cmds.warning(u"Không tìm thấy điểm giao nào (tolerance = {0}).".format(tol))

        # Chọn lại các curve chưa tìm được điểm giao để người dùng chỉnh Tolerance và chạy lại
        if missed_curves:
            cmds.select(missed_curves, replace=True)
            cmds.warning(u"Còn {0} cặp curve chưa tìm được điểm giao. Đã chọn lại {1} curve đó, hãy tăng Tolerance rồi chạy lại.".format(len(misses), len(missed_curves)))
        elif not locs:
            cmds.select(curves, replace=True)

    def apply_warp(self):
        selection = cmds.ls(selection=True, long=True)
        # Mỗi curve là một việc: (curve, mesh wrap cũ). Mesh cũ = None nghĩa là luồng chọn curve
        # (tính góc xoay từ curve); có mesh cũ nghĩa là luồng chọn mesh (chép thông số mesh cũ).
        curves = []
        old_mesh_by_curve = {}
        missing_curve = []

        for obj in selection:
            # Chọn shape trong Outliner thì quy về transform cha.
            if cmds.objectType(obj, isAType="shape"):
                parents = cmds.listRelatives(obj, parent=True, fullPath=True)
                if not parents:
                    continue
                obj = parents[0]
            shapes = cmds.listRelatives(obj, shapes=True, fullPath=True)
            if not shapes: continue
            if cmds.objectType(shapes[0]) in ["nurbsCurve", "bezierCurve"]:
                if obj not in curves:
                    curves.append(obj)
                continue
            # Mesh đã wrap trước đó: tìm ngược lại curve gốc theo UUID lưu trong sourceCurveUUID,
            # để chọn theo tên trong Outliner thay vì phải tìm curve trong scene.
            if cmds.attributeQuery(CURVE_UUID_ATTR, node=obj, exists=True):
                curve_uuid = cmds.getAttr("{0}.{1}".format(obj, CURVE_UUID_ATTR))
                curve = _resolve_uuid(curve_uuid)
                if curve:
                    if curve not in curves:
                        curves.append(curve)
                    # Chọn cả curve lẫn mesh của nó thì ưu tiên luồng mesh để giữ thông số đã chỉnh.
                    old_mesh_by_curve.setdefault(curve, obj)
                else:
                    missing_curve.append(obj.split("|")[-1])
        jobs = [(c, old_mesh_by_curve.get(c)) for c in curves]

        if missing_curve:
            cmds.warning(u"Không tìm thấy curve gốc (theo {0}) của {1} mesh: {2}".format(
                CURVE_UUID_ATTR, len(missing_curve), ", ".join(missing_curve)))

        mesh_uuids = list(self.warp_source_memory)
        if not mesh_uuids:
            cmds.warning(u"Danh sách Curve Mesh đang trống. Vui lòng chọn Mesh và ấn Select And Save Curve Mesh trước.")
            return
        if not curves:
            cmds.warning(u"Vui lòng chọn ÍT NHẤT 1 Curve hoặc 1 mesh đã wrap (có attribute {0}).".format(CURVE_UUID_ATTR))
            return

        # Tăng tốc khi xử lý nhiều curve: tạm dừng vẽ lại viewport và chặn sync_ui
        # (scriptJob SelectionChanged chạy mỗi lần duplicate làm đổi selection).
        # Gom thành 1 undo chunk để Ctrl+Z hoàn tác cả lần chạy.
        self._suspend_sync_ui = True
        cmds.undoInfo(openChunk=True, chunkName="MT_ReplaceMeshToCurves")
        refresh_suspended = False
        try:
            try:
                cmds.refresh(suspend=True)
                refresh_suspended = True
            except Exception:
                pass
            last_created_mesh, success_count, no_orient = self._apply_warp_curves(jobs, mesh_uuids)
        finally:
            if refresh_suspended:
                cmds.refresh(suspend=False)
            cmds.undoInfo(closeChunk=True)
            self._suspend_sync_ui = False

        if no_orient:
            om.MGlobal.displayInfo(u"Có {0} curve không tìm thấy attribute Orientation, dùng rotation mặc định.".format(no_orient))
        if last_created_mesh and cmds.objExists(last_created_mesh):
            cmds.select(last_created_mesh)
            self.sync_ui()
            om.MGlobal.displayInfo(u"Thành công! Đã tạo Curve Warp cho {0} đường curve.".format(success_count))

    def _capture_wrap_tweaks(self, old_mesh):
        """Đọc các thông số người dùng đã tinh chỉnh trên mesh wrap cũ để mesh thay thế kế thừa lại.
        Trả về None nếu mesh không có curveWarp (không phải mesh wrap)."""
        warps = cmds.ls(cmds.listHistory(old_mesh) or [], type="curveWarp")
        if not warps:
            return None
        warp = warps[0]
        data = {"warp": {}, "ramps": {}}

        # Gồm cả rotation: luồng chọn mesh lấy nguyên góc xoay của mesh cũ, không tính lại từ curve.
        for attr in _WARP_INHERIT_ATTRS:
            try:
                data["warp"][attr] = cmds.getAttr("{0}.{1}".format(warp, attr))
            except Exception:
                pass

        # Ramp Scale Curve / Twist Curve: lưu từng điểm (position, value).
        for ramp in ("scaleCurve", "twistCurve"):
            points = []
            for idx in cmds.getAttr("{0}.{1}".format(warp, ramp), multiIndices=True) or []:
                try:
                    pos, val = cmds.getAttr("{0}.{1}[{2}]".format(warp, ramp, idx))[0]
                except Exception:
                    continue
                points.append((pos, val))
            if points:
                data["ramps"][ramp] = points

        # Slider Trái/Phải, Lên/Xuống, Độ dày: lưu theo trục cắt ngang (crossAxis1/2) chứ không theo tx/ty/tz,
        # vì mesh mới có thể nằm dài theo trục khác nên crossAxis khác mesh cũ.
        pmv_scale, pmv_trans = self.get_pmv_nodes(old_mesh)
        t_ax1, t_ax2, s_ax1, s_ax2 = self.get_cross_axes(old_mesh)
        cross_trans = cross_scale = None
        if pmv_trans:
            try:
                cross_trans = (cmds.getAttr("{0}.{1}".format(pmv_trans, t_ax1)),
                               cmds.getAttr("{0}.{1}".format(pmv_trans, t_ax2)))
            except Exception:
                pass
        if pmv_scale:
            try:
                cross_scale = (cmds.getAttr("{0}.{1}".format(pmv_scale, s_ax1)),
                               cmds.getAttr("{0}.{1}".format(pmv_scale, s_ax2)))
            except Exception:
                pass

        # Transform của mesh (trường hợp người dùng dịch/xoay/scale trực tiếp mesh sau khi wrap).
        xf = {}
        for attr in ("translate", "rotate", "scale"):
            try:
                xf[attr] = cmds.getAttr("{0}.{1}".format(old_mesh, attr))[0]
            except Exception:
                pass
        return {"warp": data["warp"], "ramps": data["ramps"], "cross_trans": cross_trans,
                "cross_scale": cross_scale, "transform": xf}

    def _apply_wrap_tweaks(self, mesh, warp_node, pmv_scale, pmv_trans, data):
        """Gán lại các thông số đã lưu bằng _capture_wrap_tweaks cho mesh wrap mới."""
        for attr, val in data["warp"].items():
            try:
                cmds.setAttr("{0}.{1}".format(warp_node, attr), val)
            except Exception:
                pass

        for ramp, points in data["ramps"].items():
            # Xóa các điểm mặc định rồi ghi lại đúng các điểm của mesh cũ.
            for idx in cmds.getAttr("{0}.{1}".format(warp_node, ramp), multiIndices=True) or []:
                try:
                    cmds.removeMultiInstance("{0}.{1}[{2}]".format(warp_node, ramp, idx), b=True)
                except Exception:
                    pass
            for i, (pos, val) in enumerate(points):
                try:
                    cmds.setAttr("{0}.{1}[{2}]".format(warp_node, ramp, i), pos, val, type="double2")
                except Exception:
                    try:
                        cmds.setAttr("{0}.{1}[{2}].{1}_Position".format(warp_node, ramp, i), pos)
                        cmds.setAttr("{0}.{1}[{2}].{1}_Value".format(warp_node, ramp, i), val)
                    except Exception:
                        pass

        t_ax1, t_ax2, s_ax1, s_ax2 = self.get_cross_axes(mesh)
        if data["cross_trans"]:
            for ax, val in zip((t_ax1, t_ax2), data["cross_trans"]):
                try:
                    cmds.setAttr("{0}.{1}".format(pmv_trans, ax), val)
                except Exception:
                    pass
        if data["cross_scale"]:
            for ax, val in zip((s_ax1, s_ax2), data["cross_scale"]):
                try:
                    cmds.setAttr("{0}.{1}".format(pmv_scale, ax), val)
                except Exception:
                    pass

        for attr, val in data["transform"].items():
            try:
                cmds.setAttr("{0}.{1}".format(mesh, attr), val[0], val[1], val[2], type="double3")
            except Exception:
                pass

    def _apply_warp_curves(self, jobs, mesh_uuids):
        """jobs: danh sách (curve, mesh wrap cũ hoặc None), xem apply_warp."""
        # Node đo góc GS dùng chung cho mọi curve, luôn xóa khi xong (kể cả khi lỗi).
        # Node chỉ được tạo khi đo lần đầu, nên luồng chọn mesh không tốn công tạo node đo.
        probe = _GsOrientProbe()
        try:
            return self._apply_warp_curves_impl(jobs, mesh_uuids, probe)
        finally:
            probe.cleanup()

    def _apply_warp_curves_impl(self, jobs, mesh_uuids, probe):
        last_created_mesh = None
        success_count = 0
        no_orient = 0
        z_up = cmds.upAxis(query=True, axis=True) == 'z'

        # Quét scene MỘT lần để lập bảng UUID curve -> các mesh warp đã gắn UUID đó.
        # Trước đây mỗi curve lại quét toàn bộ transform trong scene nên rất chậm khi chọn nhiều curve.
        meshes_by_curve_uuid = {}
        tagged = cmds.ls("*.{0}".format(CURVE_UUID_ATTR), long=True, objectsOnly=True, recursive=True) or []
        for obj in cmds.ls(tagged, type="transform", long=True) or []:
            try:
                value = cmds.getAttr("{0}.{1}".format(obj, CURVE_UUID_ATTR))
            except Exception:
                continue
            if value:
                meshes_by_curve_uuid.setdefault(value, []).append(obj)

        for curve, picked_mesh in jobs:
            try:
                curve_shapes = cmds.listRelatives(curve, shapes=True, fullPath=True)
                if not curve_shapes: continue
                curve_shape = curve_shapes[0]

                # Luồng chọn mesh: lấy thông số của mesh cũ, bỏ qua bước tìm Orientation và đo góc từ curve.
                # Mesh cũ không còn curveWarp (vd đã xóa history) thì quay về luồng chọn curve.
                tweaks = None
                if picked_mesh and cmds.objExists(picked_mesh):
                    try:
                        tweaks = self._capture_wrap_tweaks(picked_mesh)
                    except Exception as exc:
                        cmds.warning(u"Không đọc được thông số của mesh cũ '{0}': {1}".format(picked_mesh, exc))

                custom_orient = 0.0
                if not tweaks:
                    # --- KIỂM TRA VÀ LẤY THÔNG SỐ ORIENTATION LINH HOẠT ---
                    custom_orient = self._find_curve_orientation(curve, curve_shape, verbose=False)
                    if custom_orient is None:
                        no_orient += 1
                        custom_orient = 0.0

                curve_uuid = _get_uuid(curve)

                # Thu thập mesh wrap cũ của curve (qua curveWarp và qua UUID curve) để kế thừa Group/Layer rồi xóa
                old_meshes = []
                for warp in set(cmds.listConnections(curve_shape, type='curveWarp') or []):
                    for d_shape in cmds.deformer(warp, query=True, geometry=True) or []:
                        for p in cmds.listRelatives(d_shape, parent=True, fullPath=True) or []:
                            if p not in old_meshes:
                                old_meshes.append(p)
                for obj in meshes_by_curve_uuid.get(curve_uuid, ()):
                    if obj not in old_meshes and cmds.objExists(obj):
                        old_meshes.append(obj)

                inherit_parent = None
                inherit_layers = []
                mirror_value = ""
                for old in old_meshes:
                    if not mirror_value and cmds.objExists(old) and cmds.attributeQuery("mirror", node=old, exists=True):
                        mirror_value = cmds.getAttr("{0}.mirror".format(old)) or ""
                for old in old_meshes:
                    if not cmds.objExists(old):
                        continue
                    if inherit_parent is None:
                        op = cmds.listRelatives(old, parent=True, fullPath=True)
                        if op and op[0] not in old_meshes:
                            inherit_parent = op[0]
                    for lyr in cmds.listConnections(old, type="displayLayer") or []:
                        if lyr != "defaultLayer" and lyr not in inherit_layers:
                            inherit_layers.append(lyr)
                for old in old_meshes:
                    if cmds.objExists(old):
                        cmds.delete(old)

                _freeze_curve_if_scale_uneven(curve)
                source_uuid = random.choice(mesh_uuids)
                source_mesh = _resolve_uuid(source_uuid)
                if not source_mesh:
                    cmds.warning(u"Mesh nguồn (UUID {0}) không còn tồn tại.".format(source_uuid))
                    continue
                source_short = source_mesh.split("|")[-1]
                dup_mesh = cmds.duplicate(source_mesh, returnRootsOnly=True)[0]
                
                if cmds.listRelatives(dup_mesh, parent=True):
                    dup_mesh = cmds.parent(dup_mesh, world=True)[0]

                dup_mesh = cmds.rename(dup_mesh, "{0}_Warped_#".format(source_short))
                _copy_library_marks(source_mesh, dup_mesh)
                _set_string_attr(dup_mesh, CURVE_UUID_ATTR, curve_uuid)

                if inherit_parent and cmds.objExists(inherit_parent):
                    target_grp = inherit_parent
                else:
                    target_grp = "{0}_Group".format(source_short)
                    if not cmds.objExists(target_grp):
                        cmds.group(empty=True, name=target_grp)

                dup_mesh = cmds.parent(dup_mesh, target_grp)[0]
                for lyr in inherit_layers:
                    if cmds.objExists(lyr):
                        cmds.editDisplayLayerMembers(lyr, dup_mesh, noRecurse=True)
                last_created_mesh = dup_mesh 
                
                cmds.move(0, 0, 0, dup_mesh, absolute=True, rotatePivotRelative=True)
                cmds.makeIdentity(dup_mesh, apply=True, translate=True, rotate=True, scale=True, normal=False)
                if mirror_value:
                    _apply_mirror_value(dup_mesh, mirror_value)
                
                bbox = cmds.exactWorldBoundingBox(dup_mesh)
                size_x = bbox[3] - bbox[0]
                size_y = bbox[4] - bbox[1]
                size_z = bbox[5] - bbox[2]
                
                if size_x >= size_y and size_x >= size_z:
                    c_ax1, c_ax2 = 'ty', 'tz'
                elif size_y >= size_x and size_y >= size_z:
                    c_ax1, c_ax2 = 'tx', 'tz'
                else:
                    c_ax1, c_ax2 = 'tx', 'ty'
                    
                for ax_name, ax_val in (("crossAxis1", c_ax1), ("crossAxis2", c_ax2)):
                    if not cmds.attributeQuery(ax_name, node=dup_mesh, exists=True):
                        cmds.addAttr(dup_mesh, longName=ax_name, dataType="string")
                    cmds.setAttr("{0}.{1}".format(dup_mesh, ax_name), ax_val, type="string")
                    
                pmv_scale = cmds.polyMoveVertex(dup_mesh, ch=True, pivot=(0, 0, 0))[0]
                pmv_trans = cmds.polyMoveVertex(dup_mesh, ch=True, worldSpace=True)[0]
                
                for msg_name, msg_node in (("pmvScaleNode", pmv_scale), ("pmvTransNode", pmv_trans)):
                    if not cmds.attributeQuery(msg_name, node=dup_mesh, exists=True):
                        cmds.addAttr(dup_mesh, longName=msg_name, attributeType="message")
                    cmds.connectAttr("{0}.message".format(msg_node), "{0}.{1}".format(dup_mesh, msg_name), force=True)
                
                warp_nodes = cmds.deformer(dup_mesh, type='curveWarp')
                warp_node = warp_nodes[0]
                cmds.connectAttr("{0}.worldSpace[0]".format(curve_shape), "{0}.inputCurve".format(warp_node), force=True)
                cmds.setAttr("{0}.keepLength".format(warp_node), 1)
                
                if tweaks:
                    # Luồng chọn mesh: chép toàn bộ thông số mesh cũ (gồm cả góc xoay).
                    self._apply_wrap_tweaks(dup_mesh, warp_node, pmv_scale, pmv_trans, tweaks)
                else:
                    # --- LUỒNG CHỌN CURVE: ÁP DỤNG GÓC XOAY TÍNH TỪ CURVE CHO WARP NODE ---
                    # Mesh thư viện ở Z-up nằm lệch 90 độ so với plane đo (dài X, pháp tuyến +Y), nên bù -90 độ.
                    base_offset = -90.0 if z_up else 0.0
                    rotation = None
                    generator = _gs_generator(curve_shape)
                    if generator:
                        try:
                            measured = probe.measure(curve_shape, generator)
                        except Exception:
                            measured = None
                        if measured is not None:
                            rotation = measured + base_offset
                    if rotation is None and custom_orient != 0.0:
                        # Curve không do GS dựng (hoặc đo lỗi): dùng thẳng giá trị Orientation như trước.
                        rotation = custom_orient + base_offset
                    if rotation is not None:
                        cmds.setAttr("{0}.rotation".format(warp_node), rotation)

                success_count += 1

            except Exception as e:
                cmds.warning(u"Lỗi ở curve '{0}': {1}".format(curve, str(e)))

        return last_created_mesh, success_count, no_orient

    def export_to_zbrush(self):
        if not cmds.pluginInfo('objExport', query=True, loaded=True):
            cmds.loadPlugin('objExport')
            
        root_dir = cmds.textFieldButtonGrp(self.tf_root_folder, query=True, text=True)
        if not root_dir or not os.path.exists(root_dir):
            self.browse_root_folder()
            root_dir = cmds.textFieldButtonGrp(self.tf_root_folder, query=True, text=True)
            if not root_dir or not os.path.exists(root_dir):
                return
            
        selection = cmds.ls(selection=True, long=True) or []
        if not selection:
            cmds.warning(u"Vui lòng chọn mesh gốc hoặc mesh con cần xuất.")
            return

        # Phân loại selection:
        # - Mesh gốc (dấu Library trùng UUID của chính nó, hoặc không có dấu): xuất toàn bộ mesh con của nó.
        # - Mesh con (dấu Library trỏ tới mesh gốc khác): chỉ xuất đúng mesh đang chọn.
        root_ids = []
        picked_children = []
        for node in selection:
            own_uuid = _get_uuid(node)
            ids = _export_source_ids(node)
            if own_uuid and own_uuid in ids:
                if own_uuid not in root_ids:
                    root_ids.append(own_uuid)
            elif ids:
                picked_children.append((node, ids))
        if not root_ids and not picked_children:
            cmds.warning(u"Không đọc được UUID của mesh đang chọn.")
            return

        source_names = {}

        def _source_name(source_id):
            """Tên thư mục theo mesh gốc; None nếu mesh gốc không còn trong scene."""
            if source_id not in source_names:
                source_node = _resolve_uuid(source_id)
                source_names[source_id] = _safe_dir_name(source_node.split("|")[-1]) if source_node else None
            return source_names[source_id]

        found_meshes = []
        seen = set()
        missing = 0
        no_geo = 0

        # Mesh con được chọn trực tiếp: lấy mesh gốc đầu tiên còn tồn tại để đặt tên thư mục.
        for node, ids in picked_children:
            source_id = next((i for i in ids if _source_name(i)), None)
            if source_id is None:
                missing += 1
                continue
            if not _has_export_mesh(node):
                no_geo += 1
                continue
            if node not in seen:
                seen.add(node)
                found_meshes.append((node, source_id))

        # Mesh gốc được chọn: quét scene tìm toàn bộ mesh con của nó.
        valid_roots = [r for r in root_ids if _source_name(r)]
        missing += len(root_ids) - len(valid_roots)
        root_ids = valid_roots
        if root_ids:
            attr_names = []
            for attr_name in (LIBRARY_MESH_ATTR, WARP_LIBRARY_MESH_ATTR):
                attr_names.extend(_library_attr_names(attr_name))
            for name in attr_names:
                for obj in cmds.ls("*.{0}".format(name), long=True, objectsOnly=True) or []:
                    if obj in seen:
                        continue
                    stored = _get_string_attr(obj, name)
                    if stored not in root_ids:
                        continue
                    # Mesh gốc: attribute trùng UUID hiện tại của node, không export.
                    node_uuid = _get_uuid(obj)
                    if node_uuid and stored == node_uuid:
                        continue
                    seen.add(obj)
                    # Transform còn attribute nhưng không còn mesh thật: xuất ra sẽ là OBJ rỗng.
                    if not _has_export_mesh(obj):
                        no_geo += 1
                        continue
                    found_meshes.append((obj, stored))

        if missing:
            cmds.warning(u"Bỏ qua {0} mesh vì mesh gốc không còn trong scene.".format(missing))
        if no_geo:
            cmds.warning(u"Bỏ qua {0} transform có dấu Library nhưng không còn mesh shape (chỉ còn shape intermediate hoặc trống).".format(no_geo))

        if not found_meshes:
            cmds.warning(u"Chưa có mesh con nào để xuất từ các mesh gốc đang chọn.")
            return

        # Mỗi mesh con dùng tên mesh gốc của chính nó.
        # Không nằm trong group -> "tên gốc". Nằm trong group -> "tên gốc_tên group".
        folders = {}
        order = []
        for mesh, source_id in found_meshes:
            source_name = source_names[source_id]
            parents = cmds.listRelatives(mesh, parent=True, fullPath=True)
            if parents:
                folder = "{0}_{1}".format(source_name, _safe_dir_name(parents[0].split("|")[-1]))
            else:
                folder = source_name
            if folder not in folders:
                folders[folder] = []
                order.append(folder)
            folders[folder].append(mesh)

        total = 0
        for folder in order:
            export_dir = os.path.join(root_dir, folder).replace("\\", "/")
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            obj_paths = []
            for i, mesh in enumerate(folders[folder]):
                cmds.select(mesh, replace=True)
                file_name = "{0}_Export_{1:03d}.obj".format(folder, i + 1)
                file_path = os.path.join(export_dir, file_name).replace("\\", "/")

                cmds.file(file_path, force=True, options="groups=0;ptgroups=0;materials=0;smoothing=0;normals=1",
                          type="OBJexport", pr=True, es=True)
                obj_paths.append(file_path)
            total += len(obj_paths)

            zscript_path = os.path.join(export_dir, "ZBrush_AutoImport_{0}.txt".format(folder)).replace("\\", "/")
            with open(zscript_path, "w") as f:
                f.write(_build_zbrush_import_script(obj_paths))

        cmds.select(clear=True)
        om.MGlobal.displayInfo(u"Đã xuất {0} OBJ vào {1} thư mục và tạo ZScript tại: {2}".format(total, len(order), root_dir))
