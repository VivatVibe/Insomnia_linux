from __future__ import annotations

import math
import time
from typing import Callable, Optional
import cairo
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gtk


class AnimatedEye(Gtk.Image):
    """60 FPS Vector Animated Eye using standalone Cairo surfaces and GdkPixbuf."""

    DESIGN_SIZE = 24.0

    def __init__(self, size: int = 100) -> None:
        super().__init__()
        self.width = size
        self.height = int(size * 0.8)

        self._surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)

        # Animation state
        self._progress: float = 0.0  # 0.0 = closed / asleep, 1.0 = wide open
        self._target_progress: float = 0.0
        self._velocity: float = 0.0

        # Motion.swift Spring parameters
        self._open_response: float = 0.95
        self._open_damping: float = 0.90
        self._close_duration: float = 0.80

        self._animating: bool = False
        self._last_tick_time: float = time.monotonic()
        self._timer_id: Optional[int] = None

        self._render_frame()

    def set_awake(self, awake: bool) -> None:
        new_target = 1.0 if awake else 0.0
        if self._target_progress != new_target:
            self._target_progress = new_target
            self._start_animation()

    def blink(self) -> None:
        """Trigger an instant blink gesture."""
        if self._target_progress > 0.5:
            self._progress = 0.1
            self._velocity = 0.0
            self._start_animation()

    def _start_animation(self) -> None:
        if not self._animating:
            self._animating = True
            self._last_tick_time = time.monotonic()
            if self._timer_id is None:
                self._timer_id = GLib.timeout_add(16, self._on_animation_tick)

    def _on_animation_tick(self) -> bool:
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._last_tick_time))
        self._last_tick_time = now

        opening = self._target_progress > 0.5

        if opening:
            # Spring physics for eyelid opening
            omega = 2.0 * math.pi / self._open_response
            k = omega * omega
            c = 2.0 * self._open_damping * omega
            acceleration = -k * (self._progress - self._target_progress) - c * self._velocity
            self._velocity += acceleration * dt
            self._progress += self._velocity * dt
        else:
            # Smooth ease-out closing
            speed = 1.0 / self._close_duration
            diff = self._target_progress - self._progress
            step = diff * speed * dt * 3.5
            self._progress += step
            self._velocity = 0.0

        # Check settling threshold to pause loop and save CPU
        settled = abs(self._progress - self._target_progress) < 0.002 and abs(self._velocity) < 0.01
        if settled:
            self._progress = self._target_progress
            self._velocity = 0.0
            self._animating = False
            self._timer_id = None
            self._render_frame()
            return False

        self._render_frame()
        return True

    def _render_frame(self) -> None:
        cr = cairo.Context(self._surface)
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

        # Scale 24-unit design grid centered into surface rect
        scale = min(self.width, self.height) / self.DESIGN_SIZE
        side = self.DESIGN_SIZE * scale
        offset_x = (self.width - side) / 2.0
        offset_y = (self.height - side) / 2.0

        cr.translate(offset_x, offset_y)
        cr.scale(scale, scale)

        p = max(0.0, min(1.0, self._progress))

        # Geometry coordinates from EyeLensGeometry
        corner_left = (1.5, 12.0)
        corner_right = (22.5, 12.0)
        upper_c1 = (7.0, 4.5)
        upper_c2 = (17.0, 4.5)
        lower_c1 = (17.0, 19.5)
        lower_c2 = (7.0, 19.5)

        line_width = 1.4

        # 1. Lashes
        if p > 0.05:
            cr.save()
            cr.set_source_rgba(0.9, 0.9, 0.9, p)
            cr.set_line_width(line_width)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            lash_specs = [
                ((5.5, 7.5), (4.2, 5.0)),
                ((8.5, 5.2), (7.8, 2.5)),
                ((12.0, 4.5), (12.0, 1.8)),
                ((15.5, 5.2), (16.2, 2.5)),
                ((18.5, 7.5), (19.8, 5.0)),
            ]
            for (sx, sy), (ex, ey) in lash_specs:
                cr.move_to(sx, sy)
                cr.line_to(ex, ey)
            cr.stroke()
            cr.restore()

        if p < 0.95:
            cr.save()
            cr.set_source_rgba(0.55, 0.55, 0.55, 1.0 - p)
            cr.set_line_width(line_width)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            lower_lashes = [
                ((5.5, 16.5), (4.2, 19.0)),
                ((8.5, 18.8), (7.8, 21.5)),
                ((12.0, 19.5), (12.0, 22.2)),
                ((15.5, 18.8), (16.2, 21.5)),
                ((18.5, 16.5), (19.8, 19.0)),
            ]
            for (sx, sy), (ex, ey) in lower_lashes:
                cr.move_to(sx, sy)
                cr.line_to(ex, ey)
            cr.stroke()
            cr.restore()

        # 2. Lens Interior & Pupil
        cr.save()
        cr.move_to(*corner_left)
        cr.curve_to(*upper_c1, *upper_c2, *corner_right)
        cr.curve_to(*lower_c1, *lower_c2, *corner_left)
        cr.close_path()
        cr.clip()

        # Interior fill
        cr.set_source_rgba(0.12, 0.12, 0.14, 1.0)
        cr.paint()

        if p > 0.02:
            pupil_x, pupil_y = 12.0, 12.0
            pupil_r = 4.0 * min(1.0, p * 1.2)

            # Iris glow
            cr.set_source_rgba(0.35, 0.40, 0.95, p * 0.7)
            cr.arc(pupil_x, pupil_y, pupil_r + 0.8, 0, 2 * math.pi)
            cr.fill()

            # Main pupil disc
            cr.set_source_rgba(0.95, 0.95, 0.98, p)
            cr.arc(pupil_x, pupil_y, pupil_r, 0, 2 * math.pi)
            cr.fill()

            # Specular highlight bite
            cr.set_source_rgba(0.12, 0.12, 0.14, p)
            cr.arc(13.8, 10.2, 1.3, 0, 2 * math.pi)
            cr.fill()

        # Eyelid shading
        cur_c1_y = upper_c1[1] * p + lower_c1[1] * (1.0 - p)
        cur_c2_y = upper_c2[1] * p + lower_c2[1] * (1.0 - p)

        cr.move_to(*corner_left)
        cr.curve_to(upper_c1[0], cur_c1_y, upper_c2[0], cur_c2_y, *corner_right)
        cr.curve_to(*upper_c2, *upper_c1, *corner_left)
        cr.close_path()
        cr.set_source_rgba(0.18, 0.18, 0.20, 1.0)
        cr.fill()
        cr.restore()

        # 3. Outer Lens Outline
        cr.save()
        cr.move_to(*corner_left)
        cr.curve_to(*upper_c1, *upper_c2, *corner_right)
        cr.curve_to(*lower_c1, *lower_c2, *corner_left)
        cr.close_path()

        if p > 0.5:
            cr.set_source_rgba(0.95, 0.95, 0.95, 0.95)
        else:
            cr.set_source_rgba(0.60, 0.60, 0.60, 0.70)

        cr.set_line_width(line_width)
        cr.stroke()
        cr.restore()

        # Update Gtk.Image pixbuf
        data = self._surface.get_data()
        stride = self._surface.get_stride()
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            data,
            GdkPixbuf.Colorspace.RGB,
            True,
            8,
            self.width,
            self.height,
            stride,
        )
        self.set_from_pixbuf(pixbuf)


