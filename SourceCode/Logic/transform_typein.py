# -*- coding: utf-8 -*-
"""
MT Transform Type-In - LOGIC (ô nhập toạ độ kiểu 3ds Max).
Giao diện nằm ở SourceCode/UI/MT_TransformTypeIn.py (class TransformTypeInBar),
được nhúng vào MT Selection Counter.

- Tự đổi theo tool đang dùng: Move -> toạ độ, Rotate -> góc, Scale -> tỉ lệ.
- Chọn 1 object: đọc/sửa transform của object.
- Chọn nhiều object: xử lý như 1 nhóm -> Move hiện tâm nhóm (nhập số = dời cả nhóm);
  Rotate/Scale hiện 0/1, nhập số = xoay/scale tương đối (World: quanh tâm nhóm,
  Local: mỗi object quanh pivot riêng); click phải = reset từng object về 0/1.
- Chọn vertex / edge / face / CV...: tâm (bounding box center) của vùng chọn.
- World / Local:
    World: toạ độ / góc theo hệ trục thế giới.
    Local: object -> giá trị channel box (theo parent);
           component -> theo hệ trục của object chứa nó (object space).
    Scale của object luôn là giá trị channel box ở cả 2 chế độ.
- Text nhập: "r10" = cộng tương đối 10; hỗ trợ biểu thức 10/3, 2*(5+1)...
- Theo dõi thay đổi bằng scriptJob + attributeChanged callback -> chỉ bật cờ dirty,
  UI hỏi cờ này để biết khi nào cần đọc lại (không gọi lệnh Maya liên tục).
"""
import re
import maya.cmds as cmds
import maya.api.OpenMaya as om

AXES = ("X", "Y", "Z")
BIG_MESH_IDS = 3000   # quá số này thì đọc cả mảng điểm 1 lần cho nhanh
STEP = {"move": 0.01, "rotate": 0.01, "scale": 0.01}   # bước của spinner
MODE_LABELS = {"move": "Move", "rotate": "Rotate", "scale": "Scale"}

state = {"world": True}
_flags = {"dirty": True}   # True -> UI cần đọc lại giá trị từ Maya
_jobs = []                 # scriptJob ids
_cb_ids = []               # OpenMaya callback ids (attribute changed)
_JOB_EVENTS = ("SelectionChanged", "ToolChanged", "DragRelease", "Undo", "Redo",
               "timeChanged", "NewSceneOpened", "SceneOpened",
               "linearUnitChanged", "angularUnitChanged")
_cache = {
    "sel_key": None,     # tuple selection lần trước
    "kind": None,        # 'comp' / 'obj' / None
    "objs": [],          # transforms
    "meshes": [],        # [(MDagPath, [vertex ids])]
    "others": [],        # components không phải mesh (CV, lattice point...)
    "pts": [],           # toàn bộ vertex/cv dạng tên (dùng khi apply)
}

_POLY_COMP_RE = re.compile(r"\.(vtx|e|f|vtxFace)\[")
_UV_COMP_RE = re.compile(r"\.map\[")


# --------------------------------------------------------------------------- #
# Đọc trạng thái
# --------------------------------------------------------------------------- #
def tool_mode():
    """'move' / 'rotate' / 'scale' theo tool đang dùng."""
    ctx = cmds.currentCtx() or ""
    try:
        cls = cmds.contextInfo(ctx, c=True) or ""
    except Exception:
        cls = ""
    name = (cls + " " + ctx).lower()
    if "rotate" in name:
        return "rotate"
    if "scale" in name:
        return "scale"
    return "move"


def unit_label(mode):
    return {"move": cmds.currentUnit(q=True, linear=True),
            "rotate": cmds.currentUnit(q=True, angle=True),
            "scale": "x"}[mode]


