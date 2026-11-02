# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import maya.cmds as cmds
import maya.api.OpenMaya as om2
import math
import random

# ==========================================
# CÁC HÀM TOÁN HỌC & TIỆN ÍCH BỔ TRỢ
# ==========================================
def get_safe_orthogonal(tangent, normal):
    vec = tangent - (tangent * normal) * normal
    if vec.length() < 1e-4:
        fallback = om2.MVector(1, 0, 0)
        if abs(normal * fallback) > 0.99: 
            fallback = om2.MVector(0, 1, 0)
        vec = fallback - (fallback * normal) * normal
    return vec.normal()

def get_proxy_mesh():
    proxy_list = cmds.ls('*.isHairCardProxy', objectsOnly=True)
    if not proxy_list:
        cmds.warning(u"Chưa có Proxy Mesh! Hãy chọn Mesh và bấm Set Proxy.")
        return None
    shapes = cmds.listRelatives(proxy_list[0], allDescendents=True, type='mesh', fullPath=True)
    return shapes[0] if shapes else None

def update_proxy_ui_display():
    if cmds.textField("mt_proxy_textfield", exists=True):
        proxies = cmds.ls('*.isHairCardProxy', objectsOnly=True)
        if proxies:
            cmds.textField("mt_proxy_textfield", edit=True, text=proxies[0])
        else:
            # Sửa chuỗi rỗng "" thành dòng thông báo của bạn
            cmds.textField("mt_proxy_textfield", edit=True, text="Chưa Set/ Đã gỡ bỏ Proxy")

# --- Helper cho hàm Voronoi Relax ---
def build_spatial_grid(points, cell_size):
    grid = {}
    for i, p in enumerate(points):
        cx, cy, cz = int(p.x/cell_size), int(p.y/cell_size), int(p.z/cell_size)
        if (cx,cy,cz) not in grid: grid[(cx,cy,cz)] = []
        grid[(cx,cy,cz)].append(i)
    return grid

def get_neighbors(p, points, grid, cell_size, radius):
    neighbors = []
    cx, cy, cz = int(p.x/cell_size), int(p.y/cell_size), int(p.z/cell_size)
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            for dz in [-1, 0, 1]:
                cell = (cx+dx, cy+dy, cz+dz)
                if cell in grid:
                    for idx in grid[cell]:
                        if points[idx].distanceTo(p) <= radius:
                            neighbors.append(idx)
    return neighbors

# ==========================================
# CÁC HÀM TÍNH NĂNG CHÍNH
# ==========================================
def set_proxy():
    sel = cmds.ls(selection=True, type='transform')
    if not sel: 
        return cmds.warning(u"Hãy chọn Mesh để làm Proxy.")
    
    old_proxies = cmds.ls('*.isHairCardProxy', objectsOnly=True)
    for obj in old_proxies:
        cmds.deleteAttr(obj + ".isHairCardProxy")
        
    if not cmds.attributeQuery("isHairCardProxy", node=sel[0], exists=True):
        cmds.addAttr(sel[0], longName="isHairCardProxy", attributeType='bool')
    cmds.setAttr(sel[0] + ".isHairCardProxy", True)
    
    update_proxy_ui_display()
    om2.MGlobal.displayInfo(u"Đã thiết lập {} làm Proxy Mesh.".format(sel[0]))

def clear_proxy():
    # Quét toàn bộ scene để tìm các object đang được gắn thẻ Proxy
    proxies = cmds.ls('*.isHairCardProxy', objectsOnly=True)
    
    if not proxies:
        return om2.MGlobal.displayInfo(u"Hiện không có Proxy Mesh nào được thiết lập.")
        
    count = 0
    for obj in proxies:
        try:
            cmds.deleteAttr(obj + ".isHairCardProxy")
            count += 1
        except Exception:
            pass
            
    # Cập nhật lại giao diện (ô textField sẽ tự động trống)
    update_proxy_ui_display()
    
    om2.MGlobal.displayInfo(u"Đã gỡ bỏ Proxy Mesh thành công.")

