# -*- coding: utf-8 -*-
"""
Mirror mesh theo trục X / Y / Z. Giao diện nằm trong MT_ReplaceMesh.

- Chọn mesh: bake pivot position trước, rồi duplicate, kế thừa attribute, ghi `mirror`, rồi mới lật.
- Chọn group: duplicate cả group, rồi lật mọi mesh trong group mới.
- Nhiều mesh thì bake pivot một lần, không copy history khi mesh không có deformer,
  xóa history còn lại một lệnh, và đảo normal một lệnh cho cả loạt.
- `mirror` (string, ví dụ "x", "xy") ghi các trục đã đảo đỉnh. Replace đọc attribute này
  và đảo đỉnh bản mới cho khớp hướng.
- Rotate X/Y/Z đảo dấu hết. Translate chỉ đảo dấu trục đã chọn. Scale transform giữ dương.
"""
from __future__ import unicode_literals
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as om
import maya.api.OpenMaya as om2

_AXIS = {"x": 0, "y": 1, "z": 2}
_ROTATE = ("rotateX", "rotateY", "rotateZ")
_DEFORMER_TYPES = ("polyMoveVertex", "curveWarp")
MIRROR_ATTR = "mirror"

# Python 2.7 (Maya 2018–2020) có thêm kiểu unicode, Python 3 chỉ có str và bytes.
try:
    _STRING_TYPES = (basestring,)  # type: ignore[name-defined]
except NameError:
    _STRING_TYPES = (str, bytes)


def _normalize_axes(axes):
    if isinstance(axes, _STRING_TYPES):
        axes = [axes]
    chosen = set()
    for axis in axes or []:
        name = str(axis).lower().strip()
        if name in _AXIS:
            chosen.add(name)
        else:
            cmds.warning(u"Bỏ qua trục không hợp lệ: {0}".format(axis))
    return [name for name in ("x", "y", "z") if name in chosen]


def _plug(node, attr):
    return "{0}.{1}".format(node, attr)


def _has_attr(node, attr):
    return cmds.objExists(node) and cmds.attributeQuery(attr, node=node, exists=True)


def _get_channel(node, attr):
    if not _has_attr(node, attr):
        return None
    try:
        value = cmds.getAttr(_plug(node, attr))
    except Exception:
        return None
    if isinstance(value, (list, tuple)):
        return None
    return value


def _set_channel(node, attr, value):
    plug = _plug(node, attr)
    if not _has_attr(node, attr):
        return False
    if cmds.getAttr(plug, lock=True) or cmds.connectionInfo(plug, isDestination=True):
        cmds.warning(u"Không đảo được {0} (đang khoá hoặc bị connect).".format(plug))
        return False
    try:
        cmds.setAttr(plug, value)
        return True
    except Exception as exc:
        cmds.warning(u"Không đảo được {0}: {1}".format(plug, exc))
        return False


def _negate_channel(node, attr):
    value = _get_channel(node, attr)
    if value is None:
        return False
    return _set_channel(node, attr, -value)


def collect_meshes(nodes):
    """Mesh thì lấy chính nó. Group (transform không có mesh) thì lấy mọi mesh con."""
    result = []
    seen = set()

    def add(transform):
        full = cmds.ls(transform, long=True)
        if not full:
            return
        transform = full[0]
        if transform in seen:
            return
        if cmds.listRelatives(transform, shapes=True, type="mesh", fullPath=True):
            seen.add(transform)
            result.append(transform)

    for node in nodes or []:
        full = cmds.ls(node, long=True)
        if not full:
            continue
        node = full[0]
        if cmds.nodeType(node) == "mesh":
            parent = cmds.listRelatives(node, parent=True, fullPath=True)
            if parent:
                add(parent[0])
            continue
        if cmds.objectType(node, isAType="transform") is False and cmds.nodeType(node) != "transform":
            continue
        if cmds.listRelatives(node, shapes=True, type="mesh", fullPath=True):
            add(node)
            continue
        children = cmds.listRelatives(node, allDescendents=True, type="transform", fullPath=True) or []
        for child in children:
            add(child)
    return result


def _own_history(src, dst):
    """Node history của bản copy, bỏ node còn dùng chung với mesh gốc."""
    shared = set(cmds.listHistory(src) or [])
    owned = []
    for node in cmds.listHistory(dst) or []:
        if node not in shared and node != dst:
            owned.append(node)
    return owned