def _rebuild_cache(sel):
    """Chỉ chạy khi vùng chọn thay đổi."""
    _cache.update(kind=None, objs=[], meshes=[], others=[], pts=[])
    comps = [s for s in sel if "." in s and not _UV_COMP_RE.search(s)]
    if comps:
        poly = [c for c in comps if _POLY_COMP_RE.search(c)]
        others = [c for c in comps if not _POLY_COMP_RE.search(c)]
        verts = (cmds.polyListComponentConversion(poly, toVertex=True) or []) if poly else []
        meshes = []
        if verts:
            msel = om.MSelectionList()
            for v in verts:
                msel.add(v)
            merged = {}
            for i in range(msel.length()):
                dag, comp = msel.getComponent(i)
                try:
                    dag.extendToShape()
                except Exception:
                    pass
                ids = om.MFnSingleIndexedComponent(comp).getElements()
                key = dag.fullPathName()
                if key not in merged:
                    merged[key] = (dag, set())
                merged[key][1].update(ids)
            meshes = [(d, sorted(ids)) for d, ids in merged.values()]
        if meshes or others:
            _cache.update(kind="comp", meshes=meshes, others=others,
                          pts=list(verts) + others)
            return
    objs = cmds.ls(sel, transforms=True) or []
    if objs:
        _cache.update(kind="obj", objs=objs)


def sync_selection(force=False):
    """Cập nhật cache khi vùng chọn thay đổi. Trả về loại selection: 'comp'/'obj'/None."""
    if force:
        _cache["sel_key"] = None
    sel = cmds.ls(sl=True) or []
    key = tuple(sel)
    if key != _cache["sel_key"]:
        _cache["sel_key"] = key
        _rebuild_cache(sel)
        _register_attr_callbacks()
    return _cache["kind"]


def _comp_center(world=None):
    """Tâm bounding box của component. world=None -> theo nút World/Local."""
    if world is None:
        world = state["world"]
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3

    def acc(x, y, z):
        if x < mn[0]: mn[0] = x
        if x > mx[0]: mx[0] = x
        if y < mn[1]: mn[1] = y
        if y > mx[1]: mx[1] = y
        if z < mn[2]: mn[2] = z
        if z > mx[2]: mx[2] = z

    ws = om.MSpace.kWorld if world else om.MSpace.kObject
    for dag, ids in _cache["meshes"]:
        try:
            fn = om.MFnMesh(dag)
            if len(ids) > BIG_MESH_IDS:
                allp = fn.getPoints(ws)
                for i in ids:
                    p = allp[i]
                    acc(p.x, p.y, p.z)
            else:
                for i in ids:
                    p = fn.getPoint(i, ws)
                    acc(p.x, p.y, p.z)
        except Exception:
            _cache["sel_key"] = None   # mesh đổi topology/bị xoá -> tính lại
            return None
    unit = om.MDistance.uiUnit()
    if _cache["others"]:
        # xform trả về đơn vị UI -> đổi về cm cho đồng bộ với API
        if world:
            flat = cmds.xform(_cache["others"], q=True, ws=True, t=True) or []
        else:
            flat = cmds.xform(_cache["others"], q=True, os=True, t=True) or []
        flat = [om.MDistance(v, unit).asCentimeters() for v in flat]
        for k in range(0, len(flat), 3):
            acc(flat[k], flat[k + 1], flat[k + 2])
    if mn[0] == float("inf"):
        return None
    # đổi từ cm (API) sang đơn vị UI
    return [om.MDistance((mn[i] + mx[i]) * 0.5).asUnits(unit) for i in range(3)]


def _obj_values(obj, mode):
    world = state["world"]
    if mode == "move" and world:
        return cmds.xform(obj, q=True, ws=True, rp=True)
    if mode == "rotate" and world:
        return cmds.xform(obj, q=True, ws=True, ro=True)
    attr = {"move": "translate", "rotate": "rotate", "scale": "scale"}[mode]
    return list(cmds.getAttr(obj + "." + attr)[0])