def snap_curve():
    proxy_shape = get_proxy_mesh()
    if not proxy_shape: return
    
    raw_sel = cmds.ls(selection=True, long=True)
    if not raw_sel: return cmds.warning(u"Hãy chọn Curve hoặc các CVs để Snap.")
    
    valid_pairs = []
    for item in raw_sel:
        base_node = item.split(".")[0]
        transform_node = None
        shape_node = None
        
        if cmds.nodeType(base_node) == 'nurbsCurve':
            shape_node = base_node
            parents = cmds.listRelatives(base_node, parent=True, fullPath=True)
            if parents: transform_node = parents[0]
        else:
            shapes = cmds.listRelatives(base_node, shapes=True, type='nurbsCurve', fullPath=True)
            if shapes:
                transform_node = base_node
                shape_node = shapes[0]
                
        if transform_node and shape_node:
            valid_pairs.append((transform_node, shape_node))
            
    processed = set()
    unique_pairs = []
    for t_node, s_node in valid_pairs:
        if t_node not in processed:
            processed.add(t_node)
            unique_pairs.append((t_node, s_node))
            
    if not unique_pairs: return cmds.warning(u"Không tìm thấy NURBS Curve hợp lệ từ vùng chọn.")

    mesh_fn = om2.MFnMesh(om2.MSelectionList().add(proxy_shape).getDagPath(0))
    
    for trs, shp in unique_pairs:
        cvs = cmds.ls("{}.cv[*]".format(shp), flatten=True)
        if not cvs: continue
        
        pt0 = om2.MPoint(cmds.xform(cvs[0], query=True, worldSpace=True, translation=True))
        cp, _ = mesh_fn.getClosestPoint(pt0, om2.MSpace.kWorld)
        delta = om2.MVector(cp) - om2.MVector(pt0)
        
        for cv in cvs: cmds.xform(cv, translation=(delta.x, delta.y, delta.z), relative=True, worldSpace=True)
            
        new_pt0 = cmds.xform("{}.cv[0]".format(shp), query=True, worldSpace=True, translation=True)
        cmds.xform(trs, pivots=(new_pt0[0], new_pt0[1], new_pt0[2]), worldSpace=True)
        
    om2.MGlobal.displayInfo(u"Đã Snap toàn bộ Curve xuống Proxy cho {} curve(s).".format(len(unique_pairs)))

def snap_cv0():
    proxy_shape = get_proxy_mesh()
    if not proxy_shape: return
    
    raw_sel = cmds.ls(selection=True, long=True)
    if not raw_sel: return cmds.warning(u"Hãy chọn Curve hoặc các CVs để Snap.")
    
    valid_pairs = []
    for item in raw_sel:
        base_node = item.split(".")[0]
        transform_node = None
        shape_node = None
        
        if cmds.nodeType(base_node) == 'nurbsCurve':
            shape_node = base_node
            parents = cmds.listRelatives(base_node, parent=True, fullPath=True)
            if parents: transform_node = parents[0]
        else:
            shapes = cmds.listRelatives(base_node, shapes=True, type='nurbsCurve', fullPath=True)
            if shapes:
                transform_node = base_node
                shape_node = shapes[0]
                
        if transform_node and shape_node:
            valid_pairs.append((transform_node, shape_node))
            
    processed = set()
    unique_pairs = []
    for t_node, s_node in valid_pairs:
        if t_node not in processed:
            processed.add(t_node)
            unique_pairs.append((t_node, s_node))
            
    if not unique_pairs: return cmds.warning(u"Không tìm thấy NURBS Curve hợp lệ từ vùng chọn.")

    mesh_fn = om2.MFnMesh(om2.MSelectionList().add(proxy_shape).getDagPath(0))
    
    for trs, shp in unique_pairs:
        cv0_name = "{}.cv[0]".format(shp)
        if not cmds.objExists(cv0_name): continue
        
        pt0 = om2.MPoint(cmds.xform(cv0_name, query=True, worldSpace=True, translation=True))
        cp, _ = mesh_fn.getClosestPoint(pt0, om2.MSpace.kWorld)
        delta = om2.MVector(cp) - om2.MVector(pt0)
        
        cmds.xform(cv0_name, translation=(delta.x, delta.y, delta.z), relative=True, worldSpace=True)
        new_pt0 = cmds.xform(cv0_name, query=True, worldSpace=True, translation=True)
        cmds.xform(trs, pivots=(new_pt0[0], new_pt0[1], new_pt0[2]), worldSpace=True)
        
    om2.MGlobal.displayInfo(u"Đã Snap điểm gốc cho {} curve(s).".format(len(unique_pairs)))