def _split_dg_history(src, dst):
    """History DG của bản copy, và phần không còn dùng chung với mesh gốc."""
    shared = set(cmds.listHistory(src, pruneDagObjects=True) or [])
    dst_hist = cmds.listHistory(dst, pruneDagObjects=True) or []
    owned = [node for node in dst_hist if node not in shared]
    return dst_hist, owned


def _has_construction_history(node):
    return bool(cmds.listHistory(node, pruneDagObjects=True))


def _copy_user_attributes(src, dst):
    for attr in cmds.listAttr(src, userDefined=True) or []:
        if "." in attr:
            continue
        src_plug = _plug(src, attr)
        try:
            attr_type = cmds.getAttr(src_plug, type=True)
        except Exception:
            continue
        if attr_type == "message":
            continue
        if not cmds.attributeQuery(attr, node=dst, exists=True):
            data_type = cmds.attributeQuery(attr, node=src, dataType=True)
            if data_type:
                cmds.addAttr(dst, longName=attr, dataType=data_type[0])
            else:
                kind = cmds.attributeQuery(attr, node=src, attributeType=True)
                if not kind:
                    continue
                cmds.addAttr(dst, longName=attr, attributeType=kind)
        dst_plug = _plug(dst, attr)
        if cmds.getAttr(dst_plug, lock=True) or cmds.connectionInfo(dst_plug, isDestination=True):
            continue
        if attr_type == "string":
            value = cmds.getAttr(src_plug) or ""
            cmds.setAttr(dst_plug, value, type="string")
            continue
        value = cmds.getAttr(src_plug)
        if isinstance(value, (list, tuple)):
            continue
        try:
            cmds.setAttr(dst_plug, value)
        except Exception:
            pass


def _retarget_message_attributes(src, dst):
    message_attrs = []
    for attr in cmds.listAttr(src, userDefined=True) or []:
        if "." in attr:
            continue
        src_plug = _plug(src, attr)
        try:
            if cmds.getAttr(src_plug, type=True) != "message":
                continue
        except Exception:
            continue
        message_attrs.append(attr)
    if not message_attrs:
        return

    src_hist = list(cmds.listHistory(src) or [])
    dst_hist = _own_history(src, dst)
    for attr in message_attrs:
        src_plug = _plug(src, attr)
        if not cmds.attributeQuery(attr, node=dst, exists=True):
            cmds.addAttr(dst, longName=attr, attributeType="message")
        dst_plug = _plug(dst, attr)
        current = cmds.listConnections(dst_plug, source=True, destination=False) or []
        if current and current[0] not in src_hist:
            continue
        sources = cmds.listConnections(src_plug, source=True, destination=False) or []
        if not sources:
            continue
        src_node = sources[0]
        node_type = cmds.nodeType(src_node)
        src_typed = [n for n in src_hist if cmds.nodeType(n) == node_type]
        dst_typed = [n for n in dst_hist if cmds.nodeType(n) == node_type]
        if src_node not in src_typed or len(src_typed) != len(dst_typed):
            continue
        mapped = dst_typed[src_typed.index(src_node)]
        try:
            cmds.connectAttr(_plug(mapped, "message"), dst_plug, force=True)
        except Exception:
            pass


def _display_layers_of(src):
    layers = cmds.listConnections(src, type="displayLayer") or []
    shapes = cmds.listRelatives(src, shapes=True, fullPath=True) or []
    for shape in shapes:
        layers.extend(cmds.listConnections(shape, type="displayLayer") or [])
    return [layer for layer in set(layers) if layer != "defaultLayer"]


def _copy_display_layer(src, dst):
    for layer in _display_layers_of(src):
        if cmds.objExists(layer):
            cmds.editDisplayLayerMembers(layer, dst, noRecurse=True)


def _remember_display_layer(src, dst, layer_map):
    for layer in _display_layers_of(src):
        layer_map.setdefault(layer, []).append(dst)


def _apply_display_layers(layer_map):
    for layer, members in layer_map.items():
        if not cmds.objExists(layer):
            continue
        members = [member for member in members if cmds.objExists(member)]
        if members:
            cmds.editDisplayLayerMembers(layer, members, noRecurse=True)


