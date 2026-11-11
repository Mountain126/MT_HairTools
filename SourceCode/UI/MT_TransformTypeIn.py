# -*- coding: utf-8 -*-
"""
MT Transform Type-In - UI (ô nhập toạ độ kiểu 3ds Max).
Chỉ chứa phần giao diện Qt, mọi xử lý gọi sang SourceCode/Logic/transform_typein.py.

Khi file này được reload, file Logic cũng được reload
-> sửa code Logic xong chỉ cần mở lại tool là Maya nhận code mới.
"""
import sys
import maya.cmds as cmds
from maya import OpenMayaUI

try:
    # Dành cho Maya 2025 trở lên
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
except ImportError:
    # Dành cho Maya 2017 - 2024
    from PySide2 import QtWidgets, QtCore, QtGui
    from shiboken2 import wrapInstance

if sys.version_info[0] >= 3:
    from importlib import reload as _reload
else:
    _reload = reload     # Python 2: reload là hàm có sẵn

from SourceCode.Logic import transform_typein

try:
    transform_typein.stop_tracking()   # dọn scriptJob/callback của bản cũ trước khi reload
except Exception:
    pass
_reload(transform_typein)

tt = transform_typein  # logic ô nhập transform

TYPEIN_POLL_MS = 33   # timer chỉ kiểm tra cờ dirty, không gọi lệnh Maya liên tục
TYPEIN_EMBED_HEIGHT = 98   # chiều cao thanh xếp dọc (4 hàng) khi nhúng vào panel
# Giữ lại qua các lần reload để thanh cũ bị huỷ không tắt nhầm theo dõi của thanh mới
_typein = globals().get("_typein") or {"serial": 0}

_MULTI_STYLE = ("QLineEdit { border: 1px solid rgb(82, 160, 210);"
                " background-color: rgb(45, 70, 90); }")


# --------------------------------------------------------------------------- #
# Hỗ trợ tương thích PySide2 / PySide6 và Python 2 / 3
# --------------------------------------------------------------------------- #
def _enum(owner, group, name):
    """
    Lấy giá trị enum Qt. PySide6 bản mới chỉ chấp nhận tên đầy đủ
    (Qt.CursorShape.SizeVerCursor), PySide2 thì dùng tên ngắn (Qt.SizeVerCursor).
    """
    scope = getattr(owner, group, None)
    if scope is not None and hasattr(scope, name):
        return getattr(scope, name)
    return getattr(owner, name)


_Qt = QtCore.Qt
LEFT_BUTTON = _enum(_Qt, "MouseButton", "LeftButton")
RIGHT_BUTTON = _enum(_Qt, "MouseButton", "RightButton")
NO_BUTTON = _enum(_Qt, "MouseButton", "NoButton")
CTRL_MOD = _enum(_Qt, "KeyboardModifier", "ControlModifier")
SHIFT_MOD = _enum(_Qt, "KeyboardModifier", "ShiftModifier")
KEY_ESCAPE = _enum(_Qt, "Key", "Key_Escape")
NO_PEN = _enum(_Qt, "PenStyle", "NoPen")
CURSOR_SIZE_VER = _enum(_Qt, "CursorShape", "SizeVerCursor")
EV_KEY_PRESS = _enum(QtCore.QEvent, "Type", "KeyPress")
EV_MOUSE_PRESS = _enum(QtCore.QEvent, "Type", "MouseButtonPress")
EV_MOUSE_MOVE = _enum(QtCore.QEvent, "Type", "MouseMove")
EV_MOUSE_RELEASE = _enum(QtCore.QEvent, "Type", "MouseButtonRelease")
ANTIALIASING = _enum(QtGui.QPainter, "RenderHint", "Antialiasing")
ROLE_BUTTON = _enum(QtGui.QPalette, "ColorRole", "Button")
ROLE_HIGHLIGHT = _enum(QtGui.QPalette, "ColorRole", "Highlight")
ROLE_BUTTON_TEXT = _enum(QtGui.QPalette, "ColorRole", "ButtonText")
ROLE_MID = _enum(QtGui.QPalette, "ColorRole", "Mid")
ALIGN_RIGHT_VCENTER = (_enum(_Qt, "AlignmentFlag", "AlignRight")
                       | _enum(_Qt, "AlignmentFlag", "AlignVCenter"))
WA_TRANSPARENT_MOUSE = _enum(_Qt, "WidgetAttribute", "WA_TransparentForMouseEvents")


def _ptr_int(ptr):
    """Con trỏ Maya -> số nguyên cho wrapInstance (Python 2 cần long)."""
    if sys.version_info[0] < 3:
        return long(ptr)   # noqa: F821
    return int(ptr)