def set_guides():
    raw_sel = cmds.ls(selection=True, long=True)
    if not raw_sel: return cmds.warning(u"Hãy chọn các curve làm Guide.")
    count = 0
    all_nodes = cmds.listRelatives(raw_sel, allDescendents=True, fullPath=True) or []
    all_nodes.extend(raw_sel)
    for obj in all_nodes:
        if cmds.nodeType(obj) == 'nurbsCurve':
            parent = cmds.listRelatives(obj, parent=True, fullPath=True)[0]
            if not cmds.attributeQuery("isHairFlowGuide", node=parent, exists=True):
                cmds.addAttr(parent, longName="isHairFlowGuide", attributeType='bool')
            cmds.setAttr(parent + ".isHairFlowGuide", True)
            cmds.setAttr(obj + ".overrideEnabled", 1)
            cmds.setAttr(obj + ".overrideRGBColors", 1)
            cmds.setAttr(obj + ".overrideColorRGB", 1.0, 0.0, 0.0)
            count += 1
    om2.MGlobal.displayInfo(u"Đã thiết lập {} Guides.".format(count))

def clear_guides():
    for g in cmds.ls('*.isHairFlowGuide', objectsOnly=True):
        shapes = cmds.listRelatives(g, shapes=True, type='nurbsCurve', fullPath=True)
        if shapes: cmds.setAttr(shapes[0] + ".overrideEnabled", 0)
        cmds.deleteAttr(g + ".isHairFlowGuide")
    om2.MGlobal.displayInfo(u"Đã xoá Guides.")

def distribute_curves(iterations=15):
    proxy_shape = get_proxy_mesh()
    if not proxy_shape: return
    
    raw_sel = cmds.ls(selection=True, long=True)
    curves = []
    for obj in raw_sel:
        if cmds.nodeType(obj) == 'nurbsCurve':
            p = cmds.listRelatives(obj, parent=True, fullPath=True)
            if p: curves.append(p[0])
        elif cmds.nodeType(obj) == 'transform':
            if cmds.listRelatives(obj, shapes=True, type='nurbsCurve'): curves.append(obj)
            
    curves = list(set(curves))
    num_curves = len(curves)
    if num_curves < 3: return cmds.warning(u"Hãy chọn ít nhất 3 curve để giãn cách.")

    sel_list = om2.MSelectionList()
    sel_list.add(proxy_shape)
    mesh_fn = om2.MFnMesh(sel_list.getDagPath(0))

    roots = [om2.MPoint(cmds.xform("{}.cv[0]".format(c), q=True, ws=True, t=True)) for c in curves]

    avg_spacing = 0.0
    for p in roots:
        dists = [p.distanceTo(roots[j]) for j in range(num_curves) if roots[j] != p]
        dists.sort()
        avg_spacing += sum(dists[:4]) / 4.0 if dists else 0.0
    avg_spacing /= num_curves

    cell_size = avg_spacing * 3.0
    root_grid = build_spatial_grid(roots, cell_size)

    raw_samples = []
    visited_voxels = set()
    sample_res = avg_spacing * 0.35 

    for p in roots:
        normal, _ = mesh_fn.getClosestNormal(p, om2.MSpace.kWorld)
        N = om2.MVector(normal).normal()
        up = om2.MVector(0, 1, 0)
        if abs(N * up) > 0.99: up = om2.MVector(1, 0, 0)
        tx = (up ^ N).normal()
        ty = (N ^ tx).normal()
        
        steps = [-1.5, -1.0, -0.5, 0, 0.5, 1.0, 1.5]
        for dx in steps:
            for dy in steps:
                test_p = p + tx*(dx*avg_spacing) + ty*(dy*avg_spacing)
                cp, _ = mesh_fn.getClosestPoint(om2.MPoint(test_p), om2.MSpace.kWorld)
                
                vx, vy, vz = int(cp.x/sample_res), int(cp.y/sample_res), int(cp.z/sample_res)
                if (vx, vy, vz) not in visited_voxels:
                    visited_voxels.add((vx, vy, vz))
                    raw_samples.append(om2.MPoint(cp))

    valid_samples = []
    for S in raw_samples:
        neighbors = get_neighbors(S, roots, root_grid, cell_size, avg_spacing * 2.5)
        if len(neighbors) < 3: continue
        
        normal, _ = mesh_fn.getClosestNormal(S, om2.MSpace.kWorld)
        N = om2.MVector(normal).normal()
        up = om2.MVector(0, 1, 0)
        if abs(N * up) > 0.99: up = om2.MVector(1, 0, 0)
        tx = (up ^ N).normal()
        ty = (N ^ tx).normal()
        
        angles = []
        for n_idx in neighbors:
            v = om2.MVector(roots[n_idx]) - om2.MVector(S)
            angles.append(math.atan2(v * ty, v * tx))
        
        angles.sort()
        max_gap = 2 * math.pi - (angles[-1] - angles[0])
        for k in range(1, len(angles)):
            gap = angles[k] - angles[k-1]
            if gap > max_gap: max_gap = gap
            
        if max_gap <= math.radians(170): 
            valid_samples.append(S)

    is_boundary = [False] * num_curves
    for i, root in enumerate(roots):
        neighbors = get_neighbors(root, roots, root_grid, cell_size, avg_spacing * 2.5)
        if len(neighbors) < 3:
            is_boundary[i] = True
            continue
        
        normal, _ = mesh_fn.getClosestNormal(root, om2.MSpace.kWorld)
        N = om2.MVector(normal).normal()
        up = om2.MVector(0, 1, 0)
        if abs(N * up) > 0.99: up = om2.MVector(1, 0, 0)
        tx = (up ^ N).normal()
        ty = (N ^ tx).normal()
        
        angles = []
        for n_idx in neighbors:
            if n_idx == i: continue
            v = om2.MVector(roots[n_idx]) - om2.MVector(root)
            angles.append(math.atan2(v * ty, v * tx))
            
        angles.sort()
        max_gap = 2 * math.pi - (angles[-1] - angles[0])
        for k in range(1, len(angles)):
            gap = angles[k] - angles[k-1]
            if gap > max_gap: max_gap = gap
            
        if max_gap > math.radians(150):
            is_boundary[i] = True

    for _ in range(iterations):
        root_grid = build_spatial_grid(roots, cell_size)
        centroids = {i: om2.MVector(0,0,0) for i in range(num_curves)}
        counts = {i: 0 for i in range(num_curves)}
        
        for S in valid_samples:
            neighbors = get_neighbors(S, roots, root_grid, cell_size, avg_spacing * 3.0)
            if not neighbors: continue
            
            min_d, closest_i = float('inf'), -1
            for n_idx in neighbors:
                d = S.distanceTo(roots[n_idx])
                if d < min_d:
                    min_d, closest_i = d, n_idx
            
            if closest_i != -1:
                centroids[closest_i] += om2.MVector(S)
                counts[closest_i] += 1
                
        for i in range(num_curves):
            if not is_boundary[i] and counts[i] > 0:
                avg_p = centroids[i] / counts[i]
                cp, _ = mesh_fn.getClosestPoint(om2.MPoint(avg_p), om2.MSpace.kWorld)
                roots[i] = om2.MPoint(cp)

    for i, crv in enumerate(curves):
        if not is_boundary[i]:
            orig_pos = om2.MPoint(cmds.xform("{}.cv[0]".format(crv), q=True, ws=True, t=True))
            delta = om2.MVector(roots[i]) - om2.MVector(orig_pos)
            if delta.length() > 0.0001:
                cmds.xform(crv, translation=(delta.x, delta.y, delta.z), relative=True, worldSpace=True)

    cmds.select(curves)
    om2.MGlobal.displayInfo(u"Đã phân bổ đồng đều các đường Curve")