def _match_parent(src, dst):
    src_parent = cmds.listRelatives(src, parent=True, fullPath=True)
    dst_parent = cmds.listRelatives(dst, parent=True, fullPath=True)
    src_parent = src_parent[0] if src_parent else None
    dst_parent = dst_parent[0] if dst_parent else None
    if src_parent == dst_parent:
        return cmds.ls(dst, long=True)[0]
    if src_parent and cmds.objExists(src_parent):
        dst = cmds.parent(dst, src_parent)[0]
    else:
        dst = cmds.parent(dst, world=True)[0]
    return cmds.ls(dst, long=True)[0]


def _flip_points(shape, axes):
    sel = om2.MSelectionList()
    sel.add(shape)
    dag = sel.getDagPath(0)
    fn = om2.MFnMesh(dag)
    indexes = [_AXIS[axis] for axis in axes]
    points = fn.getPoints(om2.MSpace.kObject)
    for point in points:
        for index in indexes:
            point[index] = -point[index]
    fn.setPoints(points, om2.MSpace.kObject)
    fn.updateSurface()


def _has_live_deformer(transform, history=None):
    if history is None:
        history = cmds.listHistory(transform, pruneDagObjects=True) or []
    if not history:
        return False
    return bool(cmds.ls(history, type=list(_DEFORMER_TYPES)))


def _reverse_normals(transforms):
    transforms = [node for node in transforms if cmds.objExists(node)]
    if not transforms:
        return
    try:
        cmds.polyNormal(transforms, normalMode=0, userNormalMode=0, ch=False)
    except Exception:
        for node in transforms:
            try:
                cmds.polyNormal(node, normalMode=0, userNormalMode=0, ch=False)
            except Exception:
                pass


def _flip_shape(transform, axes, keep_history=None, clear_history=None, deferred_normals=None):
    """Lật đỉnh object-space. Có deformer thì sửa shape gốc (intermediate) để history không ghi đè."""
    if keep_history is None or clear_history is None:
        history = cmds.listHistory(transform, pruneDagObjects=True) or []
        live = _has_live_deformer(transform, history)
        if keep_history is None:
            keep_history = live
        if clear_history is None:
            clear_history = bool(history) and not live
    if clear_history and not keep_history:
        try:
            cmds.delete(transform, constructionHistory=True)
        except Exception:
            pass

    shapes = cmds.listRelatives(transform, shapes=True, fullPath=True, noIntermediate=False) or []
    meshes = [shape for shape in shapes if cmds.nodeType(shape) == "mesh"]
    origs = [shape for shape in meshes if cmds.getAttr(_plug(shape, "intermediateObject"))]
    targets = origs if keep_history and origs else [
        shape for shape in meshes if not cmds.getAttr(_plug(shape, "intermediateObject"))
    ]
    for shape in targets:
        _flip_points(shape, axes)

    reverse = len(axes) % 2 == 1
    if deferred_normals is not None and not keep_history:
        deferred_normals.append((transform, reverse))
        return
    if reverse:
        _reverse_normals([transform])
    _unlock_normals(transform)


def _unlock_shape(shape):
    sel = om2.MSelectionList()
    sel.add(shape)
    fn = om2.MFnMesh(sel.getDagPath(0))
    count = fn.numVertices
    if count:
        fn.unlockVertexNormals(list(range(count)))
    fn.updateSurface()


def _unlock_normals(transform):
    """Unlock Normals trên mesh đang thấy, không thêm construction history."""
    shapes = cmds.listRelatives(transform, shapes=True, fullPath=True, noIntermediate=True) or []
    for shape in shapes:
        if cmds.nodeType(shape) != "mesh":
            continue
        try:
            _unlock_shape(shape)
        except Exception as exc:
            cmds.warning(u"Không unlock normal được '{0}': {1}".format(shape, exc))


def _flush_deferred_normals(entries):
    if not entries:
        return
    _reverse_normals([node for node, do_reverse in entries if do_reverse])
    sel = om2.MSelectionList()
    shapes = []
    for node, _do_reverse in entries:
        if not cmds.objExists(node):
            continue
        for shape in cmds.listRelatives(node, shapes=True, fullPath=True, noIntermediate=True) or []:
            if cmds.nodeType(shape) != "mesh":
                continue
            try:
                sel.add(shape)
            except Exception:
                continue
            shapes.append(shape)
    for index, shape in enumerate(shapes):
        try:
            fn = om2.MFnMesh(sel.getDagPath(index))
            count = fn.numVertices
            if count:
                fn.unlockVertexNormals(list(range(count)))
            fn.updateSurface()
        except Exception as exc:
            cmds.warning(u"Không unlock normal được '{0}': {1}".format(shape, exc))


