# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import maya.cmds as cmds
import maya.api.OpenMaya as om
import math
import sys


def mirror_vector(vec, axis):
    if axis == 'X':
        return om.MVector(-vec.x, vec.y, vec.z)
    elif axis == 'Y':
        return om.MVector(vec.x, -vec.y, vec.z)
    elif axis == 'Z':
        return om.MVector(vec.x, vec.y, -vec.z)
    return om.MVector(vec)


class ProxySurface(object):
    """
    Bọc MMeshIntersector để truy vấn điểm gần nhất trên Proxy.
    MMeshIntersector dựng sẵn cấu trúc tăng tốc một lần, nên mỗi truy vấn nhanh hơn
    nhiều so với MFnMesh.getClosestPoint, và trả về cả điểm lẫn pháp tuyến trong một lần gọi.
    Maya 2018 có lỗi trong MMeshIntersector của API 2.0 (create() báo RuntimeError),
    khi đó lùi về MFnMesh.getClosestPointAndNormal: chậm hơn nhưng cho kết quả tương đương.
    """

    def __init__(self, dag_path):
        # Truy vấn trong object space (ma trận đơn vị) để không phụ thuộc
        # vào quy ước không gian của MPointOnMesh; tự đổi world <-> object bằng ma trận.
        self._matrix = dag_path.inclusiveMatrix()
        self._inverse = dag_path.inclusiveMatrixInverse()
        self._max_distance = sys.float_info.max
        self._intersector = None
        self._mesh_fn = None
        try:
            intersector = om.MMeshIntersector()
            intersector.create(dag_path.node(), om.MMatrix())
            self._intersector = intersector
        except Exception:
            self._mesh_fn = om.MFnMesh(dag_path)

    def _closest_local(self, local_point):
        """Điểm gần nhất và pháp tuyến tại đó, cả hai trong object space."""
        if self._intersector is not None:
            hit = self._intersector.getClosestPoint(local_point, self._max_distance)
            return om.MPoint(hit.point), om.MVector(hit.normal)
        closest, normal, _ = self._mesh_fn.getClosestPointAndNormal(local_point, om.MSpace.kObject)
        return om.MPoint(closest), om.MVector(normal)

    def distance_and_side(self, point):
        """Trả về (khoảng cách tới bề mặt trong world space, phía +1/-1 so với pháp tuyến)."""
        world_point = om.MPoint(point)
        local_point = world_point * self._inverse
        local_closest, local_normal = self._closest_local(local_point)

        # Dấu của tích vô hướng không đổi qua phép biến đổi affine (pháp tuyến biến đổi
        # theo ma trận nghịch đảo chuyển vị), nên xét phía ngay trong object space là đúng.
        side = -1.0 if (local_point - local_closest) * local_normal < 0.0 else 1.0
        world_closest = local_closest * self._matrix
        return world_point.distanceTo(world_closest), side


def wrap_angle(angle):
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


# Các bước tìm góc: (bước nhảy, bán kính tìm kiếm) tính bằng độ, đổi sẵn sang radian.
_SEARCH_STAGES = tuple(
    (math.radians(step), math.radians(radius), int(round(2.0 * radius / step)) + 1)
    for step, radius in ((15.0, 180.0), (3.0, 15.0), (0.6, 3.0))
)
_SMOOTHNESS_WEIGHT = 0.08


def preserve_curve_proxy_distances(surface, points, surface_data):
    if len(points) < 3:
        return points

    root = points[0]
    axis = points[-1] - root
    if axis.length() < 1e-5:
        return points
    axis = axis.normal()

    last = len(points) - 1
    angles = [0.0] * len(points)

    # Tính sẵn các đại lượng không đổi cho từng CV: tâm trên trục, bán kính r
    # và vector vuông góc (axis x r). Khi đó điểm xoay góc a theo công thức Rodrigues:
    # tâm + r*cos(a) + (axis x r)*sin(a), vì r luôn vuông góc với trục.
    centers = [None] * len(points)
    radii = [None] * len(points)
    binormals = [None] * len(points)
    for index in range(1, last):
        relative = points[index] - root
        axial = axis * (relative * axis)
        centers[index] = root + axial
        radii[index] = relative - axial
        binormals[index] = axis ^ radii[index]

    def candidate_point(index, angle):
        return centers[index] + radii[index] * math.cos(angle) + binormals[index] * math.sin(angle)

    # Phần cost theo khoảng cách Proxy chỉ phụ thuộc (CV, góc), không phụ thuộc góc
    # của CV lân cận, nên lưu lại để không phải truy vấn lại các góc trùng nhau
    # (tâm của mỗi bước tìm, hai đầu -180/+180, và góc tốt nhất ở vòng lặp sau).
    surface_cache = [dict() for _ in points]

    def surface_cost(index, angle):
        key = round(angle, 10)
        cache = surface_cache[index]
        cost = cache.get(key)
        if cost is None:
            target_distance, target_side = surface_data[index]
            distance, side = surface.distance_and_side(candidate_point(index, angle))
            distance_scale = max(target_distance, 0.1)
            cost = ((distance - target_distance) / distance_scale) ** 2
            if target_distance > 1e-5 and side != target_side:
                cost += 4.0
            cache[key] = cost
        return cost

    def candidate_cost(index, angle):
        cost = surface_cost(index, angle)
        for neighbor in (index - 1, index + 1):
            angle_delta = wrap_angle(angle - angles[neighbor])
            cost += _SMOOTHNESS_WEIGHT * (angle_delta / math.pi) ** 2
        return cost

    for _ in range(3):
        for index in range(1, last):
            best_angle = angles[index]
            best_cost = candidate_cost(index, best_angle)
            for step, radius, sample_count in _SEARCH_STAGES:
                start = best_angle - radius
                for sample in range(sample_count):
                    candidate = wrap_angle(start + sample * step)
                    cost = candidate_cost(index, candidate)
                    if cost < best_cost:
                        best_angle, best_cost = candidate, cost
            angles[index] = best_angle

    return [
        candidate_point(index, angles[index]) if 0 < index < last else point
        for index, point in enumerate(points)
    ]


