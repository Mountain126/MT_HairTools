import math
import time
import maya.cmds as cmds
import maya.api.OpenMaya as om2


def _curve_fn(curve):
    sel = om2.MSelectionList()
    sel.add(curve)
    dag = sel.getDagPath(0)
    dag.extendToShape()
    return om2.MFnNurbsCurve(dag)


def find_crossings(curve_a, curve_b, tol=0.5, samples=300):
    """Trả về list (distance, point_on_A, point_on_B) cho mọi vị trí 2 curve giao/đi gần nhau (<= tol)."""
    fa, fb = _curve_fn(curve_a), _curve_fn(curve_b)
    s, e = fa.knotDomain

    data = []
    for i in range(samples + 1):
        pa = fa.getPointAtParam(s + (e - s) * i / float(samples), om2.MSpace.kWorld)
        pb, _ = fb.closestPoint(pa, space=om2.MSpace.kWorld)
        data.append((pa.distanceTo(pb), pa, pb))

    # Chỉ giữ cực tiểu cục bộ có khoảng cách <= tol (mỗi chỗ giao = 1 kết quả)
    results = []
    last = len(data) - 1
    for i, (d, pa, pb) in enumerate(data):
        if d > tol:
            continue
        prev_d = data[i - 1][0] if i > 0 else float("inf")
        next_d = data[i + 1][0] if i < last else float("inf")
        if d <= prev_d and d < next_d:
            results.append((d, pa, pb))
    return results


def find_crossings_screen(curve_a, curve_b, tol_px=4.0, samples=300):
    """Giống find_crossings nhưng đo khoảng cách theo pixel trong viewport đang active (giao nhìn thấy từ camera)."""
    import maya.api.OpenMayaUI as omui
    view = omui.M3dView.active3dView()
    fa, fb = _curve_fn(curve_a), _curve_fn(curve_b)
    sa, ea = fa.knotDomain
    sb, eb = fb.knotDomain

    def sample(fn, s, e):
        pts = [fn.getPointAtParam(s + (e - s) * i / float(samples), om2.MSpace.kWorld)
               for i in range(samples + 1)]
        return pts, [tuple(view.worldToView(p))[:2] for p in pts]

    pts_a, scr_a = sample(fa, sa, ea)
    pts_b, scr_b = sample(fb, sb, eb)

    data = []
    for pa, (ax, ay) in zip(pts_a, scr_a):
        best_d, best_j = float("inf"), 0
        for j, (bx, by) in enumerate(scr_b):
            d = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
            if d < best_d:
                best_d, best_j = d, j
        data.append((best_d, pa, pts_b[best_j]))

    results = []
    last = len(data) - 1
    for i, (d, pa, pb) in enumerate(data):
        if d > tol_px:
            continue
        prev_d = data[i - 1][0] if i > 0 else float("inf")
        next_d = data[i + 1][0] if i < last else float("inf")
        if d <= prev_d and d < next_d:
            results.append((d, pa, pb))
    return data, results