def _capture_channels(node, attrs):
    return {attr: _get_channel(node, attr) for attr in attrs}


def _apply_negated(node, captured, attrs):
    for attr in attrs:
        value = captured.get(attr)
        if value is not None:
            _set_channel(node, attr, -value)


_PIVOT_ATTRS = ("rotatePivot", "scalePivot", "rotatePivotTranslate", "scalePivotTranslate")


def _meshes_with_pivot_offset(meshes):
    """Mesh có pivot khác 0. Đọc attribute, không đi qua xform."""
    sel = om2.MSelectionList()
    indexed = []
    for mesh in meshes:
        try:
            sel.add(mesh)
        except Exception:
            continue
        indexed.append(mesh)
    need = []
    for index, mesh in enumerate(indexed):
        try:
            fn = om2.MFnDependencyNode(sel.getDependNode(index))
            offset = False
            for name in _PIVOT_ATTRS:
                plug = fn.findPlug(name, False)
                children = plug.numChildren()
                if children:
                    values = [plug.child(child).asDouble() for child in range(children)]
                else:
                    values = [plug.asDouble()]
                if any(abs(value) > 1e-12 for value in values):
                    offset = True
                    break
            if offset:
                need.append(mesh)
        except Exception:
            need.append(mesh)
    return need


def _bake_pivot_positions(meshes):
    """Bake pivot position một lần cho cả loạt. Pivot đang ở 0 thì bỏ qua."""
    unique = []
    seen = set()
    for mesh in meshes:
        if mesh in seen or not cmds.objExists(mesh):
            continue
        seen.add(mesh)
        unique.append(mesh)
    need = _meshes_with_pivot_offset(unique)
    if not need:
        return
    try:
        cmds.select(need, replace=True)
        mel.eval("bakeCustomToolPivot 1 0;")
    except Exception as exc:
        cmds.warning(u"Không Bake Pivot được: {0}".format(exc))


def _mirror_channels(src, dst, axes, owned=None):
    translate_attrs = ["translate{0}".format(axis.upper()) for axis in axes]
    # Mỗi trục lật sẽ đảo dấu 2 trục xoay còn lại (giữ nguyên trục xoay cùng tên)
    rotate_attrs = [
        "rotate{0}".format(a.upper())
        for a in ("x", "y", "z")
        if sum(1 for m in axes if m != a) % 2 == 1
    ]
    if owned is None:
        owned = _own_history(src, dst)

    transform_caps = _capture_channels(dst, _ROTATE + tuple("translate" + a.upper() for a in "xyz"))
    _apply_negated(dst, transform_caps, rotate_attrs)
    _apply_negated(dst, transform_caps, translate_attrs)

    for node in owned:
        node_type = cmds.nodeType(node)
        if node_type == "polyMoveVertex":
            caps = _capture_channels(node, _ROTATE + tuple("translate" + a.upper() for a in "xyz"))
            _apply_negated(node, caps, rotate_attrs)    # <-- Sửa dòng 270: thay _ROTATE bằng rotate_attrs
            _apply_negated(node, caps, translate_attrs)
        elif node_type == "curveWarp":
            if len(axes) % 2 == 1:                      # <-- Thêm điều kiện số trục lật là lẻ
                _negate_channel(node, "rotation")


def _get_mirror_value(node):
    if not _has_attr(node, MIRROR_ATTR):
        return ""
    return cmds.getAttr(_plug(node, MIRROR_ATTR)) or ""


def mirror_axes_of(node):
    """Các trục đã đảo đỉnh, đọc từ attribute `mirror`."""
    return _normalize_axes(list(_get_mirror_value(node)))