def _get_proxy_surface():
    proxy_list = cmds.ls('*.isHairCardProxy', objectsOnly=True) or []
    if not proxy_list:
        return None
    proxy_shapes = cmds.listRelatives(
        proxy_list[0], allDescendents=True, type='mesh', fullPath=True
    ) or []
    if not proxy_shapes:
        return None
    return ProxySurface(om.MSelectionList().add(proxy_shapes[0]).getDagPath(0))


def swing_flip_curves(mirror_axes):
    """
    Lật các đường NURBS Curve đang chọn qua các trục X, Y, Z
    bằng cách xoay vector gốc-ngọn (CV[0] -> CV[-1]) và giữ nguyên hình dáng cong.
    """
    selection = cmds.ls(selection=True, long=True)
    if not selection:
        cmds.warning("Vui lòng chọn ít nhất một đường Curve.")
        return

    if not mirror_axes:
        cmds.warning("Vui lòng bật ít nhất một trục lật (X, Y hoặc Z).")
        return

    # Lấy tất cả node nurbsCurve từ danh sách đang chọn
    curve_shapes = []
    for obj in selection:
        if cmds.nodeType(obj) == "nurbsCurve":
            curve_shapes.append(obj)
        else:
            shapes = cmds.listRelatives(obj, shapes=True, fullPath=True, type="nurbsCurve") or []
            curve_shapes.extend(shapes)

    if not curve_shapes:
        cmds.warning("Không tìm thấy NURBS Curve nào trong đối tượng đang chọn.")
        return

    surface = _get_proxy_surface()

    cmds.undoInfo(openChunk=True)
    try:
        for shape in curve_shapes:
            # 1. Đọc tọa độ World của toàn bộ CV bằng API trong một lần gọi
            #    (thay cho việc gọi cmds.xform query từng CV).
            curve_fn = om.MFnNurbsCurve(om.MSelectionList().add(shape).getDagPath(0))
            pts = [om.MVector(p) for p in curve_fn.cvPositions(om.MSpace.kWorld)]
            if len(pts) < 2:
                continue

            original_surface_data = (
                [surface.distance_and_side(point) for point in pts]
                if surface is not None else None
            )

            # 2. Lần lượt biến đổi tọa độ qua từng trục được kích hoạt
            for axis in mirror_axes:
                p_root = pts[0]   # Điểm 1 (Gốc)
                p_tip = pts[-1]   # Điểm 4 (Ngọn)

                # Vector đường màu vàng ban đầu (từ 1 đến 4)
                v_orig = p_tip - p_root

                # Điểm gốc mới sau khi lật qua trục
                p_root_new = mirror_vector(p_root, axis)

                # Nếu điểm đầu và điểm cuối không trùng nhau
                if v_orig.length() > 1e-5:
                    # Vector đường màu vàng mới
                    v_new = mirror_vector(v_orig, axis)

                    # Tính Quaternion xoay ngắn nhất từ đường vàng cũ sang đường vàng mới
                    q_swing = om.MQuaternion(v_orig.normal(), v_new.normal())

                    # Tính tọa độ mới cho từng CV dựa trên độ lệch so với điểm gốc 1
                    pts = [p_root_new + (p - p_root).rotateBy(q_swing) for p in pts]
                else:
                    # Trường hợp Curve kín (điểm đầu trùng điểm cuối): chỉ dịch tâm qua trục
                    pts = [(p - p_root) + p_root_new for p in pts]

            # 3. Tối ưu góc quanh trục gốc-ngọn để giữ khoảng cách Proxy mượt hơn.
            if surface is not None:
                pts = preserve_curve_proxy_distances(surface, pts, original_surface_data)

            # 4. Gán tọa độ bằng cmds.xform để thao tác vẫn Undo được
            #    (ghi trực tiếp bằng OpenMaya sẽ không vào undo chunk).
            for index, transformed in enumerate(pts):
                cmds.xform(
                    "{0}.cv[{1}]".format(shape, index),
                    worldSpace=True,
                    translation=(transformed.x, transformed.y, transformed.z)
                )

            # Đặt rotate/scale pivot của transform tại CV0 mới.
            parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
            if parents:
                root = pts[0]
                cmds.xform(parents[0], worldSpace=True, pivots=(root.x, root.y, root.z))

    finally:
        cmds.undoInfo(closeChunk=True)