def randomize_curves(rot_intensity=0.5, move_radius=0.1):
    proxy_shape = get_proxy_mesh()
    if not proxy_shape: return
    
    raw_sel = cmds.ls(selection=True, long=True)
    curves = list(set([cmds.listRelatives(c, p=True, f=True)[0] if cmds.nodeType(c)=='nurbsCurve' else c for c in raw_sel]))
    if not curves: return cmds.warning(u"Hãy chọn Curves để Randomize.")
    
    mesh_fn = om2.MFnMesh(om2.MSelectionList().add(proxy_shape).getDagPath(0))
    
    max_yaw = 40.0 * rot_intensity
    max_pitch = 20.0 * rot_intensity
    
    for crv in curves:
        cvs = cmds.ls("{}.cv[*]".format(crv), flatten=True)
        if len(cvs) < 2: continue
        
        pt0 = om2.MPoint(cmds.xform(cvs[0], query=True, worldSpace=True, translation=True))
        normal, _ = mesh_fn.getClosestNormal(pt0, om2.MSpace.kWorld)
        N = om2.MVector(normal).normal()
        
        if move_radius > 0.001:
            up = om2.MVector(0, 1, 0)
            if abs(N * up) > 0.99: up = om2.MVector(1, 0, 0)
            tx = (up ^ N).normal()
            ty = (N ^ tx).normal()
            
            r = random.uniform(0, move_radius)
            theta = random.uniform(0, 2 * math.pi)
            offset = tx * (r * math.cos(theta)) + ty * (r * math.sin(theta))
            test_p = pt0 + offset
            
            cp, _ = mesh_fn.getClosestPoint(om2.MPoint(test_p), om2.MSpace.kWorld)
            delta_move = om2.MVector(cp) - om2.MVector(pt0)
            
            for cv in cvs:
                cmds.xform(cv, translation=(delta_move.x, delta_move.y, delta_move.z), relative=True, worldSpace=True)
                
            pt0 = om2.MPoint(cmds.xform(cvs[0], query=True, worldSpace=True, translation=True))
            normal, _ = mesh_fn.getClosestNormal(pt0, om2.MSpace.kWorld)
            N = om2.MVector(normal).normal()

        if rot_intensity > 0.001:
            yaw = math.radians(random.uniform(-max_yaw, max_yaw))
            pitch = math.radians(random.uniform(-max_pitch, max_pitch))
            
            v_sum = om2.MVector(0,0,0)
            for i in range(1, len(cvs)):
                v_sum += om2.MVector(cmds.xform(cvs[i], q=True, ws=True, t=True)) - om2.MVector(pt0)
                
            cur_dir = (v_sum / (len(cvs)-1)).normal()
            
            right = get_safe_orthogonal(cur_dir, N)
            quat = om2.MQuaternion(pitch, right) * om2.MQuaternion(yaw, N)
            
            for i in range(1, len(cvs)):
                v = (om2.MVector(cmds.xform(cvs[i], q=True, ws=True, t=True)) - om2.MVector(pt0)).rotateBy(quat)
                cmds.xform(cvs[i], worldSpace=True, translation=(pt0.x+v.x, pt0.y+v.y, pt0.z+v.z))
                
        # --- BỔ SUNG: CẬP NHẬT PIVOT ---
        # Sau khi hoàn tất cả lệnh Move và Rotate, lấy lại vị trí cuối cùng của cv[0]
        final_pt0 = cmds.xform(cvs[0], query=True, worldSpace=True, translation=True)
        # Gắn Pivot của Transform node về toạ độ của final_pt0
        cmds.xform(crv, pivots=(final_pt0[0], final_pt0[1], final_pt0[2]), worldSpace=True)
                
    om2.MGlobal.displayInfo(u"Đã Random Transform Curves (Move: {}, Rot: {})".format(move_radius, rot_intensity))