def _modifier_mult():
    mods = QtWidgets.QApplication.keyboardModifiers()
    if mods & CTRL_MOD:
        return 10.0
    if mods & SHIFT_MOD:
        return 0.1
    return 1.0


def _global_pos(ev):
    try:
        return ev.globalPosition().toPoint()   # PySide6
    except AttributeError:
        return ev.globalPos()                  # PySide2


def _local_pos(ev):
    """Vị trí chuột trong widget; PySide6 đã bỏ dần pos() nên ưu tiên position()."""
    try:
        return ev.position().toPoint()         # PySide6
    except AttributeError:
        return ev.pos()                        # PySide2


# --------------------------------------------------------------------------- #
# Widget
# --------------------------------------------------------------------------- #
class SpinArrows(QtWidgets.QWidget):
    """
    Cặp mũi tên lên/xuống kiểu spinner của 3ds Max.
      Click trái: +/- 1 bước (giữ để lặp) | Kéo lên/xuống: thay đổi liên tục
      Ctrl: x10 | Shift: x0.1 | Click phải: reset
    """
    DRAG_START_PX = 3

    def __init__(self, bar, axis, parent=None):
        super(SpinArrows, self).__init__(parent)
        self.bar = bar
        self.axis = axis
        self.setFixedSize(13, 20)
        self.setCursor(CURSOR_SIZE_VER)
        self.setToolTip(u"Click: +/- 1 bước (giữ để lặp)\n"
                        u"Kéo lên/xuống: thay đổi liên tục\n"
                        u"Ctrl: x10 | Shift: x0.1\n"
                        u"Click phải: reset (Scale về 1)")
        self._dir = 0            # +1 lên / -1 xuống / 0 không bấm
        self._dragging = False
        self._press_y = 0
        self._last_y = 0
        self._chunk_open = False
        self._repeat = QtCore.QTimer(self)
        self._repeat.timeout.connect(self._on_repeat)

    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(ANTIALIASING)
        pal = self.palette()
        w, h = self.width(), self.height()
        half = h / 2.0
        base = pal.color(ROLE_BUTTON)
        hi = pal.color(ROLE_HIGHLIGHT)
        fg = pal.color(ROLE_BUTTON_TEXT if self.isEnabled() else ROLE_MID)
        for d, top in ((1, 0.0), (-1, half)):
            rect = QtCore.QRectF(0, top, w, half)
            p.fillRect(rect.adjusted(0, 0, 0, -0.5), hi if self._dir == d else base)
            cx, cy = w / 2.0, top + half / 2.0
            s = 3.0
            if d == 1:
                pts = [QtCore.QPointF(cx - s, cy + s / 2), QtCore.QPointF(cx + s, cy + s / 2),
                       QtCore.QPointF(cx, cy - s / 2)]
            else:
                pts = [QtCore.QPointF(cx - s, cy - s / 2), QtCore.QPointF(cx + s, cy - s / 2),
                       QtCore.QPointF(cx, cy + s / 2)]
            p.setPen(NO_PEN)
            p.setBrush(fg)
            p.drawPolygon(QtGui.QPolygonF(pts))
        p.end()

    def _step(self):
        return tt.STEP[tt.tool_mode()] * _modifier_mult()

    def _nudge(self, delta):
        tt.nudge(self.axis, delta, chunk=False)
        self.bar.refresh(force=True)
        self.bar.notify_changed()

    def _close_chunk(self):
        if self._chunk_open:
            tt.close_chunk()
            self._chunk_open = False

    def mousePressEvent(self, ev):
        if ev.button() == RIGHT_BUTTON:
            tt.reset(self.axis)
            self.bar.refresh(force=True)
            self.bar.notify_changed()
            return
        if ev.button() != LEFT_BUTTON:
            return
        y = _local_pos(ev).y()
        self._dir = 1 if y < self.height() / 2.0 else -1
        self._press_y = self._last_y = y
        self._dragging = False
        if not self._chunk_open:
            tt.open_chunk("MT_TypeIn_Spinner")
            self._chunk_open = True
        self._nudge(self._dir * self._step())
        self._repeat.start(400)   # trễ trước khi lặp
        self.update()

    def _on_repeat(self):
        if self._dir and not self._dragging:
            self._repeat.setInterval(50)
            self._nudge(self._dir * self._step())

    def mouseMoveEvent(self, ev):
        if not (ev.buttons() & LEFT_BUTTON):
            return
        y = _local_pos(ev).y()
        if not self._dragging and abs(y - self._press_y) >= self.DRAG_START_PX:
            self._dragging = True
            self._repeat.stop()
            self._last_y = y
            return
        if self._dragging:
            dy = self._last_y - y     # kéo lên = tăng
            if dy:
                self._last_y = y
                self._nudge(dy * self._step())

    def mouseReleaseEvent(self, ev):
        if ev.button() != LEFT_BUTTON:
            return
        self._repeat.stop()
        self._dir = 0
        self._dragging = False
        self._close_chunk()
        self.update()

    def hideEvent(self, ev):
        self._repeat.stop()
        self._close_chunk()
        super(SpinArrows, self).hideEvent(ev)