def _set_mirror_attr(node, axes):
    """Ghi đè attribute mirror sau khi attribute cũ đã được kế thừa."""
    axes = _normalize_axes(axes)
    if not axes:
        if _has_attr(node, MIRROR_ATTR):
            cmds.deleteAttr(_plug(node, MIRROR_ATTR))
        return
    if not _has_attr(node, MIRROR_ATTR):
        cmds.addAttr(node, longName=MIRROR_ATTR, dataType="string")
    cmds.setAttr(_plug(node, MIRROR_ATTR), "".join(axes), type="string")


def _stamp_mirror_attr(node, new_axes):
    """Lật cùng trục lần nữa thì triệt tiêu. Kết quả là các trục còn lệch so với mesh Library."""
    current = set(mirror_axes_of(node))
    added = set(_normalize_axes(new_axes))
    combined = [axis for axis in ("x", "y", "z") if (axis in current) ^ (axis in added)]
    _set_mirror_attr(node, combined)


def apply_mirror_value(dst, value):
    """Đảo đỉnh `dst` theo chuỗi trục đã lưu (ví dụ 'x', 'xy') và ghi lại attribute mirror."""
    axes = _normalize_axes(list(value or ""))
    if not axes or not cmds.objExists(dst):
        return False
    _flip_shape(dst, axes)
    _set_mirror_attr(dst, axes)
    return True


def apply_stored_mirror(src, dst):
    """Placeholder có attribute mirror thì đảo đỉnh mesh replace và ghi lại attribute đó."""
    if not cmds.objExists(src):
        return False
    return apply_mirror_value(dst, _get_mirror_value(src))


def _is_mesh_transform(node):
    return bool(cmds.listRelatives(node, shapes=True, type="mesh", fullPath=True))


def _ordered_meshes(root):
    nodes = cmds.listRelatives(root, allDescendents=True, type="transform", fullPath=True) or []
    return [node for node in nodes if _is_mesh_transform(node)]


def _is_under(node, root):
    return node.startswith(root + "|")


def _delete_construction_history(nodes):
    nodes = [node for node in nodes if cmds.objExists(node)]
    if not nodes:
        return
    try:
        cmds.delete(nodes, constructionHistory=True)
    except Exception:
        for node in nodes:
            try:
                cmds.delete(node, constructionHistory=True)
            except Exception:
                pass


def _mirror_pairs(pairs, axes, deferred_normals, layer_map):
    """Kế thừa attribute, xóa history không cần giữ, rồi lật. Trả về mesh đích."""
    jobs = []
    to_clear = []
    created = []
    for src, dst in pairs:
        try:
            _copy_user_attributes(src, dst)
            _retarget_message_attributes(src, dst)
            _remember_display_layer(src, dst, layer_map)
            dst_hist, owned = _split_dg_history(src, dst)
            keep_history = _has_live_deformer(dst, dst_hist)
            if dst_hist and not keep_history:
                to_clear.append(dst)
                owned = []
            jobs.append((src, dst, owned, keep_history))
        except Exception as exc:
            cmds.warning(u"Lỗi mirror '{0}': {1}".format(src, exc))

    _delete_construction_history(to_clear)
    for src, dst, owned, keep_history in jobs:
        try:
            _flip_shape(
                dst,
                axes,
                keep_history=keep_history,
                clear_history=False,
                deferred_normals=None if keep_history else deferred_normals,
            )
            _mirror_channels(None, dst, axes, owned=owned)
            _stamp_mirror_attr(dst, axes)
            created.append(dst)
        except Exception as exc:
            cmds.warning(u"Lỗi mirror '{0}': {1}".format(src, exc))
    return created


def _duplicate_mesh(mesh, copy_history):
    dup = cmds.duplicate(mesh, returnRootsOnly=True, upstreamNodes=copy_history)[0]
    dup = cmds.ls(dup, long=True)[0]
    dup = _match_parent(mesh, dup)
    short = mesh.split("|")[-1]
    dup = cmds.rename(dup, "{0}_Mirror_#".format(short))
    return cmds.ls(dup, long=True)[0]


def _duplicate_group(group):
    src_meshes = _ordered_meshes(group)
    dup = cmds.duplicate(group, returnRootsOnly=True)[0]
    dup = cmds.ls(dup, long=True)[0]
    dup = _match_parent(group, dup)
    short = group.split("|")[-1]
    dup = cmds.rename(dup, "{0}_Mirror_#".format(short))
    dup = cmds.ls(dup, long=True)[0]
    dst_meshes = _ordered_meshes(dup)
    if len(src_meshes) != len(dst_meshes):
        cmds.warning(u"Group '{0}' sau khi duplicate không cùng số mesh ({1} -> {2}).".format(
            group, len(src_meshes), len(dst_meshes)))
    return dup, list(zip(src_meshes, dst_meshes))