class HoldToEndButton(Gtk.Button):
    """Hold-to-End button with 0.6s animated circular progress ring."""

    def __init__(self, on_complete: Callable[[], None], hold_duration: float = 0.6) -> None:
        super().__init__()
        self.on_complete = on_complete
        self.hold_duration = hold_duration

        self._progress: float = 0.0
        self._holding: bool = False
        self._timer_id: Optional[int] = None
        self._last_tick: float = time.monotonic()

        self.get_style_context().add_class("destructive-action")
        self.set_size_request(-1, 46)

        # Internal Box holding ring image and text
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_halign(Gtk.Align.CENTER)

        self.image_ring = Gtk.Image()
        self.lbl_text = Gtk.Label(label="Hold to End Session")
        self.lbl_text.set_markup("<span weight='bold'>Hold to End Session</span>")

        box.pack_start(self.image_ring, False, False, 0)
        box.pack_start(self.lbl_text, False, False, 0)
        self.add(box)

        self._render_ring()

        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("leave-notify-event", self._on_leave)

    def _render_ring(self) -> None:
        size = 22
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
        cr = cairo.Context(surface)
        cr.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

        cx, cy, r = size / 2.0, size / 2.0, (size / 2.0) - 2.5

        # Background circular track
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.20)
        cr.set_line_width(2.2)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()

        # Active progress ring
        if self._progress > 0.0:
            cr.set_source_rgba(1.0, 0.35, 0.35, 1.0)
            cr.set_line_width(2.4)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            start_angle = -math.pi / 2
            end_angle = start_angle + self._progress * 2 * math.pi
            cr.arc(cx, cy, r, start_angle, end_angle)
            cr.stroke()

        # Center X glyph
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        cr.set_line_width(1.6)
        x_sz = 3.2
        cr.move_to(cx - x_sz, cy - x_sz)
        cr.line_to(cx + x_sz, cy + x_sz)
        cr.move_to(cx + x_sz, cy - x_sz)
        cr.line_to(cx - x_sz, cy + x_sz)
        cr.stroke()

        data = surface.get_data()
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            data,
            GdkPixbuf.Colorspace.RGB,
            True,
            8,
            size,
            size,
            surface.get_stride(),
        )
        self.image_ring.set_from_pixbuf(pixbuf)

    def _on_press(self, widget: Gtk.Widget, event) -> bool:
        if event.button == 1:
            self._holding = True
            self._last_tick = time.monotonic()
            self.lbl_text.set_markup("<span weight='bold'>Holding to End...</span>")
            if self._timer_id is None:
                self._timer_id = GLib.timeout_add(16, self._on_tick)
            return True
        return False

    def _on_release(self, widget: Gtk.Widget, event) -> bool:
        if event.button == 1 and self._holding:
            self._cancel_hold()
            return True
        return False

    def _on_leave(self, widget: Gtk.Widget, event) -> bool:
        if self._holding:
            self._cancel_hold()
        return False

    def _cancel_hold(self) -> None:
        self._holding = False
        self._progress = 0.0
        self.lbl_text.set_markup("<span weight='bold'>Hold to End Session</span>")
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self._render_ring()

    def _on_tick(self) -> bool:
        if not self._holding:
            return False

        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        self._progress += dt / self.hold_duration

        if self._progress >= 1.0:
            self._progress = 1.0
            self._holding = False
            self._timer_id = None
            self._render_ring()
            self.lbl_text.set_markup("<span weight='bold'>Ended!</span>")
            self.on_complete()
            return False

        self._render_ring()
        return True
