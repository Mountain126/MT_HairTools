import maya.cmds as cmds
import maya.api.OpenMaya as om
import math

def mirror_vector(vec, axis):
    if axis == 'X':
        return om.MVector(-vec.x, vec.y, vec.z)
    elif axis == 'Y':
        return om.MVector(vec.x, -vec.y, vec.z)
    elif axis == 'Z':
        return om.MVector(vec.x, vec.y, -vec.z)
    return om.MVector(vec)


def get_surface_distance_and_side(mesh_fn, point):
    maya_point = om.MPoint(point)
    closest_point, _ = mesh_fn.getClosestPoint(maya_point, om.MSpace.kWorld)
    normal, _ = mesh_fn.getClosestNormal(maya_point, om.MSpace.kWorld)
    signed_distance = (om.MVector(maya_point) - om.MVector(closest_point)) * om.MVector(normal).normal()
    side = -1.0 if signed_distance < 0.0 else 1.0
    return maya_point.distanceTo(closest_point), side


def wrap_angle(angle):
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def preserve_curve_proxy_distances(mesh_fn, points, surface_data):
    if len(points) < 3:
        return points

    root = points[0]
    axis = points[-1] - root
    if axis.length() < 1e-5:
        return points
    axis = axis.normal()

    angles = [0.0] * len(points)
    radii = [None] * len(points)
    for index in range(1, len(points) - 1):
        relative = points[index] - root
        axial = axis * (relative * axis)
        radii[index] = relative - axial

    def candidate_point(index, angle):
        rotation = om.MQuaternion(angle, axis)
        relative = points[index] - root
        axial = axis * (relative * axis)
        return root + axial + radii[index].rotateBy(rotation)

    def candidate_cost(index, angle):
        point = candidate_point(index, angle)
        target_distance, target_side = surface_data[index]
        distance, side = get_surface_distance_and_side(mesh_fn, point)
        distance_scale = max(target_distance, 0.1)
        cost = ((distance - target_distance) / distance_scale) ** 2
        if target_distance > 1e-5 and side != target_side:
            cost += 4.0

        smoothness_weight = 0.08
        for neighbor in (index - 1, index + 1):
            angle_delta = wrap_angle(angle - angles[neighbor])
            cost += smoothness_weight * (angle_delta / math.pi) ** 2
        return cost

    for _ in range(3):
        for index in range(1, len(points) - 1):
            best_angle = angles[index]
            best_cost = candidate_cost(index, best_angle)
            for step_degrees, search_radius in ((15.0, 180.0), (3.0, 15.0), (0.6, 3.0)):
                step = math.radians(step_degrees)
                radius = math.radians(search_radius)
                sample_count = int(round(2.0 * radius / step)) + 1
                center = best_angle
                for sample in range(sample_count):
                    candidate = wrap_angle(center - radius + sample * step)
                    cost = candidate_cost(index, candidate)
                    if cost < best_cost:
                        best_angle, best_cost = candidate, cost
            angles[index] = best_angle

    return [
        candidate_point(index, angles[index]) if 0 < index < len(points) - 1 else point
        for index, point in enumerate(points)
    ]


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

    import MT_HairTools
    proxy_shape = MT_HairTools.get_proxy_mesh()
    if not proxy_shape:
        cmds.warning("Không tìm thấy mesh shape của Proxy Mesh; không thể hiệu chỉnh khoảng cách Curve.")
        return

    mesh_fn = om.MFnMesh(om.MSelectionList().add(proxy_shape).getDagPath(0))

    cmds.undoInfo(openChunk=True)
    try:
        for shape in curve_shapes:
            cvs = cmds.ls(f"{shape}.cv[*]", flatten=True)
            if len(cvs) < 2:
                continue

            # 1. Lấy tọa độ World hiện tại của toàn bộ CV (1, 2, 3, 4...)
            pts = [
                om.MVector(*cmds.xform(cv, query=True, worldSpace=True, translation=True))
                for cv in cvs
            ]
            original_surface_data = [
                get_surface_distance_and_side(mesh_fn, point)
                for point in pts
            ]

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
                    new_pts = []
                    for p in pts:
                        d = p - p_root
                        d_rotated = d.rotateBy(q_swing)
                        new_pts.append(p_root_new + d_rotated)
                    pts = new_pts
                else:
                    # Trường hợp Curve kín (điểm đầu trùng điểm cuối): chỉ dịch tâm qua trục
                    pts = [ (p - p_root) + p_root_new for p in pts ]

            # 3. Tối ưu góc quanh trục gốc-ngọn để giữ khoảng cách Proxy mượt hơn.
            pts = preserve_curve_proxy_distances(mesh_fn, pts, original_surface_data)

            # 4. Gán đủ tọa độ XYZ sau khi hiệu chỉnh theo Proxy.
            for cv, transformed in zip(cvs, pts):
                cmds.xform(
                    cv,
                    worldSpace=True,
                    translation=(transformed.x, transformed.y, transformed.z)
                )

            # Đặt rotate/scale pivot của transform tại CV0 mới.
            parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
            if parents:
                root_position = cmds.xform(cvs[0], query=True, worldSpace=True, translation=True)
                cmds.xform(parents[0], worldSpace=True, pivots=root_position)

    finally:
        cmds.undoInfo(closeChunk=True)