class _UnitLineEdit(QtWidgets.QLineEdit):
    """
    Ô nhập căn phải, đơn vị (cm / deg / x) hiện mờ ở mép phải bên trong ô.
    Đơn vị là nhãn riêng đè lên ô, không nằm trong text, nên gõ số và đọc số vẫn như cũ.
    """
    UNIT_PAD = 4

    def __init__(self, parent=None):
        super(_UnitLineEdit, self).__init__(parent)
        self.setAlignment(ALIGN_RIGHT_VCENTER)
        self._unit = QtWidgets.QLabel(self)
        self._unit.setAttribute(WA_TRANSPARENT_MOUSE, True)   # click vẫn vào ô nhập
        self._unit.setAlignment(ALIGN_RIGHT_VCENTER)
        self._unit.setStyleSheet("color: rgb(150, 150, 150); background: transparent;")

    def set_unit(self, text):
        text = text or ""
        if self._unit.text() == text:
            return
        self._unit.setText(text)
        metrics = self._unit.fontMetrics()
        if hasattr(metrics, "horizontalAdvance"):
            width = metrics.horizontalAdvance(text)
        else:
            width = metrics.width(text)
        # Chừa chỗ bên phải cho đơn vị để số không bị đè lên.
        self.setTextMargins(0, 0, (width + self.UNIT_PAD * 2) if text else 0, 0)
        self._place_unit()

    def _place_unit(self):
        width = self._unit.sizeHint().width()
        self._unit.setGeometry(
            self.width() - width - self.UNIT_PAD - 2, 0, width + 2, self.height()
        )

    def resizeEvent(self, ev):
        super(_UnitLineEdit, self).resizeEvent(ev)
        self._place_unit()


class _FieldFilter(QtCore.QObject):
    """
    - Esc: huỷ gõ.
    - Nhấn chuột trái + kéo qua các ô: chọn nhiều ô liền nhau.
    - Ctrl + click: thêm/bớt từng ô vào nhóm.
    """
    def __init__(self, bar):
        super(_FieldFilter, self).__init__(bar)
        self.bar = bar

    def eventFilter(self, obj, ev):
        bar = self.bar
        fields = bar.fields
        if obj not in fields:
            return False
        t = ev.type()
        idx = fields.index(obj)

        if t == EV_KEY_PRESS and ev.key() == KEY_ESCAPE:
            bar.set_multi(set())
            obj.clearFocus()
            bar.refresh(force=True)
            return True

        if t == EV_MOUSE_PRESS and ev.button() == LEFT_BUTTON:
            if ev.modifiers() & CTRL_MOD:
                cur = set(bar.multi)
                prev = bar.anchor
                if not cur and prev is not None and fields[prev].hasFocus():
                    cur.add(prev)            # ô đang gõ dở cũng vào nhóm
                if idx in cur and len(cur) > 1:
                    cur.discard(idx)
                    bar.set_multi(cur)
                    return True              # bỏ ô này, giữ focus ô cũ
                cur.add(idx)
                bar.set_multi(cur)
                bar.anchor = idx
                obj.setFocus()
                obj.selectAll()
                return True
            bar.anchor = idx
            bar.drag = True
            bar.set_multi({idx})
            return False                     # để QLineEdit xử lý con trỏ bình thường

        if t == EV_MOUSE_MOVE and bar.drag:
            a = bar.anchor
            hit = bar.field_at(_global_pos(ev))
            if hit is not None and hit != a:
                lo, hi = min(a, hit), max(a, hit)
                bar.set_multi(range(lo, hi + 1))
                fields[a].selectAll()        # gõ sẽ thay toàn bộ
                return True
            if len(bar.multi) > 1:
                return True                  # đang quét nhiều ô: chặn bôi đen text

        if t == EV_MOUSE_RELEASE and ev.button() == LEFT_BUTTON:
            bar.drag = False
            if len(bar.multi) > 1:
                a = bar.anchor
                fields[a].setFocus()
                fields[a].selectAll()
                bar.mirror_text(a, fields[a].text())
        return False