def _partition_selection(nodes):
    """Tách group và mesh lẻ. Mesh nằm trong group đang chọn thì để group đó lo."""
    groups = []
    loose = []
    for node in nodes or []:
        full = cmds.ls(node, long=True)
        if not full:
            continue
        node = full[0]
        if cmds.nodeType(node) == "mesh":
            parent = cmds.listRelatives(node, parent=True, fullPath=True)
            if not parent:
                continue
            node = parent[0]
        if cmds.nodeType(node) != "transform":
            continue
        if _is_mesh_transform(node):
            loose.append(node)
        elif _ordered_meshes(node):
            groups.append(node)

    groups = [group for group in groups if not any(group != other and _is_under(group, other) for other in groups)]
    loose = [mesh for mesh in loose if not any(_is_under(mesh, group) for group in groups)]
    return groups, loose


def mirror_meshes(nodes, axes):
    """Duplicate rồi lật. Group thì duplicate cả group trước. Trả về các mesh đã lật."""
    axes = _normalize_axes(axes)
    if not axes:
        cmds.warning(u"Chọn ít nhất 1 trục X, Y hoặc Z để mirror.")
        return []

    groups, loose = _partition_selection(nodes)
    if not groups and not loose:
        cmds.warning(u"Không có mesh để mirror. Hãy chọn mesh hoặc group chứa mesh.")
        return []

    created = []
    select_roots = []
    deferred_normals = []
    layer_map = {}
    previous = cmds.ls(selection=True, long=True) or []
    cmds.undoInfo(openChunk=True, chunkName="MT Mirror Mesh")
    suspended = False
    try:
        cmds.refresh(suspend=True)
        suspended = True

        bake_meshes = []
        for group in groups:
            if cmds.objExists(group):
                bake_meshes.extend(_ordered_meshes(group))
        bake_meshes.extend([mesh for mesh in loose if cmds.objExists(mesh)])
        _bake_pivot_positions(bake_meshes)

        for group in groups:
            try:
                if not cmds.objExists(group):
                    continue
                dup_group, pairs = _duplicate_group(group)
                select_roots.append(dup_group)
                created.extend(_mirror_pairs(pairs, axes, deferred_normals, layer_map))
            except Exception as exc:
                cmds.warning(u"Lỗi mirror group '{0}': {1}".format(group, exc))
        loose_pairs = []
        for mesh in loose:
            try:
                if not cmds.objExists(mesh):
                    continue
                dup = _duplicate_mesh(mesh, _has_construction_history(mesh))
                loose_pairs.append((mesh, dup))
            except Exception as exc:
                cmds.warning(u"Lỗi mirror '{0}': {1}".format(mesh, exc))
        if loose_pairs:
            mirrored = _mirror_pairs(loose_pairs, axes, deferred_normals, layer_map)
            created.extend(mirrored)
            select_roots.extend(mirrored)
    finally:
        try:
            _flush_deferred_normals(deferred_normals)
            _apply_display_layers(layer_map)
        except Exception as exc:
            cmds.warning(u"Không hoàn tất được bước mirror: {0}".format(exc))
        created = [mesh for mesh in created if cmds.objExists(mesh)]
        select_roots = [node for node in select_roots if cmds.objExists(node)]
        try:
            if select_roots:
                cmds.select(select_roots, replace=True)
            elif previous:
                cmds.select(previous, replace=True)
        except Exception:
            pass
        if suspended:
            cmds.refresh(suspend=False)
            cmds.refresh(force=True)
        cmds.undoInfo(closeChunk=True)

    if select_roots:
        om.MGlobal.displayInfo(u"Đã mirror {0} mesh theo trục {1}.".format(
            len(created), ", ".join(axis.upper() for axis in axes)))
    return created


def mirror_selected(axes=("x",)):
    selection = cmds.ls(selection=True, long=True) or []
    if not selection:
        cmds.warning(u"Hãy chọn mesh hoặc group cần mirror.")
        return []
    return mirror_meshes(selection, axes)