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
    def __init__(self):
        self.window_name = "MT_ReplaceMeshWindow"
        self.title = "MT Replace Mesh"
        self.job_id = None
        self.source_memory = []
        self.warp_source_memory = []
        self.keep_placeholder = False
        self.mirror_axes = {"x": False, "y": False, "z": False}

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
        curves = []
        
        for obj in selection:
            shapes = cmds.listRelatives(obj, shapes=True, fullPath=True)
            if not shapes: continue
            if cmds.objectType(shapes[0]) in ["nurbsCurve", "bezierCurve"]: curves.append(obj)

        mesh_uuids = list(self.warp_source_memory)
        if not mesh_uuids:
            cmds.warning(u"Danh sách Curve Mesh đang trống. Vui lòng chọn Mesh và ấn Select And Save Curve Mesh trước.")
            return
        if not curves:
            cmds.warning(u"Vui lòng chọn ÍT NHẤT 1 Curve.")
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
            last_created_mesh, success_count, no_orient = self._apply_warp_curves(curves, mesh_uuids)
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

    def _apply_warp_curves(self, curves, mesh_uuids):
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

        for curve in curves:
            try:
                curve_shapes = cmds.listRelatives(curve, shapes=True, fullPath=True)
                if not curve_shapes: continue
                curve_shape = curve_shapes[0]

                # --- KIỂM TRA VÀ LẤY THÔNG SỐ ORIENTATION LINH HOẠT ---
                custom_orient = self._find_curve_orientation(curve, curve_shape, verbose=False)
                if custom_orient is None:
                    no_orient += 1
                    custom_orient = 0.0
                # -------------------------------------------------------------

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
                
                # --- ÁP DỤNG GIÁ TRỊ ORIENT LẤY ĐƯỢC VÀO THUỘC TÍNH ROTATION CỦA WARP NODE ---
                if custom_orient != 0.0:
                    # Z-up: bù -90 độ; Y-up: đảo hướng 180 - orient
                    cmds.setAttr("{0}.rotation".format(warp_node), custom_orient - 90.0 if z_up else custom_orient)

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

        # Mesh con được chọn trực tiếp: lấy mesh gốc đầu tiên còn tồn tại để đặt tên thư mục.
        for node, ids in picked_children:
            source_id = next((i for i in ids if _source_name(i)), None)
            if source_id is None:
                missing += 1
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
                    found_meshes.append((obj, stored))

        if missing:
            cmds.warning(u"Bỏ qua {0} mesh vì mesh gốc không còn trong scene.".format(missing))

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
                f.write('/* ZBrush Run-Once Script - Auto Duplicate & Import OBJs */\n')
                f.write('[If, 1,\n')
                f.write('  [IShowActions, 0]\n')
                for obj_file in obj_paths:
                    f.write('  [IPress, Tool:SubTool:Duplicate]\n')
                    f.write('  [IPress, Tool:SubTool:SelectDown]\n')
                    f.write('  [ISet, Tool:Geometry:SDiv, 1]\n')
                    f.write('  [FileNameSetNext, "{0}"]\n'.format(obj_file))
                    f.write('  [IPress, Tool:Import]\n')
                    f.write('  [ISet, Tool:Geometry:SDiv, 100]\n')
                f.write(']\n')

        cmds.select(clear=True)
        om.MGlobal.displayInfo(u"Đã xuất {0} OBJ vào {1} thư mục và tạo ZScript tại: {2}".format(total, len(order), root_dir))