def random_flip_uv():
    raw_sel = cmds.ls(selection=True, long=True)
    if not raw_sel: 
        return cmds.warning(u"Hãy chọn các Curve để Random Flip UV.")
    
    # 1. Lọc lấy danh sách các Curve hợp lệ từ vùng chọn
    curves = []
    for item in raw_sel:
        base_node = item.split(".")[0]
        if cmds.nodeType(base_node) == 'nurbsCurve':
            parents = cmds.listRelatives(base_node, parent=True, fullPath=True)
            if parents: curves.append(parents[0])
        else:
            shapes = cmds.listRelatives(base_node, shapes=True, type='nurbsCurve', fullPath=True)
            if shapes: curves.append(base_node)
            
    curves = list(set(curves))
    if not curves:
        return cmds.warning(u"Không tìm thấy NURBS Curve hợp lệ từ vùng chọn.")
        
    # 2. Lấy ngẫu nhiên 50% số lượng curve
    num_to_flip = len(curves) // 2
    if num_to_flip == 0 and len(curves) == 1:
        # Nếu người dùng chỉ chọn 1 sợi, random 50/50 cơ hội lật
        if random.random() > 0.5: num_to_flip = 1
        
    if num_to_flip == 0:
        return om2.MGlobal.displayInfo(u"Không có Mesh nào được lật (Xác suất 50%).")
        
    curves_to_flip = random.sample(curves, num_to_flip)
    
    # 3. Tìm các Mesh nằm chung Group (cùng cấp cha) với các Curve đã chọn
    meshes_to_flip = []
    for crv in curves_to_flip:
        parent_group = cmds.listRelatives(crv, parent=True, fullPath=True)
        if not parent_group: continue
        
        # Quét tất cả các anh em (siblings) trong cùng 1 Group cha
        siblings = cmds.listRelatives(parent_group[0], children=True, fullPath=True) or []
        for sib in siblings:
            if sib == crv: continue
            
            # Kiểm tra nếu sibling này là Transform chứa Mesh (geoCard)
            shapes = cmds.listRelatives(sib, shapes=True, type='mesh', fullPath=True)
            if shapes:
                # Chỉ lấy mesh hiển thị (Bỏ qua intermediate objects ẩn sinh ra do Lattice/Twist)
                for shp in shapes:
                    if not cmds.getAttr(shp + ".intermediateObject"):
                        meshes_to_flip.append(sib)
                        break
                        
    meshes_to_flip = list(set(meshes_to_flip))
    
    if not meshes_to_flip:
        return cmds.warning(u"Không tìm thấy Mesh (geoCard) nào chung Group với các Curve được chọn.")
        
    # 4. Thực hiện lật UV chiều ngang (Horizontal) tại tâm local
    for mesh in meshes_to_flip:
        try:
            # .map[*] nhắm vào toàn bộ UV, flipType=0 (Horizontal), local=True (Lật tại tâm của chính mảng UV đó)
            cmds.polyFlipUV(mesh + ".map[*]", flipType=0, local=True)
        except Exception as e:
            pass # Bỏ qua nếu mesh gặp lỗi lịch sử node
            
    om2.MGlobal.displayInfo(u"Đã Random Flip UV ngẫu nhiên 50% số lượng ({} Mesh được lật ngang).".format(len(meshes_to_flip)))
    cmds.select(raw_sel) # Trả lại vùng chọn ban đầu để thao tác tiếp