def test_selected_curves(tol=0.5, samples=300, make_locators=True, screen_space=False, tol_px=4.0):
    """Chọn >= 2 curve rồi chạy hàm này. Tạo locator tại các điểm giao của từng cặp curve.
    screen_space=True: đo theo pixel trong viewport hiện tại (tol_px), bỏ qua độ lệch chiều sâu."""
    curves = [c for c in cmds.ls(selection=True, long=True) or []
              if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    if len(curves) < 2:
        cmds.warning("Chọn ít nhất 2 curve.")
        return []

    if make_locators and cmds.objExists("crossing_test_grp"):
        cmds.delete("crossing_test_grp")
    grp = cmds.group(empty=True, name="crossing_test_grp") if make_locators else None

    all_hits = []
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            if screen_space:
                data, hits = find_crossings_screen(curves[i], curves[j], tol_px, samples)
                print("{0} x {1}: khoảng cách nhỏ nhất = {2:.2f} px".format(
                    curves[i].split("|")[-1], curves[j].split("|")[-1], min(x[0] for x in data)))
            else:
                hits = find_crossings(curves[i], curves[j], tol, samples)
                fa, fb = _curve_fn(curves[i]), _curve_fn(curves[j])
                s, e = fa.knotDomain
                min_d = min(fb.closestPoint(fa.getPointAtParam(s + (e - s) * k / 100.0, om2.MSpace.kWorld),
                                            space=om2.MSpace.kWorld)[0].distanceTo(
                    fa.getPointAtParam(s + (e - s) * k / 100.0, om2.MSpace.kWorld)) for k in range(101))
                print("{0} x {1}: khoảng cách 3D nhỏ nhất = {2:.4f}".format(
                    curves[i].split("|")[-1], curves[j].split("|")[-1], min_d))
            for d, pa, pb in hits:
                mid = om2.MPoint((pa.x + pb.x) / 2.0, (pa.y + pb.y) / 2.0, (pa.z + pb.z) / 2.0)
                all_hits.append((curves[i], curves[j], d, mid))
                print("{0} x {1}: dist={2:.4f} pos=({3:.3f}, {4:.3f}, {5:.3f})".format(
                    curves[i].split("|")[-1], curves[j].split("|")[-1], d, mid.x, mid.y, mid.z))
                if make_locators:
                    loc = cmds.spaceLocator(name="crossing_loc_#")[0]
                    cmds.xform(loc, worldSpace=True, translation=(mid.x, mid.y, mid.z))
                    cmds.parent(loc, grp)

    print("Tổng số điểm giao tìm thấy: {0}".format(len(all_hits)))
    return all_hits


def _sample_curve(curve, samples):
    fn = _curve_fn(curve)
    s, e = fn.knotDomain
    out = []
    for i in range(samples + 1):
        p = fn.getPointAtParam(s + (e - s) * i / float(samples), om2.MSpace.kWorld)
        out.append((p.x, p.y, p.z))
    return out


def find_crossings_on_surface(curves, mesh=None, tol=0.5, samples=200, min_gap=3):
    """Không phụ thuộc camera. Chiếu mọi curve lên 1 bề mặt chung rồi so khoảng cách.
    - mesh: chiếu lên mesh (closest point). None: chiếu hướng tâm lên mặt cầu bao quanh các curve.
    - min_gap: bỏ qua kết quả quá gần nhau (theo số mẫu) trên cùng 1 curve để tránh trùng.
    Trả về list (curveA, curveB, distance, MPoint)."""
    pts = {c: _sample_curve(c, samples) for c in curves}

    mesh_fn = None
    if mesh:
        sel = om2.MSelectionList()
        sel.add(mesh)
        dag = sel.getDagPath(0)
        dag.extendToShape()
        mesh_fn = om2.MFnMesh(dag)
    else:
        allp = [p for c in curves for p in pts[c]]
        lo_c = [min(p[k] for p in allp) for k in range(3)]
        hi_c = [max(p[k] for p in allp) for k in range(3)]
        center = [(lo_c[k] + hi_c[k]) / 2.0 for k in range(3)]
        radius = sum(math.sqrt(sum((p[k] - center[k]) ** 2 for k in range(3))) for p in allp) / len(allp)

    proj = {}
    for c in curves:
        arr = []
        for p in pts[c]:
            if mesh_fn:
                q, _ = mesh_fn.getClosestPoint(om2.MPoint(p[0], p[1], p[2]), space=om2.MSpace.kWorld)
                arr.append((q.x, q.y, q.z))
            else:
                v = [p[k] - center[k] for k in range(3)]
                n = math.sqrt(sum(x * x for x in v))
                if n > 1e-9:
                    v = [x / n * radius for x in v]
                arr.append(tuple(center[k] + v[k] for k in range(3)))
        proj[c] = arr

    def bbox(arr):
        return [min(p[k] for p in arr) for k in range(3)], [max(p[k] for p in arr) for k in range(3)]

    boxes = {c: bbox(proj[c]) for c in curves}
    tol2 = tol * tol
    hits = []
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            a, b = proj[curves[i]], proj[curves[j]]
            (amin, amax), (bmin, bmax) = boxes[curves[i]], boxes[curves[j]]
            # Bỏ qua cặp có bounding box (nới tol) không chồng nhau
            if any(amin[k] - tol > bmax[k] or bmin[k] - tol > amax[k] for k in range(3)):
                continue
            d2, near = [], []
            for pa in a:
                best, bj = float("inf"), 0
                for n, pb in enumerate(b):
                    dd = (pa[0] - pb[0]) ** 2 + (pa[1] - pb[1]) ** 2 + (pa[2] - pb[2]) ** 2
                    if dd < best:
                        best, bj = dd, n
                d2.append(best)
                near.append(bj)
            for k, dk in enumerate(d2):
                if dk > tol2:
                    continue
                lo, hi = max(0, k - min_gap), min(len(d2), k + min_gap + 1)
                window = d2[lo:hi]
                if dk > min(window) or k != lo + window.index(min(window)):
                    continue
                pb = b[near[k]]
                m = [(a[k][x] + pb[x]) / 2.0 for x in range(3)]
                hits.append((curves[i], curves[j], math.sqrt(dk), om2.MPoint(m[0], m[1], m[2])))
    return hits


def test_on_surface(tol=0.5, samples=200, make_locators=True):
    """Chọn nhiều curve (có thể kèm 1 mesh đầu để chiếu lên). Không phụ thuộc camera."""
    sel = cmds.ls(selection=True, long=True) or []
    curves = [c for c in sel if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    meshes = [c for c in sel if cmds.listRelatives(c, shapes=True, type="mesh")]
    if len(curves) < 2:
        cmds.warning("Chọn ít nhất 2 curve (có thể kèm 1 mesh).")
        return []

    hits = find_crossings_on_surface(curves, meshes[0] if meshes else None, tol, samples)

    if make_locators:
        if cmds.objExists("crossing_test_grp"):
            cmds.delete("crossing_test_grp")
        grp = cmds.group(empty=True, name="crossing_test_grp")
        for ca, cb, d, m in hits:
            loc = cmds.spaceLocator(name="crossing_loc_#")[0]
            cmds.xform(loc, worldSpace=True, translation=(m.x, m.y, m.z))
            cmds.parent(loc, grp)
    print("Chiếu lên: {0} | Tìm thấy {1} điểm giao".format(meshes[0] if meshes else "mặt cầu bao quanh", len(hits)))
    return hits


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


def find_crossings_cylinder2(curves, radius=0.5, samples=300, min_angle=0.0, verbose=True, max_overlap=6.0):
    """Phiên bản cải tiến:
    - Số mẫu tự tăng theo chiều dài curve để không bỏ sót vùng giao hẹp.
    - Vị trí điểm giao được tinh chỉnh bằng golden-section nên điểm đặt locator là điểm gần nhau nhất thật sự.
    - min_angle mặc định thấp hơn (5 độ) và verbose in rõ lý do cặp curve bị loại.
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
                t = s + step * k
                pa = fa.getPointAtParam(t, om2.MSpace.kWorld)
                pb, _ = fb.closestPoint(pa, space=om2.MSpace.kWorld)
                data.append(pa.distanceTo(pb))

            # Mỗi vùng liên tục có khoảng cách <= limit (2 hình trụ chồng nhau) -> 1 điểm giao
            k = 0
            found_cluster = False
            loose = limit * 1.5  # vùng gom rộng hơn ngưỡng, rồi mới so khoảng cách đã tinh chỉnh với limit
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
                # Đoạn 2 curve nằm gần nhau dài bất thường => chạy song song chứ không phải giao nhau
                overlap_len = (k - start) * step * fa.length() / max(e - s, 1e-9)
                if max_overlap and overlap_len > max_overlap * limit:
                    if verbose:
                        print("BỎ QUA {0} x {1}: chạy song song {2:.2f} (> {3}*2*radius), d={4:.3f}".format(na, nb, overlap_len, max_overlap, d))
                    continue
                if ang < min_angle:
                    if verbose:
                        print("BỎ QUA {0} x {1}: góc {2:.1f} < {3}, d={4:.3f}".format(na, nb, ang, min_angle, d))
                    continue
                mid = om2.MPoint((pa.x + pb.x) / 2.0, (pa.y + pb.y) / 2.0, (pa.z + pb.z) / 2.0)
                hits.append((ca, cb, d, mid, ang))
            if verbose and not found_cluster and refined_min < float("inf"):
                print("KHÔNG GIAO {0} x {1}: khoảng cách nhỏ nhất (đã tinh chỉnh) {2:.4f} > 2*radius ({3:.3f}) -> cần radius >= {4:.3f}".format(
                    na, nb, refined_min, limit, refined_min / 2.0))
    return hits


def find_crossings_cylinder(curves, radius=0.5, samples=300, min_angle=15.0):
    """Mỗi curve có 1 hình trụ giả tưởng bán kính `radius` chạy dọc theo nó.
    Hai hình trụ giao nhau <=> khoảng cách giữa 2 curve <= 2*radius. Mỗi vùng giao liên tục
    được gom thành 1 điểm giao (tại vị trí 2 curve gần nhau nhất).
    - min_angle: bỏ qua vùng mà 2 curve gần như song song (góc < min_angle độ), 0 để tắt.
    Trả về list (curveA, curveB, distance, MPoint, angle)."""
    fns = {c: _curve_fn(c) for c in curves}
    pts = {c: _sample_curve(c, samples) for c in curves}
    boxes = {}
    for c in curves:
        boxes[c] = ([min(p[k] for p in pts[c]) for k in range(3)],
                    [max(p[k] for p in pts[c]) for k in range(3)])
    limit = radius * 2.0

    hits = []
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            ca, cb = curves[i], curves[j]
            (amin, amax), (bmin, bmax) = boxes[ca], boxes[cb]
            if any(amin[k] - limit > bmax[k] or bmin[k] - limit > amax[k] for k in range(3)):
                continue
            fa, fb = fns[ca], fns[cb]
            s, e = fa.knotDomain

            samples_data = []
            for n in range(samples + 1):
                param = s + (e - s) * n / float(samples)
                pa = fa.getPointAtParam(param, om2.MSpace.kWorld)
                pb, pbp = fb.closestPoint(pa, space=om2.MSpace.kWorld)
                samples_data.append((pa.distanceTo(pb), param, pa, pb, pbp))

            # Gom các mẫu liên tiếp nằm trong vùng giao của 2 hình trụ
            cluster = []
            for item in samples_data + [None]:
                if item is not None and item[0] <= limit:
                    cluster.append(item)
                    continue
                if cluster:
                    d, param, pa, pb, pbp = min(cluster, key=lambda x: x[0])
                    ta = fa.tangent(param, om2.MSpace.kWorld)
                    tb = fb.tangent(pbp, om2.MSpace.kWorld)
                    ang = math.degrees(math.acos(min(1.0, abs(ta.normal() * tb.normal()))))
                    if ang >= min_angle:
                        mid = om2.MPoint((pa.x + pb.x) / 2.0, (pa.y + pb.y) / 2.0, (pa.z + pb.z) / 2.0)
                        hits.append((ca, cb, d, mid, ang))
                    cluster = []
    return hits


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _length(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _unit(a):
    length = _length(a)
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / length, a[1] / length, a[2] / length)


def _point_seg_dist(p, a, b):
    ab = _sub(b, a)
    ab2 = _dot(ab, ab)
    if ab2 < 1e-18:
        return _length(_sub(p, a))
    t = max(0.0, min(1.0, _dot(_sub(p, a), ab) / ab2))
    return _length(_sub(p, _add(a, _mul(ab, t))))


def _aabb_sep2(a0, a1, b0, b1):
    sep = 0.0
    for k in range(3):
        a_lo = a0[k] if a0[k] < a1[k] else a1[k]
        a_hi = a1[k] if a1[k] > a0[k] else a0[k]
        b_lo = b0[k] if b0[k] < b1[k] else b1[k]
        b_hi = b1[k] if b1[k] > b0[k] else b0[k]
        if a_hi < b_lo:
            gap = b_lo - a_hi
            sep += gap * gap
        elif b_hi < a_lo:
            gap = a_lo - b_hi
            sep += gap * gap
    return sep


def _seg_seg(a0, a1, b0, b1):
    """Khoảng cách ngắn nhất giữa 2 đoạn thẳng. Trả về (dist, s, t), s/t trong [0, 1]."""
    small = 1e-12
    u = _sub(a1, a0)
    v = _sub(b1, b0)
    w = _sub(a0, b0)
    a = _dot(u, u)
    b = _dot(u, v)
    c = _dot(v, v)
    if a < small and c < small:
        return _length(w), 0.0, 0.0
    d = _dot(u, w)
    e = _dot(v, w)
    denom = a * c - b * b
    s_n = 0.0
    s_d = denom
    t_n = e
    t_d = denom
    if denom <= small * max(a * c, 1.0):
        s_n = 0.0
        s_d = 1.0
        t_n = e
        t_d = c
    else:
        s_n = b * e - c * d
        t_n = a * e - b * d
        if s_n < 0.0:
            s_n = 0.0
            t_n = e
            t_d = c
        elif s_n > s_d:
            s_n = s_d
            t_n = e + b
            t_d = c
    if t_n < 0.0:
        t_n = 0.0
        if -d < 0.0:
            s_n = 0.0
        elif -d > a:
            s_n = s_d
        else:
            s_n = -d
            s_d = a
    elif t_d > small and t_n > t_d:
        t_n = t_d
        if (-d + b) < 0.0:
            s_n = 0.0
        elif (-d + b) > a:
            s_n = s_d
        else:
            s_n = -d + b
            s_d = a
    sc = 0.0 if abs(s_d) < small else max(0.0, min(1.0, s_n / s_d))
    tc = 0.0 if abs(t_d) < small else max(0.0, min(1.0, t_n / t_d))
    delta = _sub(_add(a0, _mul(u, sc)), _add(b0, _mul(v, tc)))
    return _length(delta), sc, tc


def _newton_direction(r, du, du2, dv, dv2):
    """Bước Newton cho cực tiểu ||Ca(u)-Cb(v)||. None nếu bài toán suy biến (song song)."""
    f1 = _dot(r, du)
    f2 = _dot(r, dv)
    a = _dot(du, du) + _dot(r, du2)
    b = -_dot(du, dv)
    c = -b
    d = -_dot(dv, dv) + _dot(r, dv2)
    det = a * d - b * c
    scale = abs(_dot(du, du) * _dot(dv, dv)) + 1.0
    if abs(det) <= 1e-18 * scale:
        return None
    su = (-f1 * d + f2 * b) / det
    sv = (f1 * c - f2 * a) / det
    return su, sv


def _adaptive_polyline(fn, chord_tol, max_len):
    """Lấy mẫu theo sai số dây cung, không theo param đều. Trả về [(param, x, y, z), ...]."""
    start, end = fn.knotDomain
    cache = {}

    def ev(t):
        t = float(t)
        hit = cache.get(t)
        if hit is None:
            p = fn.getPointAtParam(t, om2.MSpace.kWorld)
            hit = (p.x, p.y, p.z)
            cache[t] = hit
        return hit

    pts = [(start, ) + ev(start)]

    def rec(t0, p0, t1, p1, depth):
        if len(pts) > 4000 or depth >= 16 or (t1 - t0) <= 1e-10:
            pts.append((t1, ) + tuple(p1))
            return
        chord = _length(_sub(p1, p0))
        err = 0.0
        if chord <= max_len:
            span = t1 - t0
            for frac in (0.25, 0.5, 0.75):
                err = max(err, _point_seg_dist(ev(t0 + span * frac), p0, p1))
                if err > chord_tol:
                    break
        if chord > max_len or err > chord_tol:
            tm = (t0 + t1) * 0.5
            pm = ev(tm)
            rec(t0, p0, tm, pm, depth + 1)
            rec(tm, pm, t1, p1, depth + 1)
        else:
            pts.append((t1, ) + tuple(p1))

    rec(start, ev(start), end, ev(end), 0)
    return pts


def _poly_at(pts, u):
    if u <= pts[0][0]:
        return pts[0][1:]
    if u >= pts[-1][0]:
        return pts[-1][1:]
    lo, hi = 0, len(pts) - 2
    while lo < hi:
        mid = (lo + hi) // 2
        if pts[mid + 1][0] < u:
            lo = mid + 1
        else:
            hi = mid
    t0, t1 = pts[lo][0], pts[lo + 1][0]
    frac = 0.0 if t1 <= t0 else (u - t0) / (t1 - t0)
    return _lerp(pts[lo][1:], pts[lo + 1][1:], max(0.0, min(1.0, frac)))


def _poly_arclen(pts, u0, u1):
    if u1 < u0:
        u0, u1 = u1, u0
    if u1 - u0 < 1e-12:
        return 0.0
    seq = [_poly_at(pts, u0)]
    for p in pts:
        if u0 < p[0] < u1:
            seq.append(p[1:])
    seq.append(_poly_at(pts, u1))
    total = 0.0
    for a, b in zip(seq, seq[1:]):
        total += _length(_sub(b, a))
    return total


def _merge_intervals(intervals):
    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged = []
    for a, b in ordered:
        if not merged or a > merged[-1][1]:
            merged.append([a, b])
        else:
            merged[-1][1] = max(merged[-1][1], b)
    return merged


def _param_bounds(pts, seg, pad=1):
    i0 = max(0, seg - pad)
    i1 = min(len(pts) - 1, seg + 1 + pad)
    lo, hi = pts[i0][0], pts[i1][0]
    if hi < lo:
        lo, hi = hi, lo
    if hi <= lo:
        hi = lo + 1e-8
    return lo, hi


def _project_param_interval(t0, t1, a0, a1, b0, b1):
    direction = _sub(a1, a0)
    denom = _dot(direction, direction)
    if denom < 1e-18:
        return None

    def project(p):
        return _dot(_sub(p, a0), direction) / denom

    s0, s1 = sorted((project(b0), project(b1)))
    s0 = max(0.0, s0)
    s1 = min(1.0, s1)
    if s1 <= s0 + 1e-8:
        return None
    return (t0 + s0 * (t1 - t0), t0 + s1 * (t1 - t0))


def _crossings_from_polylines(polys, limit, margin, min_angle, max_overlap, refine=None, verbose=False):
    """Tìm cực tiểu cục bộ của khoảng cách giữa các polyline. refine() đẩy điểm lên curve gốc."""
    segments = []
    for ci, poly in enumerate(polys):
        pts = poly["pts"]
        for si in range(len(pts) - 1):
            segments.append((ci, si, pts[si][1:], pts[si + 1][1:], pts[si][0], pts[si + 1][0]))
    if not segments:
        return [], {"segments": 0, "tests": 0, "regions": 0}

    cell = max(margin, 1e-6)
    inv = 1.0 / cell
    buckets = {}

    def cells_of(p0, p1, pad):
        lo = [min(p0[k], p1[k]) - pad for k in range(3)]
        hi = [max(p0[k], p1[k]) + pad for k in range(3)]
        ia = [int(math.floor(lo[k] * inv)) for k in range(3)]
        ib = [int(math.floor(hi[k] * inv)) for k in range(3)]
        out = []
        for ix in range(ia[0], ib[0] + 1):
            for iy in range(ia[1], ib[1] + 1):
                for iz in range(ia[2], ib[2] + 1):
                    out.append((ix, iy, iz))
        return out

    for idx, seg in enumerate(segments):
        for key in cells_of(seg[2], seg[3], 0.0):
            buckets.setdefault(key, []).append(idx)

    margin2 = margin * margin
    cands = []
    tests = 0
    seen = set()
    for idx, (ci, si, a0, a1, t0, t1) in enumerate(segments):
        for key in cells_of(a0, a1, margin):
            for jdx in buckets.get(key, ()):
                if jdx <= idx:
                    continue
                cj = segments[jdx][0]
                if cj <= ci:
                    continue
                pair = (idx, jdx)
                if pair in seen:
                    continue
                seen.add(pair)
                b0, b1 = segments[jdx][2], segments[jdx][3]
                if _aabb_sep2(a0, a1, b0, b1) > margin2:
                    continue
                tests += 1
                dist, s, t = _seg_seg(a0, a1, b0, b1)
                if dist <= margin + 1e-7:
                    cands.append((ci, si, cj, segments[jdx][1], dist, s, t))

    by_seg = {}
    for i, cand in enumerate(cands):
        by_seg[(cand[0], cand[1], cand[2], cand[3])] = i
    parent = list(range(len(cands)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i, (ci, si, cj, sj, dist, s, t) in enumerate(cands):
        for da in (0, 1):
            for db in (-1, 0, 1):
                if da == 0 and db <= 0:
                    continue
                other = by_seg.get((ci, si + da, cj, sj + db))
                if other is not None:
                    union(i, other)

    groups = {}
    for i in range(len(cands)):
        groups.setdefault(find(i), []).append(cands[i])

    hits = []
    pair_state = {}
    for group in groups.values():
        seed = min(group, key=lambda c: (c[4], c[1], c[3]))
        ci, si, cj, sj, dist, s, t = seed
        pa_pts = polys[ci]["pts"]
        pb_pts = polys[cj]["pts"]
        a0, a1 = pa_pts[si][1:], pa_pts[si + 1][1:]
        b0, b1 = pb_pts[sj][1:], pb_pts[sj + 1][1:]
        u = pa_pts[si][0] + s * (pa_pts[si + 1][0] - pa_pts[si][0])
        v = pb_pts[sj][0] + t * (pb_pts[sj + 1][0] - pb_pts[sj][0])
        pa, pb = _lerp(a0, a1, s), _lerp(b0, b1, t)
        ta, tb = _unit(_sub(a1, a0)), _unit(_sub(b1, b0))
        if refine is not None:
            ulo, uhi = _param_bounds(pa_pts, si)
            vlo, vhi = _param_bounds(pb_pts, sj)
            u, v, pa, pb, ta, tb, dist = refine(ci, cj, u, v, ulo, uhi, vlo, vhi)

        us = []
        parallel = []
        for gci, gsi, gcj, gsj, gd, gs, gt in group:
            gpts = polys[gci]["pts"]
            us.append(gpts[gsi][0] + gs * (gpts[gsi + 1][0] - gpts[gsi][0]))
            if gd > limit:
                continue
            gp0, gp1 = gpts[gsi][1:], gpts[gsi + 1][1:]
            hq = polys[gcj]["pts"]
            hq0, hq1 = hq[gsj][1:], hq[gsj + 1][1:]
            if _sin_dirs(gp0, gp1, hq0, hq1) < 0.12:
                interval = _project_param_interval(gpts[gsi][0], gpts[gsi + 1][0], gp0, gp1, hq0, hq1)
                if interval:
                    parallel.append(interval)
        overlap = _poly_arclen(pa_pts, min(us), max(us)) if us else 0.0
        if parallel:
            overlap = max(overlap, max(_poly_arclen(pa_pts, a, b) for a, b in _merge_intervals(parallel)))

        name_a = polys[ci]["name"].split("|")[-1]
        name_b = polys[cj]["name"].split("|")[-1]
        state = pair_state.setdefault((ci, cj), {"hit": False, "filtered": False, "best": dist, "names": (name_a, name_b)})
        state["best"] = min(state["best"], dist)
        if dist > limit + 1e-7:
            continue
        if max_overlap and overlap > max_overlap * limit:
            state["filtered"] = True
            if verbose:
                print("BỎ QUA {0} x {1}: chạy song song {2:.2f} (> {3}*2*radius), d={4:.3f}".format(
                    name_a, name_b, overlap, max_overlap, dist))
            continue
        dot = abs(_dot(ta, tb))
        ang = 90.0 if _length(ta) < 1e-8 or _length(tb) < 1e-8 else math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        if ang < min_angle:
            state["filtered"] = True
            if verbose:
                print("BỎ QUA {0} x {1}: góc {2:.1f} < {3}, d={4:.3f}".format(name_a, name_b, ang, min_angle, dist))
            continue
        state["hit"] = True
        hits.append((ci, cj, dist, pa, pb, ang))

    deduped = []
    dedupe = max(1e-4, limit * 0.05)
    for hit in hits:
        ci, cj, dist, pa, pb, ang = hit
        mid = _mul(_add(pa, pb), 0.5)
        if any(k[0] == ci and k[1] == cj and _length(_sub(mid, _mul(_add(k[3], k[4]), 0.5))) < dedupe for k in deduped):
            continue
        deduped.append(hit)
    if verbose:
        for state in pair_state.values():
            if state["hit"] or state["filtered"]:
                continue
            na, nb = state["names"]
            best = state["best"]
            print("KHÔNG GIAO {0} x {1}: khoảng cách nhỏ nhất {2:.4f} > 2*radius ({3:.3f}) -> cần radius >= {4:.3f}".format(
                na, nb, best, limit, best / 2.0))
    return deduped, {"segments": len(segments), "tests": tests, "regions": len(groups)}


def _sin_dirs(a0, a1, b0, b1):
    u, v = _sub(a1, a0), _sub(b1, b0)
    lu, lv = _length(u), _length(v)
    if lu < 1e-12 or lv < 1e-12:
        return 0.0
    cosine = max(-1.0, min(1.0, _dot(u, v) / (lu * lv)))
    return math.sqrt(max(0.0, 1.0 - cosine * cosine))


def _eval_curve_state(fa, fb, u, v):
    ga = fa.getDerivativesAtParam(u, space=om2.MSpace.kWorld, dUU=True)
    gb = fb.getDerivativesAtParam(v, space=om2.MSpace.kWorld, dUU=True)
    pa, dua, duu = ga[0], ga[1], ga[2]
    pb, dvb, dvv = gb[0], gb[1], gb[2]
    r = (pa.x - pb.x, pa.y - pb.y, pa.z - pb.z)
    return {
        "r": r,
        "du": (dua.x, dua.y, dua.z),
        "du2": (duu.x, duu.y, duu.z),
        "dv": (dvb.x, dvb.y, dvb.z),
        "dv2": (dvv.x, dvv.y, dvv.z),
        "dist": _length(r),
        "pa": (pa.x, pa.y, pa.z),
        "pb": (pb.x, pb.y, pb.z),
    }


def _newton_refine(fa, fb, u, v, ulo, uhi, vlo, vhi):
    sa, ea = fa.knotDomain
    sb, eb = fb.knotDomain
    ulo, uhi = max(min(ulo, uhi), sa), min(max(ulo, uhi), ea)
    vlo, vhi = max(min(vlo, vhi), sb), min(max(vlo, vhi), eb)
    if uhi <= ulo:
        uhi = min(ea, ulo + 1e-6)
    if vhi <= vlo:
        vhi = min(eb, vlo + 1e-6)
    u = min(max(u, ulo), uhi)
    v = min(max(v, vlo), vhi)
    state = _eval_curve_state(fa, fb, u, v)
    best = (state["dist"], u, v, state)
    u_span = max(uhi - ulo, 1e-8)
    v_span = max(vhi - vlo, 1e-8)
    for _ in range(8):
        step = _newton_direction(state["r"], state["du"], state["du2"], state["dv"], state["dv2"])
        if step is None:
            break
        su = max(-0.5 * u_span, min(0.5 * u_span, step[0]))
        sv = max(-0.5 * v_span, min(0.5 * v_span, step[1]))
        if su * su + sv * sv < 1e-24:
            break
        improved = False
        alpha = 1.0
        for _line in range(6):
            un = min(max(u + su * alpha, ulo), uhi)
            vn = min(max(v + sv * alpha, vlo), vhi)
            if abs(un - u) < 1e-14 and abs(vn - v) < 1e-14:
                break
            trial = _eval_curve_state(fa, fb, un, vn)
            if trial["dist"] < best[0] - 1e-10:
                u, v, state = un, vn, trial
                best = (trial["dist"], u, v, trial)
                improved = True
                break
            alpha *= 0.5
        if not improved:
            break
    dist, u, v, state = best
    return u, v, state["pa"], state["pb"], _unit(state["du"]), _unit(state["dv"]), dist


def find_crossings_local(curves, radius=0.5, min_angle=0.0, verbose=True, max_overlap=6.0):
    """Điểm hai curve gần nhau nhất trong từng vùng, chính xác hơn và ít lần gọi closestPoint.

    Curve được xấp xỉ bằng đoạn thẳng theo sai số dây cung, rồi chỉ so những đoạn nằm
    trong cùng ô lưới (cạnh ô ~ 2*radius). Mỗi vùng gần nhau được đẩy về cực tiểu thật
    trên NURBS bằng Newton, nên không bỏ sót nhánh mà closestPoint toàn cục nuốt mất.
    Trả về list (curveA, curveB, distance, MPoint, angle), cùng dạng với find_crossings_cylinder2.
    """
    started = time.perf_counter()
    limit = radius * 2.0
    chord_tol = max(limit * 0.02, 1e-4)
    max_len = max(limit * 4.0, chord_tol * 8.0)
    margin = limit + 2.0 * chord_tol
    fns = [_curve_fn(c) for c in curves]
    polys = []
    for curve, fn in zip(curves, fns):
        polys.append({"name": curve, "pts": _adaptive_polyline(fn, chord_tol, max_len)})

    def refine(ci, cj, u, v, ulo, uhi, vlo, vhi):
        return _newton_refine(fns[ci], fns[cj], u, v, ulo, uhi, vlo, vhi)

    raw, stats = _crossings_from_polylines(polys, limit, margin, min_angle, max_overlap, refine, verbose)
    hits = []
    for ci, cj, dist, pa, pb, ang in raw:
        mid = om2.MPoint((pa[0] + pb[0]) * 0.5, (pa[1] + pb[1]) * 0.5, (pa[2] + pb[2]) * 0.5)
        hits.append((curves[ci], curves[cj], dist, mid, ang))
    if verbose:
        print("Local: {0} curve, {1} đoạn, {2} phép thử, {3} vùng, {4:.3f}s".format(
            len(curves), stats["segments"], stats["tests"], stats["regions"], time.perf_counter() - started))
    return hits


def test_cylinder(radius=0.5, samples=300, min_angle=0.0, make_locators=True, verbose=True, max_overlap=6.0, method="local"):
    """Chọn nhiều curve rồi chạy. Không phụ thuộc camera. Locator đặt tại các điểm giao.
    method='local': đoạn thẳng + lưới + Newton (mặc định). method='legacy': quét closestPoint."""
    curves = [c for c in cmds.ls(selection=True, long=True) or []
              if cmds.listRelatives(c, shapes=True, type="nurbsCurve")]
    if len(curves) < 2:
        cmds.warning("Chọn ít nhất 2 curve.")
        return []

    if method == "legacy":
        hits = find_crossings_cylinder2(curves, radius, samples, min_angle, verbose, max_overlap)
    else:
        hits = find_crossings_local(curves, radius, min_angle, verbose, max_overlap)

    if make_locators:
        if cmds.objExists("crossing_test_grp"):
            cmds.delete("crossing_test_grp")
        grp = cmds.group(empty=True, name="crossing_test_grp")
        for ca, cb, d, m, ang in hits:
            loc = cmds.spaceLocator(name="crossing_loc_#")[0]
            cmds.xform(loc, worldSpace=True, translation=(m.x, m.y, m.z))
            cmds.parent(loc, grp)
    print("Hình trụ bán kính {0}: tìm thấy {1} điểm giao trên {2} curve".format(radius, len(hits), len(curves)))
    return hits


def _poly(points, name):
    pts = []
    acc = 0.0
    prev = None
    for p in points:
        if prev is not None:
            acc += _length(_sub(p, prev))
        pts.append((acc, p[0], p[1], p[2]))
        prev = p
    return {"name": name, "pts": pts}


def _test_crossing_kernel():
    """Kiểm tra hình học thuần (không cần Maya): khoảng cách đoạn, lưới, và cực tiểu cục bộ."""
    def near(a, b, tol):
        return abs(a - b) <= tol

    dist, s, t = _seg_seg((0, 0, 0), (1, 0, 0), (0.5, -1, 1), (0.5, 1, 1))
    assert near(dist, 1.0, 1e-6) and near(s, 0.5, 1e-6) and near(t, 0.5, 1e-6), (dist, s, t)
    dist, s, t = _seg_seg((0, 0, 0), (1, 0, 0), (2, 1, 0), (3, 1, 0))
    assert near(dist, math.sqrt(2.0), 1e-6) and near(s, 1.0, 1e-6) and near(t, 0.0, 1e-6), (dist, s, t)
    dist, s, t = _seg_seg((0, 0, 0), (2, 0, 0), (1, 0, 0), (3, 0, 0))
    assert dist <= 1e-6, dist
    dist, s, t = _seg_seg((0, 0, 0), (10, 0, 0), (4, -5, 0.25), (6, 5, 0.25))
    assert near(dist, 0.25, 1e-6) and near(s, 0.5, 1e-6), (dist, s, t)

    # Hai đường thẳng chéo: Newton một bước phải về đúng chân khoảng cách.
    step = _newton_direction((0.4, 0.3, -1.0), (1, 0, 0), (0, 0, 0), (0, 1, 0), (0, 0, 0))
    assert step is not None and near(0.4 + step[0], 0.0, 1e-6) and near(-0.3 + step[1], 0.0, 1e-6), step

    def residual(u, v):
        pa = (u, 0.15 * u * u, 0.0)
        dpa = (1.0, 0.3 * u, 0.0)
        ddpa = (0.0, 0.3, 0.0)
        pb = (0.2 * v, 1.0 + 0.05 * v * v, v)
        dpb = (0.2, 0.1 * v, 1.0)
        ddpb = (0.0, 0.1, 0.0)
        return _sub(pa, pb), dpa, ddpa, dpb, ddpb

    u, v = 0.3, -0.4
    r, du, du2, dv, dv2 = residual(u, v)
    step = _newton_direction(r, du, du2, dv, dv2)
    eps = 1e-5

    def fg(uu, vv):
        rr, duu, duu2, dvv, dvv2 = residual(uu, vv)
        return _dot(rr, duu), _dot(rr, dvv)

    f1, f2 = fg(u, v)
    j00 = (fg(u + eps, v)[0] - fg(u - eps, v)[0]) / (2 * eps)
    j01 = (fg(u, v + eps)[0] - fg(u, v - eps)[0]) / (2 * eps)
    j10 = (fg(u + eps, v)[1] - fg(u - eps, v)[1]) / (2 * eps)
    j11 = (fg(u, v + eps)[1] - fg(u, v - eps)[1]) / (2 * eps)
    got0 = j00 * step[0] + j01 * step[1]
    got1 = j10 * step[0] + j11 * step[1]
    assert near(got0, -f1, 1e-3) and near(got1, -f2, 1e-3), (got0, -f1, got1, -f2)

    def run(polys, limit, **kwargs):
        hits, stats = _crossings_from_polylines(polys, limit, kwargs.pop("margin", limit), kwargs.pop("min_angle", 0.0),
                                                kwargs.pop("max_overlap", 0.0), None, False)
        return hits, stats

    a = _poly([(0, 0, 0), (10, 0, 0)], "A")
    b = _poly([(4, -5, 0.25), (6, 5, 0.25)], "B")
    hits, _stats = run([a, b], 0.5)
    assert len(hits) == 1, hits
    mid = _mul(_add(hits[0][3], hits[0][4]), 0.5)
    assert near(mid[0], 5.0, 1e-5) and near(mid[1], 0.0, 1e-5) and near(mid[2], 0.125, 1e-5), mid
    assert near(hits[0][2], 0.25, 1e-6), hits[0][2]

    # Hai chỗ gần nhau trên cùng một cặp. closestPoint toàn cục chỉ thấy chỗ gần hơn.
    axis = _poly([(i, 0.0, 0.0) for i in range(11)], "axis")
    other_pts = [(i, 0.1, 0.0) for i in range(5)]
    other_pts += [(4.0, 0.1, 20.0), (2.0, 5.0, 20.0), (2.0, 5.0, 0.45), (2.0, -5.0, 0.45)]
    other = _poly(other_pts, "other")
    hits, _stats = run([axis, other], 0.5, max_overlap=0.0)
    dists = sorted(h[2] for h in hits)
    assert len(hits) == 2, [(h[2], h[3], h[4]) for h in hits]
    assert dists[0] <= 0.15 and abs(dists[1] - 0.45) < 1e-3, dists
    # Đoạn chạy sát dài bị loại, chỗ lệch 0.45 ở cùng vùng x vẫn còn.
    hits, _stats = run([axis, other], 0.5, max_overlap=6.0)
    assert len(hits) == 1 and abs(hits[0][2] - 0.45) < 1e-3, [(h[2], h[3]) for h in hits]

    straight = _poly([(i, 0.0, 0.0) for i in range(21)], "s")
    parallel = _poly([(i, 0.1, 0.0) for i in range(21)], "p")
    hits, _stats = run([straight, parallel], 0.5, max_overlap=6.0)
    assert hits == [], hits
    hits, _stats = run([straight, parallel], 0.5, max_overlap=0.0, min_angle=20.0)
    assert hits == [], hits

    # Lưới không được bỏ sót cực tiểu nào so với vét cạn.
    import random
    rng = random.Random(3)
    cloud = []
    for n in range(25):
        x, y, z = (rng.uniform(-4, 4) for _ in range(3))
        pts = [(x, y, z)]
        for _k in range(6):
            x += rng.uniform(-0.8, 0.8)
            y += rng.uniform(-0.8, 0.8)
            z += rng.uniform(-0.8, 0.8)
            pts.append((x, y, z))
        cloud.append(_poly(pts, "c{0}".format(n)))
    limit = 0.35
    hits, _stats = run(cloud, limit)
    segs = []
    for ci, poly in enumerate(cloud):
        pts = poly["pts"]
        for si in range(len(pts) - 1):
            segs.append((ci, si, pts[si][1:], pts[si + 1][1:]))
    brute = []
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if segs[j][0] <= segs[i][0]:
                continue
            dist, s, t = _seg_seg(segs[i][2], segs[i][3], segs[j][2], segs[j][3])
            if dist <= limit + 1e-7:
                pa = _lerp(segs[i][2], segs[i][3], s)
                pb = _lerp(segs[j][2], segs[j][3], t)
                brute.append((segs[i][0], segs[i][1], segs[j][0], segs[j][1], dist, pa, pb))
    link = {(c[0], c[1], c[2], c[3]): k for k, c in enumerate(brute)}
    parent = list(range(len(brute)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for k, c in enumerate(brute):
        for da in (0, 1):
            for db in (-1, 0, 1):
                if da == 0 and db <= 0:
                    continue
                other = link.get((c[0], c[1] + da, c[2], c[3] + db))
                if other is not None:
                    ri, rj = find(k), find(other)
                    if ri != rj:
                        parent[rj] = ri
    comps = {}
    for k in range(len(brute)):
        comps.setdefault(find(k), []).append(brute[k])
    mins = []
    for group in comps.values():
        best = min(group, key=lambda c: c[4])
        mins.append(_mul(_add(best[5], best[6]), 0.5))
    hit_mids = [_mul(_add(h[3], h[4]), 0.5) for h in hits]
    dedupe = max(1e-4, limit * 0.05)
    for mid in hit_mids:
        assert any(_length(_sub(mid, m)) < 1e-4 for m in mins), mid
    for mid in mins:
        assert any(_length(_sub(mid, m)) <= dedupe + 1e-6 for m in hit_mids), mid
    return True


# Cách dùng trong Maya Script Editor (Python):
#   import sys; sys.path.append(r"c:/Users/Mountain/OneDrive/Documents/maya/2023/scripts/MT_HairTools")
#   import test_curve_crossings as t; import importlib; importlib.reload(t)
#   t.test_cylinder(radius=0.5)                 # cách mới: đoạn thẳng + lưới + Newton
#   t.test_cylinder(radius=0.5, method="legacy")