def neutral(mode):
    return 1.0 if mode == "scale" else 0.0


def _is_group():
    """Đang chọn nhiều object -> xử lý như 1 nhóm."""
    return _cache["kind"] == "obj" and len(_cache["objs"]) > 1


def _objs_center(world=None):
    """
    Tâm (bounding box center) của nhóm object.
    World: theo vị trí pivot trong world | Local: theo giá trị translate (channel box).
    """
    if world is None:
        world = state["world"]
    pts = []
    for o in _cache["objs"]:
        if world:
            pts.append(cmds.xform(o, q=True, ws=True, rp=True))
        else:
            pts.append(list(cmds.getAttr(o + ".translate")[0]))
    if not pts:
        return None
    return [(min(p[i] for p in pts) + max(p[i] for p in pts)) * 0.5 for i in range(3)]


def read_values(mode=None):
    """
    Đọc giá trị để hiển thị.
    Trả về (mode, kind, [x, y, z]); phần tử None = các object khác giá trị nhau (để trống).
    """
    sync_selection()
    if mode is None:
        mode = tool_mode()
    kind = _cache["kind"]
    vals = [None, None, None]
    if kind == "comp":
        vals = (_comp_center() or vals) if mode == "move" else [neutral(mode)] * 3
    elif kind == "obj":
        try:
            if len(_cache["objs"]) == 1:
                vals = _obj_values(_cache["objs"][0], mode)
            elif mode == "move":
                vals = _objs_center() or vals          # nhóm: tâm của nhóm
            else:
                vals = [neutral(mode)] * 3             # nhóm: xoay/scale tương đối
        except Exception:
            _cache["sel_key"] = None                   # object bị xoá/đổi tên -> tính lại
    return mode, kind, vals