def generate_curves(count=100, length=5.0, cvs_count=6):
    selection = om2.MGlobal.getActiveSelectionList()
    if selection.length() == 0: return cmds.warning(u"Hãy chọn Faces trên Proxy Mesh!")
    dag_path, component = selection.getComponent(0)
    if component.isNull() or component.apiType() != om2.MFn.kMeshPolygonComponent:
        return cmds.warning(u"Vui lòng chọn Face (Polygon).")

    mesh_fn = om2.MFnMesh(dag_path)
    all_points = mesh_fn.getPoints(om2.MSpace.kWorld)
    triangles, total_area = [], 0.0
    
    it_poly = om2.MItMeshPolygon(dag_path, component)
    while not it_poly.isDone():
        _, tri_indices = it_poly.getTriangles()
        for i in range(0, len(tri_indices), 3):
            p0, p1, p2 = all_points[tri_indices[i]], all_points[tri_indices[i+1]], all_points[tri_indices[i+2]]
            v0, v1, v2 = om2.MVector(p0), om2.MVector(p1), om2.MVector(p2)
            area = 0.5 * ((v1 - v0) ^ (v2 - v0)).length()
            triangles.append({'p0': p0, 'p1': p1, 'p2': p2, 'area': area})
            total_area += area
        it_poly.next()

    new_curves = []
    for tri in triangles:
        num_hairs = int((tri['area'] / total_area) * count)
        if random.random() < (((tri['area'] / total_area) * count) - num_hairs): num_hairs += 1 
        for _ in range(num_hairs):
            r1, r2 = random.random(), random.random()
            sqrt_r1 = math.sqrt(r1)
            u, v, w = 1.0 - sqrt_r1, sqrt_r1 * (1.0 - r2), sqrt_r1 * r2
            pos = om2.MPoint(u*tri['p0'].x + v*tri['p1'].x + w*tri['p2'].x, u*tri['p0'].y + v*tri['p1'].y + w*tri['p2'].y, u*tri['p0'].z + v*tri['p1'].z + w*tri['p2'].z)
            normal, _ = mesh_fn.getClosestNormal(pos, om2.MSpace.kWorld)
            N = normal.normal()
            
            cv_positions = [(pos.x + N.x * (length/(cvs_count-1)) * i, pos.y + N.y * (length/(cvs_count-1)) * i, pos.z + N.z * (length/(cvs_count-1)) * i) for i in range(cvs_count)]
            crv = cmds.curve(d=3 if cvs_count >= 4 else 1, p=cv_positions)
            cmds.xform(crv, pivots=(cv_positions[0][0], cv_positions[0][1], cv_positions[0][2]), worldSpace=True)
            new_curves.append(crv)

    if new_curves:
        cmds.group(new_curves, name="GeneratedHair_GRP#")
        cmds.select(new_curves)
        om2.MGlobal.displayInfo(u"Đã sinh ra {} curves.".format(len(new_curves)))
        
        distribute_curves(iterations=15)
        
        match = True
        pres_len = False
        blend = 2.0
        lift = 15.0
        
        if cmds.window("MTHairToolsUI", exists=True):
            match = cmds.checkBox('mt_hair_match', query=True, value=True)
            pres_len = cmds.checkBox('mt_hair_pres_len', query=True, value=True)
            if cmds.floatSliderGrp('mt_hair_blend', exists=True):
                blend = cmds.floatSliderGrp('mt_hair_blend', query=True, value=True)
                lift = cmds.floatSliderGrp('mt_hair_lift', query=True, value=True)
                
        align_and_deform_curves(match_shape=match, preserve_len=pres_len, blend=blend, min_lift=lift)