class TransformTypeInBar(QtWidgets.QWidget):
    """
    compact=False (1 hàng):  [World] Move  X:[_ cm]▲▼ Y:[_ cm]▲▼ Z:[_ cm]▲▼
    compact=True  (xếp dọc, dùng trong panel hẹp):
        [World] Move
        X: [                  12.5 cm]▲▼
        Y: [                     0 cm]▲▼
        Z: [                     0 cm]▲▼
    Số căn phải, đơn vị hiện mờ ở mép phải bên trong ô.

    on_changed: hàm gọi lại (không tham số) sau mỗi lần Type-In sửa transform,
    để panel chứa nó cập nhật thông tin khác (vd kích thước vùng chọn).
    """

    def __init__(self, parent=None, compact=False, on_changed=None):
        super(TransformTypeInBar, self).__init__(parent)
        self.setObjectName("MT_TransformTypeIn_widget")
        self.multi = set()
        self.anchor = None
        self.drag = False
        self.on_changed = on_changed
        self._last_mode = None
        self._last_world = None
        self._last_enable = None

        outer = None
        if compact:
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(4, 3, 4, 3)
            outer.setSpacing(3)
            top = QtWidgets.QHBoxLayout()
            top.setSpacing(3)
            outer.addLayout(top)
            lay = None                        # mỗi trục 1 hàng riêng (tạo trong vòng lặp)
        else:
            lay = QtWidgets.QHBoxLayout(self)
            lay.setContentsMargins(4, 2, 4, 2)
            lay.setSpacing(3)
            top = lay

        self.space_btn = QtWidgets.QPushButton("World")
        self.space_btn.setCheckable(True)
        self.space_btn.setChecked(tt.state["world"])
        self.space_btn.setFixedSize(44, 20)
        self.space_btn.setToolTip(u"World: theo hệ trục thế giới\n"
                                  u"Local: object -> giá trị channel box | component -> object space")
        self._apply_space_style(tt.state["world"])
        self.space_btn.toggled.connect(self._on_space_toggled)
        top.addWidget(self.space_btn)

        self.mode_lbl = QtWidgets.QLabel("Move")
        self.mode_lbl.setFixedWidth(40)
        top.addWidget(self.mode_lbl)

        # Đơn vị hiện ngay trong từng ô nhập (xem _UnitLineEdit), không cần nhãn riêng.
        if compact:
            top.addStretch(1)

        self._filter = _FieldFilter(self)
        self.fields, self.spins = [], []
        for i, ax in enumerate(tt.AXES):
            ax_lbl = QtWidgets.QLabel(ax + ":")
            if compact:
                lay = QtWidgets.QHBoxLayout()
                lay.setSpacing(3)
                outer.addLayout(lay)
                ax_lbl.setFixedWidth(16)
            else:
                lay.addSpacing(4)
            lay.addWidget(ax_lbl)
            qle = _UnitLineEdit()
            if compact:
                qle.setFixedHeight(20)
                qle.setMinimumWidth(40)   # tự giãn theo chiều rộng panel
            else:
                qle.setFixedSize(72, 20)
            qle.setToolTip(u"Enter: áp dụng | Esc: huỷ | 'r10' = cộng tương đối 10\n"
                           u"Kéo chuột qua nhiều ô / Ctrl+click: nhập 1 lần cho nhiều ô")
            qle.installEventFilter(self._filter)
            qle.returnPressed.connect(lambda _i=i: self.apply(_i))
            qle.textEdited.connect(lambda text, _i=i: self.mirror_text(_i, text))
            lay.addWidget(qle)
            sp = SpinArrows(self, i)
            lay.addWidget(sp)
            self.fields.append(qle)
            self.spins.append(sp)

        if not compact:
            lay.addStretch(1)

        # Theo dõi thay đổi trong Maya + timer nhẹ
        tt.start_tracking()
        _typein["serial"] += 1
        serial = _typein["serial"]
        # Không dùng "lambda *_a, s=serial" vì cú pháp đó chỉ có ở Python 3;
        # serial là biến cục bộ không đổi nên closure giữ đúng giá trị.
        self.destroyed.connect(lambda *_a: _on_typein_destroyed(serial))
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(TYPEIN_POLL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.refresh(force=True)

    # --- nhiều ô ---
    def set_multi(self, axes):
        self.multi = set(axes)
        show = len(self.multi) > 1
        for i, q in enumerate(self.fields):
            q.setStyleSheet(_MULTI_STYLE if (show and i in self.multi) else "")

    def mirror_text(self, axis, text):
        if axis in self.multi:
            for i in self.multi:
                if i != axis:
                    self.fields[i].setText(text)

    def field_at(self, gpos):
        for i, q in enumerate(self.fields):
            if q.rect().contains(q.mapFromGlobal(gpos)):
                return i
        return None

    def _check_focus(self):
        """Rời khỏi ô -> bỏ chọn nhiều ô (chỉ dùng Qt)."""
        if self.multi and not self.drag:
            if not any(q.hasFocus() for q in self.fields):
                self.set_multi(set())

    # --- cập nhật ---
    def _tick(self):
        try:
            self._check_focus()
            pressed = QtWidgets.QApplication.mouseButtons() != NO_BUTTON
            if tt.consume_dirty() or pressed:
                self.refresh()
        except Exception as e:   # không để timer chết vì 1 lỗi lặt vặt
            print("MT Type-In: %s" % e)

    def refresh(self, force=False):
        mode, kind, vals = tt.read_values()
        world = tt.state["world"]

        # Đơn vị đọc mỗi lần refresh để bắt cả khi đổi đơn vị scene (set_unit tự bỏ qua nếu không đổi).
        unit = tt.unit_label(mode)
        for qle in self.fields:
            qle.set_unit(unit)

        if force or mode != self._last_mode or world != self._last_world:
            self.mode_lbl.setText(tt.MODE_LABELS[mode])
            self.space_btn.blockSignals(True)
            self.space_btn.setChecked(world)
            self.space_btn.setText("World" if world else "Local")
            self._apply_space_style(world)
            self.space_btn.blockSignals(False)
            self._last_mode, self._last_world = mode, world

        enable = kind is not None
        if force or enable != self._last_enable:
            for w in self.fields + self.spins:
                w.setEnabled(enable)
            self._last_enable = enable

        # ô đang gõ (và các ô cùng nhóm chọn) thì không ghi đè
        self._check_focus()
        focused = [i for i, q in enumerate(self.fields) if q.hasFocus()]
        busy = set()
        if focused:
            busy = set(self.multi) if focused[0] in self.multi else {focused[0]}

        for i, qle in enumerate(self.fields):
            if i in busy and not force:
                continue
            text = tt.fmt(vals[i])
            if qle.text() != text:
                qle.setText(text)
                qle.setCursorPosition(0)

    def _apply_space_style(self, world):
        """
        World = xanh (như nút Select All Meshes), Local = cam (như nút Select All Curves).
        Gán thẳng theo trạng thái, không dùng :checked vì style của Maya vẽ đè nút đang bật thành màu tối.
        """
        color = "rgb(57, 146, 255)" if world else "rgb(238, 137, 38)"
        self.space_btn.setStyleSheet(
            "QPushButton {{ background-color: {0}; color: rgb(0, 0, 0);"
            " border: 1px solid rgb(40, 40, 40); border-radius: 2px; }}".format(color))

    def notify_changed(self):
        if self.on_changed is None:
            return
        try:
            self.on_changed()
        except Exception as e:
            print("MT Type-In: %s" % e)

    # --- thao tác ---
    def apply(self, axis):
        """Enter: áp dụng cho mọi ô đang được chọn cùng lúc."""
        axes = sorted(self.multi) if axis in self.multi else [axis]
        tt.apply_text(axes, self.fields[axis].text())
        self.set_multi(set())
        self.fields[axis].clearFocus()
        self.refresh(force=True)
        self.notify_changed()

    def _on_space_toggled(self, checked):
        tt.set_world(checked)
        self.refresh(force=True)


def _on_typein_destroyed(serial):
    """Thanh bị đóng -> tắt theo dõi (chỉ khi đó là thanh mới nhất)."""
    if serial == _typein["serial"]:
        try:
            tt.stop_tracking()
        except Exception:
            pass


def embed_typein(parent_layout, on_changed=None):
    """
    Nhúng thanh Type-In (xếp dọc) vào một layout maya.cmds.
    Trả về tên layout chứa nó.
    """
    holder = cmds.columnLayout(adjustableColumn=True, parent=parent_layout,
                               height=TYPEIN_EMBED_HEIGHT)
    ptr = OpenMayaUI.MQtUtil.findLayout(holder)
    if not ptr:
        cmds.warning(u"MT Type-In: không tìm thấy layout để nhúng.")
        return holder
    host = wrapInstance(_ptr_int(ptr), QtWidgets.QWidget)
    bar = TransformTypeInBar(compact=True, on_changed=on_changed)
    bar.setFixedHeight(TYPEIN_EMBED_HEIGHT)
    if host.layout() is not None:
        host.layout().addWidget(bar)
    else:
        bar.setParent(host)
        bar.show()
    return holder