def fmt(v):
    if v is None:
        return ""
    s = ("%.3f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def parse(text):
    """Trả về (giá trị, relative?) hoặc (None, False) nếu không hợp lệ."""
    t = (text or "").strip().replace(",", ".")
    rel = False
    if t[:1] in ("r", "R"):
        rel, t = True, t[1:].strip()
    if not t or not re.match(r"^[0-9eE\.\+\-\*/\(\)\s]+$", t):
        return None, False
    try:
        return float(eval(t, {"__builtins__": {}}, {})), rel
    except Exception:
        return None, False


def set_world(world):
    state["world"] = bool(world)
    _flags["dirty"] = True


# --------------------------------------------------------------------------- #
# Theo dõi thay đổi: callback chỉ bật cờ dirty, KHÔNG gọi lệnh Maya
# --------------------------------------------------------------------------- #
def mark_dirty(*_):
    _flags["dirty"] = True


def consume_dirty():
    """Trả về True nếu có thay đổi kể từ lần hỏi trước (và xoá cờ)."""
    d = _flags["dirty"]
    _flags["dirty"] = False
    return d


def _remove_attr_callbacks():
    if _cb_ids:
        try:
            om.MMessage.removeCallbacks(list(_cb_ids))
        except Exception:
            pass
        del _cb_ids[:]


def _register_attr_callbacks():
    """Theo dõi attribute của node đang chọn -> sửa channel box cũng cập nhật ngay."""
    _remove_attr_callbacks()
    if not _jobs:
        return   # chưa bật theo dõi (UI chưa mở)
    nodes = set(_cache["objs"])
    for dag, _ids in _cache["meshes"]:
        nodes.add(dag.fullPathName())
    for c in _cache["others"]:
        nodes.add(c.split(".")[0])
    for n in list(nodes):
        parents = cmds.listRelatives(n, parent=True, fullPath=True) or []
        if cmds.nodeType(n) != "transform" and parents:
            nodes.update(parents)   # shape -> theo dõi cả transform cha
    for n in nodes:
        try:
            msel = om.MSelectionList()
            msel.add(n)
            _cb_ids.append(om.MNodeMessage.addAttributeChangedCallback(
                msel.getDependNode(0), mark_dirty))
        except Exception:
            pass


def start_tracking():
    """Bật scriptJob/callback theo dõi thay đổi (gọi khi mở UI)."""
    stop_tracking()
    for ev in _JOB_EVENTS:
        try:
            _jobs.append(cmds.scriptJob(event=[ev, mark_dirty]))
        except Exception:
            pass
    _cache["sel_key"] = None
    _flags["dirty"] = True


def stop_tracking():
    """Tắt toàn bộ scriptJob/callback (gọi khi đóng UI)."""
    for j in _jobs:
        try:
            cmds.scriptJob(kill=j, force=True)
        except Exception:
            pass
    del _jobs[:]
    _remove_attr_callbacks()


# --------------------------------------------------------------------------- #
# Áp dụng giá trị
#   op: 'set' = đặt tuyệt đối | 'add' = cộng thêm | 'mul' = nhân
# --------------------------------------------------------------------------- #
def open_chunk(name="MT_TransformTypeIn"):
    cmds.undoInfo(openChunk=True, chunkName=name)


def close_chunk():
    cmds.undoInfo(closeChunk=True)


def perform(axis, val, op, chunk=True):
    kind = sync_selection()
    if not kind:
        return
    mode = tool_mode()
    if chunk:
        open_chunk()
    try:
        if kind == "comp":
            _apply_comp(mode, axis, val, op)
        else:
            _apply_obj(_cache["objs"], mode, axis, val, op)
    except Exception as e:
        cmds.warning("MT Type-In: %s" % e)
    finally:
        if chunk:
            close_chunk()


def apply_text(axes, text):
    """
    Áp dụng text gõ trong ô cho 1 hoặc nhiều trục (1 bước undo).
    Trả về True nếu text hợp lệ.
    """
    val, rel = parse(text)
    sync_selection(force=True)   # đảm bảo dùng vùng chọn mới nhất
    if val is None:
        return False
    op = "add" if rel else "set"
    open_chunk()
    try:
        for ax in axes:
            perform(ax, val, op, chunk=False)
    finally:
        close_chunk()
    return True


def nudge(axis, delta, chunk=True):
    """Spinner tăng/giảm: cộng delta vào giá trị đang hiển thị."""
    mode = tool_mode()
    if mode == "scale" and (_cache["kind"] == "comp" or _is_group()):
        perform(axis, 1.0 + delta, "mul", chunk)
    else:
        perform(axis, delta, "add", chunk)


def reset(axis):
    """
    Click phải spinner: Move/Rotate về 0, Scale về 1.
    Nhóm object + Rotate/Scale: reset giá trị channel box của từng object.
    """
    sync_selection()
    mode = tool_mode()
    if _cache["kind"] == "comp" and mode != "move":
        return   # component rotate/scale không có giá trị tuyệt đối để reset
    if _is_group() and mode != "move":
        attr = ("rotate" if mode == "rotate" else "scale") + AXES[axis]
        open_chunk()
        try:
            for o in _cache["objs"]:
                plug = o + "." + attr
                try:
                    if not cmds.getAttr(plug, lock=True):
                        cmds.setAttr(plug, neutral(mode))
                except Exception as e:
                    cmds.warning("MT Type-In: %s" % e)
        finally:
            close_chunk()
        return
    perform(axis, neutral(mode), "set")


def _apply_comp(mode, axis, val, op):
    pts = _cache["pts"]
    world = state["world"]
    space = {"ws": True} if world else {"os": True}
    if not pts:
        return
    if mode == "move":
        center = _comp_center()
        if center is None:
            return
        d = [0.0, 0.0, 0.0]
        d[axis] = val - center[axis] if op == "set" else val
        cmds.move(d[0], d[1], d[2], pts, r=True, **space)
        return
    pivot = _comp_center(world=True)   # pivot luôn tính theo world
    if pivot is None:
        return
    if mode == "rotate":
        r = [0.0, 0.0, 0.0]
        r[axis] = val
        cmds.rotate(r[0], r[1], r[2], pts, r=True, pivot=pivot, **space)
    else:
        s = [1.0, 1.0, 1.0]
        s[axis] = val if op != "add" else 1.0 + val
        cmds.scale(s[0], s[1], s[2], pts, r=True, pivot=pivot, **space)


def _apply_group(objs, mode, axis, val, op):
    """Nhiều object: xử lý như 1 nhóm (giữ nguyên vị trí tương đối giữa các object)."""
    world = state["world"]
    space = {"ws": True} if world else {"os": True}
    if mode == "move":
        if op == "set":
            center = _objs_center()
            if center is None:
                return
            val = val - center[axis]          # dịch cả nhóm để tâm tới giá trị nhập
        if world:
            d = [0.0, 0.0, 0.0]
            d[axis] = val
            cmds.move(d[0], d[1], d[2], objs, r=True, ws=True)
        else:
            _apply_attr(objs, "translate" + AXES[axis], val, "add")
        return
    if mode == "rotate":
        r = [0.0, 0.0, 0.0]
        r[axis] = val
        if world:   # xoay cả nhóm quanh tâm nhóm
            cmds.rotate(r[0], r[1], r[2], objs, r=True, pivot=_objs_center(world=True), **space)
        else:       # mỗi object xoay quanh trục + pivot của chính nó
            cmds.rotate(r[0], r[1], r[2], objs, r=True, **space)
        return
    s = [1.0, 1.0, 1.0]
    s[axis] = val if op != "add" else 1.0 + val
    if world:       # scale cả nhóm quanh tâm nhóm (khoảng cách giữa các object cũng scale)
        cmds.scale(s[0], s[1], s[2], objs, r=True, pivot=_objs_center(world=True))
    else:           # mỗi object scale quanh pivot của chính nó
        cmds.scale(s[0], s[1], s[2], objs, r=True)


def _apply_attr(objs, attr, val, op):
    for o in objs:
        plug = o + "." + attr
        if cmds.getAttr(plug, lock=True):
            cmds.warning("MT Type-In: %s bị khoá" % plug)
            continue
        cur = cmds.getAttr(plug)
        new = {"set": val, "add": cur + val, "mul": cur * val}[op]
        cmds.setAttr(plug, new)


def _apply_obj(objs, mode, axis, val, op):
    if len(objs) > 1:
        _apply_group(objs, mode, axis, val, op)
        return
    world = state["world"]
    if mode == "move" and world:
        if op == "set":
            for o in objs:
                p = cmds.xform(o, q=True, ws=True, rp=True)
                p[axis] = val
                cmds.move(p[0], p[1], p[2], o, a=True, ws=True, rpr=True)
        else:
            d = [0.0, 0.0, 0.0]
            d[axis] = val
            cmds.move(d[0], d[1], d[2], objs, r=True, ws=True)
        return
    if mode == "rotate" and world:
        if op == "set":
            for o in objs:
                r = cmds.xform(o, q=True, ws=True, ro=True)
                r[axis] = val
                cmds.xform(o, ws=True, ro=r)
        else:
            d = [0.0, 0.0, 0.0]
            d[axis] = val
            cmds.rotate(d[0], d[1], d[2], objs, r=True, ws=True)
        return
    # Local (và scale): sửa thẳng giá trị channel box
    attr = {"move": "translate", "rotate": "rotate", "scale": "scale"}[mode] + AXES[axis]
    for o in objs:
        plug = o + "." + attr
        if cmds.getAttr(plug, lock=True):
            cmds.warning("MT Type-In: %s bị khoá" % plug)
            continue
        cur = cmds.getAttr(plug)
        new = {"set": val, "add": cur + val, "mul": cur * val}[op]
        cmds.setAttr(plug, new)