def align_and_deform_curves(match_shape=True, preserve_len=False, blend=2.0, min_lift=15.0):
    raw_sel = cmds.ls(selection=True, long=True)
    if not raw_sel: return cmds.warning(u"Không có curve mục tiêu nào được chọn.")
    
    curves = []
    all_nodes = cmds.listRelatives(raw_sel, allDescendents=True, fullPath=True) or []
    all_nodes.extend(raw_sel)
    for obj in all_nodes:
        if cmds.nodeType(obj) == 'nurbsCurve':
            parent = cmds.listRelatives(obj, parent=True, fullPath=True)[0]
            if not cmds.attributeQuery("isHairFlowGuide", node=parent, exists=True): curves.append(parent)
    curves = list(set(curves))
    if not curves: return
    try: cmds.makeIdentity(curves, apply=True, t=1, r=1, s=1, n=0)
    except: pass

    proxy_shape = get_proxy_mesh()
    if not proxy_shape: return
    mesh_fn = om2.MFnMesh(om2.MSelectionList().add(proxy_shape).getDagPath(0))

    guides = cmds.ls('*.isHairFlowGuide', objectsOnly=True)
    if not guides: return cmds.warning(u"Chưa có Guide nào được thiết lập!")

    guide_data = []
    for g in guides:
        g_fn = om2.MFnNurbsCurve(om2.MSelectionList().add(cmds.listRelatives(g, shapes=True, fullPath=True)[0]).getDagPath(0))
        p_start, p_end = g_fn.findParamFromLength(0.0), g_fn.findParamFromLength(g_fn.length())
        pt0 = g_fn.getPointAtParam(p_start, om2.MSpace.kWorld)
        normal, _ = mesh_fn.getClosestNormal(pt0, om2.MSpace.kWorld)
        Y_axis = normal.normal()
        X_axis = get_safe_orthogonal((om2.MVector(g_fn.getPointAtParam(p_end, om2.MSpace.kWorld)) - om2.MVector(pt0)).normal(), Y_axis)
        Z_axis = (X_axis ^ Y_axis).normal()
        g_matrix = om2.MMatrix([X_axis.x, X_axis.y, X_axis.z, 0.0, Y_axis.x, Y_axis.y, Y_axis.z, 0.0, Z_axis.x, Z_axis.y, Z_axis.z, 0.0, pt0.x, pt0.y, pt0.z, 1.0])
        guide_data.append({'fn': g_fn, 'pt0': pt0, 'tangent': X_axis, 'inv_mat': g_matrix.inverse()})

    for crv in curves:
        cvs = cmds.ls("{}.cv[*]".format(crv), flatten=True)
        num_cvs = len(cvs)
        if num_cvs < 2: continue
        pt0 = om2.MPoint(cmds.xform(cvs[0], query=True, ws=True, t=True))
        normal, _ = mesh_fn.getClosestNormal(pt0, om2.MSpace.kWorld)
        target_Y = normal.normal()

        guide_dists = sorted([(pt0.distanceTo(gd['pt0']), gd) for gd in guide_data], key=lambda x: x[0])[:3]
        total_w = sum(1.0 / (math.pow(d, blend) + 1e-5) for d, _ in guide_dists)
        blend_X = om2.MVector(0,0,0)
        for d, gd in guide_dists: blend_X += gd['tangent'] * ((1.0 / (math.pow(d, blend) + 1e-5)) / total_w)
            
        target_X, target_Z = get_safe_orthogonal(blend_X, target_Y), (get_safe_orthogonal(blend_X, target_Y) ^ target_Y).normal()

        if match_shape:
            target_mat = om2.MMatrix([target_X.x, target_X.y, target_X.z, 0.0, target_Y.x, target_Y.y, target_Y.z, 0.0, target_Z.x, target_Z.y, target_Z.z, 0.0, pt0.x, pt0.y, pt0.z, 1.0])
            orig_pts = [om2.MPoint(cmds.xform(cv, q=True, ws=True, t=True)) for cv in cvs]
            orig_len = sum(orig_pts[i-1].distanceTo(orig_pts[i]) for i in range(1, num_cvs))
            blended_local_pts = [om2.MPoint(0,0,0)]
            
            for cv_idx in range(1, num_cvs):
                t, blend_vec = cv_idx / float(num_cvs - 1), om2.MVector(0,0,0)
                for d, gd in guide_dists:
                    param = gd['fn'].findParamFromLength(gd['fn'].length() * t)
                    blend_vec += om2.MVector(gd['fn'].getPointAtParam(param, om2.MSpace.kWorld) * gd['inv_mat']) * ((1.0 / (math.pow(d, blend) + 1e-5)) / total_w)
                blended_local_pts.append(om2.MPoint(blend_vec))

            scale_factor = (orig_len / sum(blended_local_pts[i-1].distanceTo(blended_local_pts[i]) for i in range(1, num_cvs))) if preserve_len else 1.0
            for i in range(1, num_cvs):
                blended_local_pts[i].x *= scale_factor; blended_local_pts[i].y *= scale_factor; blended_local_pts[i].z *= scale_factor
                world_pt = blended_local_pts[i] * target_mat
                cmds.xform(cvs[i], ws=True, t=(world_pt.x, world_pt.y, world_pt.z))
        else:
            pts = [om2.MPoint(cmds.xform(cv, q=True, ws=True, t=True)) for cv in cvs]
            v_sum = om2.MVector(0,0,0)
            for i in range(1, num_cvs): v_sum += om2.MVector(pts[i]) - om2.MVector(pt0)
                
            current_X = get_safe_orthogonal((v_sum / (num_cvs - 1)).normal(), target_Y)
            align_quat = om2.MQuaternion()
            if target_X.length() > 1e-4 and current_X.length() > 1e-4:
                dot_val = max(min(current_X * target_X, 1.0), -1.0)
                if math.acos(dot_val) > 1e-4: align_quat = om2.MQuaternion(math.acos(dot_val), (current_X ^ target_X).normal())
            for i in range(1, num_cvs): cmds.xform(cvs[i], ws=True, t=(pt0.x+((om2.MVector(pts[i]) - om2.MVector(pt0)).rotateBy(align_quat)).x, pt0.y+((om2.MVector(pts[i]) - om2.MVector(pt0)).rotateBy(align_quat)).y, pt0.z+((om2.MVector(pts[i]) - om2.MVector(pt0)).rotateBy(align_quat)).z))

            pts = [om2.MPoint(cmds.xform(cv, q=True, ws=True, t=True)) for cv in cvs]
            v_sum = om2.MVector(0,0,0)
            for i in range(1, num_cvs): v_sum += om2.MVector(pts[i]) - om2.MVector(pt0)
                
            final_dir = (v_sum / (num_cvs - 1)).normal()
            dot_product = max(min(final_dir * target_Y, 1.0), -1.0)
            if math.asin(dot_product) < math.radians(min_lift):
                axis = final_dir ^ target_Y
                if axis.length() < 1e-5: axis = (om2.MVector(1,0,0) if abs(target_Y * om2.MVector(1,0,0)) < 0.99 else om2.MVector(0,1,0) ^ target_Y).normal()
                else: axis.normalize()
                lift_quat = om2.MQuaternion(math.radians(min_lift) - math.asin(dot_product), axis)
                for i in range(1, num_cvs): cmds.xform(cvs[i], ws=True, t=(pt0.x+((om2.MVector(pts[i]) - om2.MVector(pt0)).rotateBy(lift_quat)).x, pt0.y+((om2.MVector(pts[i]) - om2.MVector(pt0)).rotateBy(lift_quat)).y, pt0.z+((om2.MVector(pts[i]) - om2.MVector(pt0)).rotateBy(lift_quat)).z))
    
    om2.MGlobal.displayInfo(u"Hoàn tất Deform & Align.")

# ==========================================
# GIAO DIỆN CHÍNH (UI)
# ==========================================

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
    # 2. Nhóm Guides & Generation
    # ----------------------------------------
    guides_frame = cmds.frameLayout(label=" 2. Guides & Generation ", collapsable=True, parent=column_main, bgc=color01(33, 41, 84), font="boldLabelFont", marginHeight=6, marginWidth=6)
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
    # 3. Nhóm Groom Modifiers
    # ----------------------------------------
    modifiers_frame = cmds.frameLayout(label=" 3. Groom Modifiers ", collapsable=True, parent=column_main, bgc=color01(33, 41, 84), font="boldLabelFont", marginHeight=6, marginWidth=6)
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