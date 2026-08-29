from __future__ import annotations

import math
import os
import random
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser

try:
    import customtkinter as ctk
except ImportError as exc:
    raise SystemExit("customtkinter is required. Run BUILD_APP.bat or: pip install customtkinter") from exc

from PIL import Image, ImageOps

from frames_engine import (
    AppleFramesEngine,
    AssetManager,
    HEIF_OK,
    SUPPORTED_INPUTS,
    build_manual_grid,
    list_images,
    manual_grid_estimate,
    parse_frame_filename,
    save_image,
    safe_resource_path,
)

APP_TITLE = "Apple Frames Studio"
APP_VERSION = "1.5"
APP_USER_MODEL_ID = "AppleFramesStudio.Windows.1.5"

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("dark-blue")


class ScreenshotRow:
    def __init__(self, app, parent, info: dict, index: int):
        self.app = app
        self.info = info
        self.path = Path(info["path"])
        self.added_index = index
        self.selected_var = ctk.BooleanVar(value=False)

        self.frame = ctk.CTkFrame(parent, corner_radius=14)
        self.frame.grid_columnconfigure(2, weight=1)

        self.select_box = ctk.CTkCheckBox(
            self.frame, text="", width=24, variable=self.selected_var,
            command=self.app.on_row_selection_changed
        )
        self.select_box.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=12, sticky="w")

        thumb = self.app.make_thumb(self.path, (72, 72))
        self.thumb_ref = thumb
        ctk.CTkLabel(self.frame, text="", image=thumb).grid(row=0, column=1, rowspan=2, padx=(4, 12), pady=12, sticky="n")

        status = f"{info['width']}×{info['height']}"
        if info.get("supported"):
            status += f"  •  {info.get('device')}"
        else:
            status += "  •  Unsupported resolution"
        ctk.CTkLabel(self.frame, text=self.path.name, font=ctk.CTkFont(size=14, weight="bold"), anchor="w").grid(
            row=0, column=2, padx=(0, 8), pady=(10, 2), sticky="ew"
        )
        ctk.CTkLabel(self.frame, text=status, text_color=("#616161", "#b0b0b0"), anchor="w").grid(
            row=1, column=2, padx=(0, 8), pady=(0, 10), sticky="ew"
        )

        self.device_var = ctk.StringVar()
        self.color_var = ctk.StringVar(value="Default")

        values = self._device_values()
        default = self._default_device_value(values)
        self.device_var.set(default)
        self.device_menu = ctk.CTkOptionMenu(
            self.frame, values=values, variable=self.device_var,
            width=235, command=self.on_device_changed, dynamic_resizing=False
        )
        self.device_menu.grid(row=0, column=3, padx=6, pady=(10, 2), sticky="e")

        color_values = self._color_values_for_current()
        self.color_menu = ctk.CTkOptionMenu(
            self.frame, values=color_values, variable=self.color_var,
            width=190, dynamic_resizing=False
        )
        self.color_menu.grid(row=1, column=3, padx=6, pady=(2, 10), sticky="e")

        ctk.CTkButton(self.frame, text="Remove", width=72, fg_color="transparent", border_width=1,
                      command=self.remove).grid(row=0, column=4, rowspan=2, padx=(6, 12), pady=12)

    def _device_values(self):
        if self.info.get("supported"):
            values = self.info.get("variants") or [self.info.get("device")]
            return [x for x in values if x]
        return self.app.engine.device_names if self.app.engine else ["Unsupported"]

    def _default_device_value(self, values):
        desired = self.info.get("device")
        return desired if desired in values else values[0]

    def _color_values_for_current(self):
        if not self.app.engine:
            return ["Default"]
        device = self.device_var.get()
        colors = self.app.engine.colors_for(device)
        return ["Default", "Random"] + colors if colors else ["Default"]

    def on_device_changed(self, _value=None):
        vals = self._color_values_for_current()
        self.color_menu.configure(values=vals)
        if self.color_var.get() not in vals:
            self.color_var.set("Default")
        self.app.refresh_bulk_controls()

    def set_device(self, device: str):
        values = self._device_values()
        if device not in values:
            return False
        self.device_var.set(device)
        self.on_device_changed(device)
        return True

    def set_color(self, color: str):
        vals = self._color_values_for_current()
        if color in vals:
            self.color_var.set(color)
            return True
        return False

    def remove(self):
        self.app.auto_rows.remove(self)
        self.frame.destroy()
        self.app.refresh_auto_row_positions()
        self.app.refresh_auto_summary()
        self.app.refresh_bulk_controls()

    def get_selection(self):
        return self.path, self.device_var.get(), self.color_var.get()


class AppleFramesStudio(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1420x930")
        self.minsize(1180, 760)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._icon_path = self._resolve_icon_path()
        self._icon_png_path = self._resolve_icon_png_path()
        self._icon_photo = None
        self._apply_windows_identity()
        self._apply_window_icon(self)
        # CustomTkinter can update its default icon shortly after startup, so
        # re-apply ours once the native window has been fully created.
        self.after(300, lambda: self._apply_window_icon(self))

        self.assets = AssetManager()
        self.engine: AppleFramesEngine | None = None
        self.auto_rows: list[ScreenshotRow] = []
        self.auto_cancel = False
        self.manual_cancel = False
        self._manual_thread = None
        self._auto_thread = None
        self._load_engine()
        self._build_shell()
        self.show_page("Auto Frame")

    # ---------- shared ----------
    def _resolve_icon_path(self):
        bundled = safe_resource_path("apple_frames_studio.ico")
        if bundled:
            return bundled
        local = Path(__file__).resolve().with_name("apple_frames_studio.ico")
        return local if local.exists() else None

    def _resolve_icon_png_path(self):
        bundled = safe_resource_path("apple_frames_studio_icon.png")
        if bundled:
            return bundled
        local = Path(__file__).resolve().with_name("apple_frames_studio_icon.png")
        return local if local.exists() else None

    @staticmethod
    def _apply_windows_identity():
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    def _apply_window_icon(self, window):
        # Use both iconbitmap (.ico) and iconphoto (.png). The former is best
        # for Windows title bars; the latter prevents Tk/CustomTkinter from
        # falling back to a Python/Tk icon on recreated native windows.
        if self._icon_path:
            try:
                window.iconbitmap(default=str(self._icon_path))
            except Exception:
                try:
                    window.iconbitmap(str(self._icon_path))
                except Exception:
                    pass
        if self._icon_png_path:
            try:
                if self._icon_photo is None:
                    self._icon_photo = tk.PhotoImage(file=str(self._icon_png_path))
                window.iconphoto(True, self._icon_photo)
            except Exception:
                pass

    def ui(self, fn):
        self.after(0, fn)

    def make_thumb(self, path: Path, size=(72, 72)):
        try:
            with Image.open(path) as im0:
                im = ImageOps.exif_transpose(im0).convert("RGBA")
                im.thumbnail(size, Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", size, (0, 0, 0, 0))
                canvas.alpha_composite(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
            return ctk.CTkImage(light_image=canvas, dark_image=canvas, size=size)
        except Exception:
            placeholder = Image.new("RGBA", size, (120, 120, 120, 255))
            return ctk.CTkImage(light_image=placeholder, dark_image=placeholder, size=size)

    def _load_engine(self):
        path = self.assets.resolve()
        if path:
            try:
                self.engine = AppleFramesEngine(path)
            except Exception:
                self.engine = None
        else:
            self.engine = None

    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=245, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)

        ctk.CTkLabel(self.sidebar, text="Apple Frames\nStudio", font=ctk.CTkFont(size=28, weight="bold"),
                     justify="left").grid(row=0, column=0, padx=24, pady=(30, 4), sticky="w")
        ctk.CTkLabel(self.sidebar, text=f"Windows composer  •  v{APP_VERSION}",
                     text_color=("#6e6e6e", "#a9a9a9")).grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")

        self.nav_buttons = {}
        for r, name in enumerate(["Auto Frame", "Manual Grid", "Frame Library"], start=2):
            btn = ctk.CTkButton(self.sidebar, text=name, anchor="w", height=44, corner_radius=10,
                                command=lambda n=name: self.show_page(n))
            btn.grid(row=r, column=0, padx=16, pady=6, sticky="ew")
            self.nav_buttons[name] = btn

        self.appearance = ctk.CTkOptionMenu(self.sidebar, values=["System", "Light", "Dark"], command=ctk.set_appearance_mode)
        self.appearance.set("System")
        self.appearance.grid(row=9, column=0, padx=16, pady=(10, 8), sticky="ew")

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.pages = {
            "Auto Frame": self._build_auto_page(),
            "Manual Grid": self._build_manual_page(),
            "Frame Library": self._build_library_page(),
        }

    def show_page(self, name):
        for page in self.pages.values():
            page.grid_remove()
        self.pages[name].grid(row=0, column=0, sticky="nsew")
        for n, b in self.nav_buttons.items():
            b.configure(fg_color=("#3b8ed0", "#1f6aa5") if n == name else "transparent")
        if name == "Frame Library":
            self.refresh_library_status()

    # ---------- auto frame ----------
    def _build_auto_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, padx=28, pady=(26, 10), sticky="ew")
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="Auto Frame", font=ctk.CTkFont(size=30, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            head,
            text="Frame one screenshot or hundreds at once. Device, orientation, variants and masks are resolved automatically.",
            text_color=("#666", "#aaa")
        ).grid(row=1, column=0, pady=(4, 0), sticky="w")
        self.auto_asset_badge = ctk.CTkLabel(head, text="", corner_radius=10, padx=12, pady=6)
        self.auto_asset_badge.grid(row=0, column=1, rowspan=2, sticky="e")
        self._update_asset_badge()

        toolbar = ctk.CTkFrame(page, corner_radius=14)
        toolbar.grid(row=1, column=0, padx=28, pady=(10, 5), sticky="ew")
        ctk.CTkButton(toolbar, text="Add screenshots", command=self.auto_add_files).pack(side="left", padx=(14, 6), pady=12)
        ctk.CTkButton(toolbar, text="Add folder", fg_color="transparent", border_width=1, command=self.auto_add_folder).pack(side="left", padx=6, pady=12)
        ctk.CTkButton(toolbar, text="Clear", fg_color="transparent", border_width=1, command=self.auto_clear).pack(side="left", padx=6, pady=12)
        self.auto_summary = ctk.CTkLabel(toolbar, text="0 screenshots", text_color=("#666", "#aaa"))
        self.auto_summary.pack(side="right", padx=16)

        # Bulk edit strip: designed for hundreds of screenshots.
        bulk = ctk.CTkFrame(page, corner_radius=14)
        bulk.grid(row=2, column=0, padx=28, pady=(5, 10), sticky="ew")
        bulk.grid_columnconfigure(6, weight=1)
        ctk.CTkButton(bulk, text="Select all", width=88, fg_color="transparent", border_width=1,
                      command=self.select_all_rows).grid(row=0, column=0, padx=(12, 4), pady=10)
        ctk.CTkButton(bulk, text="Select none", width=92, fg_color="transparent", border_width=1,
                      command=self.select_no_rows).grid(row=0, column=1, padx=4, pady=10)
        self.bulk_selected_label = ctk.CTkLabel(bulk, text="0 selected", text_color=("#666", "#aaa"))
        self.bulk_selected_label.grid(row=0, column=2, padx=(8, 14), pady=10)

        self.auto_bulk_scope = ctk.StringVar(value="All screenshots")
        self.auto_bulk_model = ctk.StringVar(value="Keep current")
        self.auto_bulk_color = ctk.StringVar(value="Keep current")
        self.bulk_scope_menu = ctk.CTkOptionMenu(
            bulk, values=["All screenshots", "Selected screenshots"], variable=self.auto_bulk_scope,
            width=165, command=lambda _v: self.refresh_bulk_controls()
        )
        self.bulk_scope_menu.grid(row=0, column=3, padx=4, pady=10)
        self.bulk_model_menu = ctk.CTkOptionMenu(
            bulk, values=["Keep current"], variable=self.auto_bulk_model, width=235,
            command=lambda _v: self.refresh_bulk_color_options(), dynamic_resizing=False
        )
        self.bulk_model_menu.grid(row=0, column=4, padx=4, pady=10)
        self.bulk_color_menu = ctk.CTkOptionMenu(
            bulk, values=["Keep current", "Default", "Random"], variable=self.auto_bulk_color,
            width=160, dynamic_resizing=False
        )
        self.bulk_color_menu.grid(row=0, column=5, padx=4, pady=10)
        ctk.CTkButton(bulk, text="Apply to target", width=125, command=self.apply_bulk_settings).grid(
            row=0, column=7, padx=(8, 12), pady=10
        )

        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=3, column=0, padx=28, pady=(4, 12), sticky="nsew")
        body.grid_columnconfigure(0, weight=4)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.auto_list = ctk.CTkScrollableFrame(body, label_text="Screenshots", corner_radius=14)
        self.auto_list.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.auto_list.grid_columnconfigure(0, weight=1)

        opts = ctk.CTkScrollableFrame(body, label_text="Composition & Export", corner_radius=14, width=380)
        opts.grid(row=0, column=1, padx=(10, 0), sticky="nsew")
        opts.grid_columnconfigure(0, weight=1)

        self.auto_output_mode = ctk.StringVar(value="Merge all")
        self.auto_order = ctk.StringVar(value="As added")
        self.auto_arrangement = ctk.StringVar(value="Grid")
        self.auto_columns = ctk.StringVar(value="")
        self.auto_batch_size = ctk.StringVar(value="3")
        self.auto_spacing = ctk.StringVar(value="60")
        self.auto_proportional = ctk.BooleanVar(value=True)
        self.auto_background = ctk.StringVar(value="transparent")
        self.auto_format = ctk.StringVar(value="PNG")
        self.auto_quality = ctk.StringVar(value="92")
        self.auto_png_compress = ctk.StringVar(value="6")
        self.auto_output_dir = ctk.StringVar(value=str(Path.home() / "Desktop"))

        row = 0
        self._field_label(opts, "Output mode", row); row += 1
        ctk.CTkOptionMenu(opts, values=["Merge all", "Individual files", "Batches"], variable=self.auto_output_mode,
                          command=self.auto_mode_changed).grid(row=row, column=0, padx=14, sticky="ew"); row += 1

        self._field_label(opts, "Order", row); row += 1
        ctk.CTkOptionMenu(
            opts, values=["As added", "Chronological (oldest first)", "Reverse chronological (newest first)"],
            variable=self.auto_order, command=self.auto_order_changed
        ).grid(row=row, column=0, padx=14, sticky="ew"); row += 1

        self._field_label(opts, "Arrangement", row); row += 1
        ctk.CTkOptionMenu(opts, values=["Grid", "Horizontal", "Vertical"], variable=self.auto_arrangement,
                          command=self.auto_arrangement_changed).grid(row=row, column=0, padx=14, sticky="ew"); row += 1

        self._field_label(opts, "Grid columns (blank = Auto)", row); row += 1
        self.auto_columns_entry = ctk.CTkEntry(opts, textvariable=self.auto_columns, placeholder_text="Auto")
        self.auto_columns_entry.grid(row=row, column=0, padx=14, sticky="ew"); row += 1

        self._field_label(opts, "Batch size", row); row += 1
        self.auto_batch_entry = ctk.CTkEntry(opts, textvariable=self.auto_batch_size)
        self.auto_batch_entry.grid(row=row, column=0, padx=14, sticky="ew"); row += 1

        self._field_label(opts, "Spacing between devices (px)", row); row += 1
        ctk.CTkEntry(opts, textvariable=self.auto_spacing).grid(row=row, column=0, padx=14, sticky="ew"); row += 1
        ctk.CTkSwitch(opts, text="Proportional physical scaling", variable=self.auto_proportional).grid(
            row=row, column=0, padx=14, pady=(14, 6), sticky="w"); row += 1

        self._field_label(opts, "Background", row); row += 1
        bgline = ctk.CTkFrame(opts, fg_color="transparent")
        bgline.grid(row=row, column=0, padx=14, sticky="ew"); row += 1
        bgline.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(bgline, textvariable=self.auto_background).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(bgline, text="Pick", width=58, command=self.pick_auto_bg).grid(row=0, column=1, padx=(6, 0))

        self._field_label(opts, "Format", row); row += 1
        ctk.CTkOptionMenu(opts, values=["PNG", "JPEG", "WEBP", "TIFF", "BMP", "PDF"], variable=self.auto_format).grid(
            row=row, column=0, padx=14, sticky="ew"); row += 1
        self._field_label(opts, "JPEG / WebP quality", row); row += 1
        ctk.CTkEntry(opts, textvariable=self.auto_quality).grid(row=row, column=0, padx=14, sticky="ew"); row += 1
        self._field_label(opts, "PNG compression 0–9", row); row += 1
        ctk.CTkEntry(opts, textvariable=self.auto_png_compress).grid(row=row, column=0, padx=14, sticky="ew"); row += 1
        self._field_label(opts, "Output folder", row); row += 1
        outline = ctk.CTkFrame(opts, fg_color="transparent")
        outline.grid(row=row, column=0, padx=14, sticky="ew"); row += 1
        outline.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(outline, textvariable=self.auto_output_dir).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(outline, text="Browse", width=70, command=self.pick_auto_output).grid(row=0, column=1, padx=(6, 0))

        ctk.CTkButton(opts, text="Preview composition", height=42, fg_color="transparent", border_width=1,
                      command=self.auto_preview).grid(row=row, column=0, padx=14, pady=(18, 6), sticky="ew"); row += 1
        ctk.CTkButton(opts, text="Frame & Export", height=48, command=self.auto_export).grid(
            row=row, column=0, padx=14, pady=6, sticky="ew"); row += 1
        ctk.CTkButton(opts, text="Cancel", height=36, fg_color="transparent", border_width=1,
                      command=self.cancel_auto).grid(row=row, column=0, padx=14, pady=(6, 12), sticky="ew")

        self.auto_progress = ctk.CTkProgressBar(page)
        self.auto_progress.grid(row=4, column=0, padx=28, pady=(0, 4), sticky="ew")
        self.auto_progress.set(0)
        self.auto_status = ctk.CTkLabel(page, text="Ready.", anchor="w", text_color=("#666", "#aaa"))
        self.auto_status.grid(row=5, column=0, padx=30, pady=(0, 18), sticky="ew")
        self.auto_mode_changed(self.auto_output_mode.get())
        self.auto_arrangement_changed(self.auto_arrangement.get())
        self.refresh_bulk_controls()
        return page

    def _field_label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=row, column=0, padx=14, pady=(12, 4), sticky="ew"
        )

    def _update_asset_badge(self):
        if not hasattr(self, "auto_asset_badge"):
            return
        if self.engine:
            self.auto_asset_badge.configure(text=f"{self.assets.frame_count()} frame assets ready")
        else:
            self.auto_asset_badge.configure(text="Frame library missing")

    def auto_add_files(self):
        if not self.engine:
            messagebox.showwarning(APP_TITLE, "Frame library is missing. Open Frame Library and install/update assets first.")
            return
        patterns = " ".join(f"*{x}" for x in sorted(SUPPORTED_INPUTS))
        paths = filedialog.askopenfilenames(title="Choose Apple device screenshots", filetypes=[("Images", patterns), ("All files", "*.*")])
        self._add_auto_paths([Path(p) for p in paths])

    def auto_add_folder(self):
        if not self.engine:
            messagebox.showwarning(APP_TITLE, "Frame library is missing. Open Frame Library and install/update assets first.")
            return
        folder = filedialog.askdirectory(title="Choose screenshots folder")
        if folder:
            self._add_auto_paths(list_images(Path(folder), "Name"))

    def _add_auto_paths(self, paths):
        existing = {r.path.resolve() for r in self.auto_rows}
        next_index = max((r.added_index for r in self.auto_rows), default=-1) + 1
        for path in paths:
            try:
                path = Path(path)
                if path.resolve() in existing or path.suffix.lower() not in SUPPORTED_INPUTS:
                    continue
                info = self.engine.inspect(path)
                row = ScreenshotRow(self, self.auto_list, info, next_index)
                next_index += 1
                self.auto_rows.append(row)
                existing.add(path.resolve())
            except Exception as exc:
                messagebox.showwarning(APP_TITLE, f"Could not inspect {path.name}:\n{exc}")
        self.refresh_auto_row_positions()
        self.refresh_auto_summary()
        self.refresh_bulk_controls()

    def auto_clear(self):
        for r in self.auto_rows:
            r.frame.destroy()
        self.auto_rows.clear()
        self.refresh_auto_summary()
        self.refresh_bulk_controls()

    def _auto_row_sort_key(self, row: ScreenshotRow):
        try:
            timestamp = row.path.stat().st_mtime
        except Exception:
            timestamp = 0
        return (timestamp, row.path.name.lower(), row.added_index)

    def ordered_auto_rows(self):
        rows = list(self.auto_rows)
        order = self.auto_order.get() if hasattr(self, "auto_order") else "As added"
        if order == "Chronological (oldest first)":
            rows.sort(key=self._auto_row_sort_key)
        elif order == "Reverse chronological (newest first)":
            rows.sort(key=self._auto_row_sort_key, reverse=True)
        else:
            rows.sort(key=lambda r: r.added_index)
        return rows

    def refresh_auto_row_positions(self):
        if not hasattr(self, "auto_list"):
            return
        for idx, row in enumerate(self.ordered_auto_rows()):
            row.frame.grid(row=idx, column=0, padx=4, pady=5, sticky="ew")

    def auto_order_changed(self, _value=None):
        self.refresh_auto_row_positions()
        if self.auto_rows:
            self.auto_status.configure(text=f"Order: {self.auto_order.get()} (uses file modified time).")

    def refresh_auto_summary(self):
        n = len(self.auto_rows)
        supported = sum(1 for r in self.auto_rows if r.info.get("supported"))
        selected = sum(1 for r in self.auto_rows if r.selected_var.get())
        self.auto_summary.configure(
            text=f"{n} screenshot{'s' if n != 1 else ''}  •  {supported} auto-detected  •  {selected} selected"
        )
        if hasattr(self, "bulk_selected_label"):
            self.bulk_selected_label.configure(text=f"{selected} selected")

    def on_row_selection_changed(self):
        self.refresh_auto_summary()
        self.refresh_bulk_controls()

    def select_all_rows(self):
        for row in self.auto_rows:
            row.selected_var.set(True)
        self.refresh_auto_summary()
        self.refresh_bulk_controls()

    def select_no_rows(self):
        for row in self.auto_rows:
            row.selected_var.set(False)
        self.refresh_auto_summary()
        self.refresh_bulk_controls()

    def _bulk_target_rows(self):
        if not self.auto_rows:
            return []
        if self.auto_bulk_scope.get() == "Selected screenshots":
            return [r for r in self.auto_rows if r.selected_var.get()]
        return list(self.auto_rows)

    def refresh_bulk_controls(self):
        if not hasattr(self, "bulk_model_menu"):
            return
        targets = self._bulk_target_rows()
        selected = sum(1 for r in self.auto_rows if r.selected_var.get())
        self.bulk_selected_label.configure(text=f"{selected} selected")

        if not targets:
            values = ["Keep current"]
        else:
            compatible_sets = [set(r._device_values()) for r in targets]
            common = set.intersection(*compatible_sets) if compatible_sets else set()
            # Preserve the frame-library/variant order from the first target.
            ordered_common = [v for v in targets[0]._device_values() if v in common]
            values = ["Keep current"] + ordered_common

        current = self.auto_bulk_model.get()
        self.bulk_model_menu.configure(values=values)
        if current not in values:
            self.auto_bulk_model.set(values[1] if len(values) > 1 else "Keep current")
        elif current == "Keep current" and len(values) > 1:
            # Keep this conservative: never silently change model just because target scope changed.
            pass
        self.refresh_bulk_color_options()

    def refresh_bulk_color_options(self):
        if not hasattr(self, "bulk_color_menu"):
            return
        model = self.auto_bulk_model.get()
        values = ["Keep current", "Default", "Random"]
        if self.engine and model not in ("", "Keep current"):
            values += self.engine.colors_for(model)
        current = self.auto_bulk_color.get()
        self.bulk_color_menu.configure(values=values)
        if current not in values:
            self.auto_bulk_color.set("Keep current")

    def apply_bulk_settings(self):
        targets = self._bulk_target_rows()
        if not targets:
            messagebox.showinfo(APP_TITLE, "No screenshots are in the selected bulk target.")
            return
        model = self.auto_bulk_model.get()
        color = self.auto_bulk_color.get()
        changed_models = 0
        changed_colors = 0
        skipped = 0
        for row in targets:
            if model != "Keep current":
                if row.set_device(model):
                    changed_models += 1
                else:
                    skipped += 1
                    continue
            if color != "Keep current":
                if row.set_color(color):
                    changed_colors += 1
                elif color in ("Default", "Random"):
                    # Default/Random always have a sensible fallback when a model has colors.
                    vals = row._color_values_for_current()
                    if color in vals:
                        row.color_var.set(color)
                        changed_colors += 1
        self.refresh_bulk_controls()
        self.auto_status.configure(
            text=f"Bulk edit applied to {len(targets)} screenshot(s): {changed_models} model, {changed_colors} color changes"
            + (f" • {skipped} skipped" if skipped else "")
        )

    def set_all_colors(self, choice):
        for row in self.auto_rows:
            vals = row._color_values_for_current()
            if choice in vals:
                row.color_var.set(choice)

    def auto_mode_changed(self, value):
        self.auto_batch_entry.configure(state="normal" if value == "Batches" else "disabled")

    def auto_arrangement_changed(self, value):
        self.auto_columns_entry.configure(state="normal" if value == "Grid" else "disabled")

    def pick_auto_output(self):
        p = filedialog.askdirectory(title="Choose output folder")
        if p:
            self.auto_output_dir.set(p)

    def pick_auto_bg(self):
        c = colorchooser.askcolor(title="Pick composition background")
        if c and c[1]:
            self.auto_background.set(c[1])

    def cancel_auto(self):
        self.auto_cancel = True
        self.auto_status.configure(text="Cancel requested…")

    def _collect_auto_cfg(self):
        if not self.engine:
            raise ValueError("Frame library is not available.")
        if not self.auto_rows:
            raise ValueError("Add at least one screenshot.")
        rows = self.ordered_auto_rows()
        selections = [r.get_selection() for r in rows]
        spacing = max(0, int(self.auto_spacing.get().strip()))
        batch = max(2, int(self.auto_batch_size.get().strip() or "2"))
        columns_text = self.auto_columns.get().strip()
        columns = None
        if columns_text:
            columns = int(columns_text)
            if columns < 1:
                raise ValueError("Grid columns must be at least 1, or blank for Auto.")
        quality = max(1, min(100, int(self.auto_quality.get().strip())))
        png_comp = max(0, min(9, int(self.auto_png_compress.get().strip())))
        out_dir = Path(self.auto_output_dir.get().strip()).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        bg = self.auto_background.get().strip() or "transparent"
        if bg.lower() != "transparent":
            Image.new("RGBA", (1, 1), bg)  # validate color
        return {
            "selections": selections, "spacing": spacing, "batch": batch, "columns": columns,
            "quality": quality, "png": png_comp, "out_dir": out_dir,
            "format": self.auto_format.get(), "mode": self.auto_output_mode.get(),
            "order": self.auto_order.get(), "arrangement": self.auto_arrangement.get(),
            "proportional": self.auto_proportional.get(), "background": bg,
        }

    def _render_auto_selection(self, selection):
        path, device, color = selection
        return self.engine.render(path, device_name=device, color_choice=color)

    def auto_preview(self):
        try:
            cfg = self._collect_auto_cfg()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc)); return
        if cfg["mode"] == "Individual files" and len(cfg["selections"]) > 1:
            sels = cfg["selections"][:1]
        elif cfg["mode"] == "Batches":
            sels = cfg["selections"][:cfg["batch"]]
        else:
            sels = cfg["selections"]
        self.auto_status.configure(text="Building preview…")
        self.auto_progress.set(0)
        def worker():
            try:
                images, infos = [], []
                for i, sel in enumerate(sels):
                    im, inf = self._render_auto_selection(sel)
                    images.append(im); infos.append(inf)
                    self.ui(lambda p=(i + 1) / max(1, len(sels)): self.auto_progress.set(p * .8))
                preview = images[0] if len(images) == 1 else self.engine.compose(
                    images, infos, cfg["spacing"], cfg["proportional"], cfg["background"],
                    arrangement=cfg["arrangement"], columns=cfg["columns"]
                )
                self.ui(lambda: self._show_preview_window(preview))
                self.ui(lambda: self.auto_progress.set(1))
                self.ui(lambda: self.auto_status.configure(text="Preview ready."))
            except Exception as exc:
                self.ui(lambda e=exc: messagebox.showerror(APP_TITLE, str(e)))
                self.ui(lambda: self.auto_status.configure(text="Preview failed."))
        threading.Thread(target=worker, daemon=True).start()

    def _show_preview_window(self, image: Image.Image):
        win = ctk.CTkToplevel(self)
        win.title("Composition Preview")
        win.geometry("1000x760")
        win.transient(self)
        self._apply_window_icon(win)
        win.after(250, lambda: self._apply_window_icon(win))
        max_w, max_h = 930, 660
        scale = min(max_w / image.width, max_h / image.height, 1.0)
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        thumb = image.resize(size, Image.Resampling.LANCZOS) if scale < 1 else image
        bg = Image.new("RGB", thumb.size, "#d9d9d9")
        if thumb.mode == "RGBA":
            bg.paste(thumb, mask=thumb.getchannel("A"))
        else:
            bg.paste(thumb)
        cimg = ctk.CTkImage(light_image=bg, dark_image=bg, size=size)
        lab = ctk.CTkLabel(win, text="", image=cimg)
        lab.image = cimg
        lab.pack(expand=True, padx=20, pady=20)
        ctk.CTkLabel(win, text=f"Full output: {image.width:,} × {image.height:,} px").pack(pady=(0, 16))

    def auto_export(self):
        if self._auto_thread and self._auto_thread.is_alive():
            messagebox.showinfo(APP_TITLE, "An export is already running."); return
        try:
            cfg = self._collect_auto_cfg()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc)); return
        self.auto_cancel = False
        self.auto_progress.set(0)
        self.auto_status.configure(text="Rendering frames…")
        self._auto_thread = threading.Thread(target=self._auto_export_worker, args=(cfg,), daemon=True)
        self._auto_thread.start()

    def _auto_export_worker(self, cfg):
        try:
            selections = cfg["selections"]
            rendered = []
            infos = []
            for i, sel in enumerate(selections):
                if self.auto_cancel:
                    raise RuntimeError("Export cancelled.")
                im, info = self._render_auto_selection(sel)
                rendered.append(im); infos.append(info)
                pct = .65 * (i + 1) / len(selections)
                self.ui(lambda p=pct, inf=info: (self.auto_progress.set(p), self.auto_status.configure(text=f"Framed {inf['device']}…")))

            outputs = []
            mode = cfg["mode"]
            fmt = cfg["format"]
            if mode == "Individual files":
                for i, (im, sel) in enumerate(zip(rendered, selections)):
                    path = cfg["out_dir"] / f"{Path(sel[0]).stem}_framed"
                    outputs.append(save_image(im, path, fmt, cfg["quality"], cfg["png"]))
                    self.ui(lambda p=.65 + .35 * (i + 1) / len(rendered): self.auto_progress.set(p))
            elif mode == "Batches":
                batches = math.ceil(len(rendered) / cfg["batch"])
                for b in range(batches):
                    if self.auto_cancel:
                        raise RuntimeError("Export cancelled.")
                    s, e = b * cfg["batch"], min(len(rendered), (b + 1) * cfg["batch"])
                    merged = self.engine.compose(
                        rendered[s:e], infos[s:e], cfg["spacing"], cfg["proportional"], cfg["background"],
                        arrangement=cfg["arrangement"], columns=cfg["columns"]
                    )
                    outputs.append(save_image(merged, cfg["out_dir"] / f"merged_{b+1}_framed", fmt, cfg["quality"], cfg["png"]))
                    self.ui(lambda p=.65 + .35 * (b + 1) / batches: self.auto_progress.set(p))
            else:
                merged = rendered[0] if len(rendered) == 1 else self.engine.compose(
                    rendered, infos, cfg["spacing"], cfg["proportional"], cfg["background"],
                    arrangement=cfg["arrangement"], columns=cfg["columns"]
                )
                name = f"{Path(selections[0][0]).stem}_framed" if len(rendered) == 1 else "merged_framed"
                outputs.append(save_image(merged, cfg["out_dir"] / name, fmt, cfg["quality"], cfg["png"]))
                self.ui(lambda: self.auto_progress.set(1))

            self.ui(lambda: self.auto_status.configure(text=f"Done — saved {len(outputs)} file(s) to {cfg['out_dir']}"))
            self.ui(lambda: self.auto_progress.set(1))
            self.ui(lambda: messagebox.showinfo(APP_TITLE, f"Finished.\n\nSaved {len(outputs)} file(s) to:\n{cfg['out_dir']}"))
        except Exception as exc:
            self.ui(lambda e=exc: self.auto_status.configure(text=str(e)))
            if "cancelled" not in str(exc).lower():
                self.ui(lambda e=exc: messagebox.showerror(APP_TITLE, str(e)))

    # ---------- manual grid ----------
    def _build_manual_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(page, text="Manual Grid", font=ctk.CTkFont(size=30, weight="bold")).grid(row=0, column=0, padx=28, pady=(26, 2), sticky="w")
        ctk.CTkLabel(page, text="Your original tight-grid workflow, preserved with the same placement, orientation, gap, compression and giant-canvas controls.",
                     text_color=("#666", "#aaa")).grid(row=0, column=0, padx=28, pady=(68, 12), sticky="w")

        scroll = ctk.CTkScrollableFrame(page, corner_radius=14)
        scroll.grid(row=1, column=0, padx=28, pady=(8, 10), sticky="nsew")
        scroll.grid_columnconfigure((0, 1), weight=1)

        self.m_frame = ctk.StringVar(); self.m_folder = ctk.StringVar(); self.m_output = ctk.StringVar()
        self.m_sw = ctk.StringVar(value="1179"); self.m_sh = ctk.StringVar(value="2556")
        self.m_sx = ctk.StringVar(value=""); self.m_sy = ctk.StringVar(value="")
        self.m_orientation = ctk.StringVar(value="Auto"); self.m_rotate = ctk.StringVar(value="Left (CCW)")
        self.m_gridmode = ctk.StringVar(value="Tight"); self.m_columns = ctk.StringVar(value="")
        self.m_gapx = ctk.StringVar(value="12"); self.m_gapy = ctk.StringVar(value="12"); self.m_lock = ctk.BooleanVar(value=True)
        self.m_bg = ctk.StringVar(value="#ffffff"); self.m_radius = ctk.StringVar(value="130")
        self.m_inset = ctk.StringVar(value="4"); self.m_fill = ctk.StringVar(value="103")
        self.m_format = ctk.StringVar(value="PNG"); self.m_quality = ctk.StringVar(value="92")
        self.m_png = ctk.StringVar(value="1"); self.m_opt = ctk.BooleanVar(value=False); self.m_prog = ctk.BooleanVar(value=False)
        self.m_heif = ctk.BooleanVar(value=False); self.m_workers = ctk.StringVar(value=str(max(1, os.cpu_count() or 1)))
        self.m_sort = ctk.StringVar(value="Name")

        files_card = self._card(scroll, "Files", 0, 0, colspan=2)
        self._path_row(files_card, "Frame image", self.m_frame, self.pick_manual_frame, 0)
        self._path_row(files_card, "Screenshots folder", self.m_folder, self.pick_manual_folder, 1)
        self._path_row(files_card, "Output file", self.m_output, self.pick_manual_output, 2)

        place = self._card(scroll, "Screen placement inside frame", 1, 0)
        self._entry_pair(place, "Screen width", self.m_sw, "Screen height", self.m_sh, 0)
        self._entry_pair(place, "Screen X", self.m_sx, "Screen Y", self.m_sy, 1)
        self._entry_pair(place, "Corner radius", self.m_radius, "Inset px", self.m_inset, 2)
        self._entry_pair(place, "Fill scale %", self.m_fill, "Workers", self.m_workers, 3)
        ctk.CTkButton(place, text="Auto-read from frame filename", fg_color="transparent", border_width=1,
                      command=self.manual_autofill).grid(row=4, column=0, columnspan=4, padx=12, pady=(8, 12), sticky="ew")

        layout = self._card(scroll, "Layout", 1, 1)
        self._option_row(layout, "Image orientation", self.m_orientation, ["Auto", "Keep original", "Force portrait", "Force landscape"], 0)
        self._option_row(layout, "Landscape frame rotation", self.m_rotate, ["Left (CCW)", "Right (CW)"], 1)
        self._option_row(layout, "Grid mode", self.m_gridmode, ["Tight", "Uniform cell"], 2)
        self._entry_pair(layout, "Columns (blank = auto)", self.m_columns, "Horizontal gap", self.m_gapx, 3)
        self._entry_pair(layout, "Vertical gap", self.m_gapy, "Background", self.m_bg, 4)
        ctk.CTkSwitch(layout, text="Lock vertical gap to horizontal gap", variable=self.m_lock).grid(row=5, column=0, columnspan=4, padx=12, pady=8, sticky="w")
        self._option_row(layout, "Sort", self.m_sort, ["Name", "Modified time"], 6)

        out = self._card(scroll, "Output / compression", 2, 0)
        self._option_row(out, "Format", self.m_format, ["PNG", "JPEG", "WEBP", "TIFF", "BMP", "PDF"], 0)
        self._entry_pair(out, "JPEG / WebP quality", self.m_quality, "PNG compress 0–9", self.m_png, 1)
        ctk.CTkSwitch(out, text="Optimize", variable=self.m_opt).grid(row=2, column=0, columnspan=2, padx=12, pady=7, sticky="w")
        ctk.CTkSwitch(out, text="Progressive JPEG", variable=self.m_prog).grid(row=3, column=0, columnspan=2, padx=12, pady=7, sticky="w")
        ctk.CTkSwitch(out, text="Also save HEIF / HEIC copy", variable=self.m_heif).grid(row=4, column=0, columnspan=2, padx=12, pady=7, sticky="w")

        actions = self._card(scroll, "Build", 2, 1)
        self.manual_estimate_label = ctk.CTkLabel(actions, text="No estimate yet.", justify="left", anchor="w")
        self.manual_estimate_label.grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 8), sticky="ew")
        ctk.CTkButton(actions, text="Estimate output", fg_color="transparent", border_width=1, command=self.manual_estimate).grid(row=1, column=0, padx=(12, 6), pady=6, sticky="ew")
        ctk.CTkButton(actions, text="Build giant image", command=self.manual_build).grid(row=1, column=1, padx=(6, 12), pady=6, sticky="ew")
        ctk.CTkButton(actions, text="Cancel", fg_color="transparent", border_width=1, command=self.cancel_manual).grid(row=2, column=0, columnspan=2, padx=12, pady=(6, 12), sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)

        self.manual_progress = ctk.CTkProgressBar(page)
        self.manual_progress.grid(row=2, column=0, padx=28, pady=(0, 4), sticky="ew")
        self.manual_progress.set(0)
        self.manual_status = ctk.CTkLabel(page, text="Ready.", anchor="w", text_color=("#666", "#aaa"))
        self.manual_status.grid(row=3, column=0, padx=30, pady=(0, 18), sticky="ew")
        return page

    def _card(self, parent, title, row, col, colspan=1):
        card = ctk.CTkFrame(parent, corner_radius=14)
        card.grid(row=row, column=col, columnspan=colspan, padx=7, pady=7, sticky="nsew")
        card.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=4, padx=12, pady=(12, 4), sticky="w")
        return card

    def _path_row(self, parent, label, var, command, row):
        rr = row + 1
        ctk.CTkLabel(parent, text=label).grid(row=rr, column=0, padx=12, pady=6, sticky="w")
        ctk.CTkEntry(parent, textvariable=var).grid(row=rr, column=1, columnspan=2, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(parent, text="Browse", width=76, command=command).grid(row=rr, column=3, padx=(6, 12), pady=6)

    def _entry_pair(self, parent, l1, v1, l2, v2, row):
        rr = row + 1
        ctk.CTkLabel(parent, text=l1).grid(row=rr, column=0, padx=(12, 6), pady=6, sticky="w")
        ctk.CTkEntry(parent, textvariable=v1, width=110).grid(row=rr, column=1, padx=6, pady=6, sticky="ew")
        ctk.CTkLabel(parent, text=l2).grid(row=rr, column=2, padx=6, pady=6, sticky="w")
        ctk.CTkEntry(parent, textvariable=v2, width=110).grid(row=rr, column=3, padx=(6, 12), pady=6, sticky="ew")

    def _option_row(self, parent, label, var, values, row):
        rr = row + 1
        ctk.CTkLabel(parent, text=label).grid(row=rr, column=0, padx=12, pady=6, sticky="w")
        ctk.CTkOptionMenu(parent, values=values, variable=var).grid(row=rr, column=1, columnspan=3, padx=(6, 12), pady=6, sticky="ew")

    def pick_manual_frame(self):
        p = filedialog.askopenfilename(title="Choose frame image", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.heic *.heif"), ("All files", "*.*")])
        if p:
            self.m_frame.set(p); self.manual_autofill()

    def pick_manual_folder(self):
        p = filedialog.askdirectory(title="Choose screenshots folder")
        if p: self.m_folder.set(p)

    def pick_manual_output(self):
        p = filedialog.asksaveasfilename(title="Choose output file", defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("WebP", "*.webp"), ("TIFF", "*.tif"), ("BMP", "*.bmp"), ("PDF", "*.pdf")])
        if p: self.m_output.set(p)

    def manual_autofill(self):
        p = self.m_frame.get().strip()
        if not p: return
        info = parse_frame_filename(Path(p).name)
        if info:
            sw, sh, x, y = info
            self.m_sw.set(str(sw)); self.m_sh.set(str(sh)); self.m_sx.set(str(x)); self.m_sy.set(str(y))
            self.manual_status.configure(text=f"Read placement from frame filename: {sw}×{sh}+{x}+{y}")

    def _ival(self, var, label, blank=False):
        s = var.get().strip()
        if blank and not s: return None
        try: return int(s)
        except Exception: raise ValueError(f"{label} must be an integer.")

    def _collect_manual_cfg(self):
        frame, folder = Path(self.m_frame.get().strip()), Path(self.m_folder.get().strip())
        out = Path(self.m_output.get().strip())
        if not frame.exists(): raise ValueError("Choose a valid frame image.")
        if not folder.is_dir(): raise ValueError("Choose a valid screenshots folder.")
        if not str(out).strip(): raise ValueError("Choose an output file.")
        files = list_images(folder, self.m_sort.get())
        if not files: raise ValueError("No supported images were found in the selected folder.")
        gx = self._ival(self.m_gapx, "Horizontal gap")
        gy = gx if self.m_lock.get() else self._ival(self.m_gapy, "Vertical gap")
        return {
            "frame": frame, "files": files,
            "screen_w": self._ival(self.m_sw, "Screen width"), "screen_h": self._ival(self.m_sh, "Screen height"),
            "screen_x": self._ival(self.m_sx, "Screen X"), "screen_y": self._ival(self.m_sy, "Screen Y"),
            "corner_radius": self._ival(self.m_radius, "Corner radius"), "inset": self._ival(self.m_inset, "Inset"),
            "columns": self._ival(self.m_columns, "Columns", True), "gap_x": gx, "gap_y": gy,
            "fill_scale": self._ival(self.m_fill, "Fill scale"), "workers": self._ival(self.m_workers, "Workers"),
            "bg": self.m_bg.get().strip() or "#ffffff", "orientation_mode": self.m_orientation.get(),
            "rotate_landscape": self.m_rotate.get(), "grid_mode": self.m_gridmode.get(),
            "out": out, "format": self.m_format.get(), "quality": self._ival(self.m_quality, "Quality"),
            "png": self._ival(self.m_png, "PNG compression"), "opt": self.m_opt.get(), "prog": self.m_prog.get(),
            "heif": self.m_heif.get(),
        }

    def manual_estimate(self):
        try:
            cfg = self._collect_manual_cfg(); e = manual_grid_estimate(cfg)
            self.manual_estimate_label.configure(text=f"Canvas: {e['width']:,} × {e['height']:,} px\nRaw RGBA RAM ≈ {e['ram_gb']:.2f} GB  •  {e['count']} images")
            self.manual_status.configure(text="Estimate complete.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def cancel_manual(self):
        self.manual_cancel = True
        self.manual_status.configure(text="Cancel requested…")

    def manual_build(self):
        if self._manual_thread and self._manual_thread.is_alive():
            messagebox.showinfo(APP_TITLE, "A manual grid build is already running."); return
        try: cfg = self._collect_manual_cfg()
        except Exception as exc: messagebox.showerror(APP_TITLE, str(exc)); return
        self.manual_cancel = False; self.manual_progress.set(0); self.manual_status.configure(text="Starting…")
        self._manual_thread = threading.Thread(target=self._manual_worker, args=(cfg,), daemon=True)
        self._manual_thread.start()

    def _manual_worker(self, cfg):
        started = time.time()
        try:
            def progress(pct, text):
                self.ui(lambda: self.manual_progress.set(max(0, min(1, pct / 100))))
                self.ui(lambda: self.manual_status.configure(text=text))
            giant, meta = build_manual_grid(cfg, progress_cb=progress, cancel_cb=lambda: self.manual_cancel)
            if self.manual_cancel: raise RuntimeError("Build cancelled.")
            self.ui(lambda: self.manual_status.configure(text="Saving output…"))
            out = save_image(giant, cfg["out"], cfg["format"], cfg["quality"], cfg["png"], cfg["opt"], cfg["prog"])
            if cfg["heif"]:
                if HEIF_OK:
                    giant.convert("RGB").save(out.with_suffix(".heic"), format="HEIF", quality=max(1, min(100, cfg["quality"])))
                else:
                    self.ui(lambda: messagebox.showwarning(APP_TITLE, "HEIF copy skipped because pillow-heif is not installed."))
            elapsed = time.time() - started
            self.ui(lambda: self.manual_progress.set(1))
            self.ui(lambda: self.manual_status.configure(text=f"Done in {elapsed:.1f}s  •  {meta['width']:,}×{meta['height']:,} px"))
            self.ui(lambda: messagebox.showinfo(APP_TITLE, f"Finished.\n\nSaved:\n{out}"))
        except Exception as exc:
            self.ui(lambda e=exc: self.manual_status.configure(text=str(e)))
            if "cancelled" not in str(exc).lower(): self.ui(lambda e=exc: messagebox.showerror(APP_TITLE, str(e)))

    # ---------- library ----------
    def _build_library_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(page, text="Frame Library", font=ctk.CTkFont(size=30, weight="bold")).grid(row=0, column=0, padx=28, pady=(26, 4), sticky="w")
        ctk.CTkLabel(page, text="The app uses your bundled Apple Frames pack offline and can refresh it from the same MacStories CDN used by Apple Frames 4.",
                     text_color=("#666", "#aaa")).grid(row=1, column=0, padx=28, pady=(0, 18), sticky="w")

        card = ctk.CTkFrame(page, corner_radius=16)
        card.grid(row=2, column=0, padx=28, pady=8, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        self.lib_status = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=18, weight="bold"), anchor="w")
        self.lib_status.grid(row=0, column=0, padx=18, pady=(18, 4), sticky="ew")
        self.lib_path = ctk.CTkLabel(card, text="", anchor="w", justify="left", wraplength=900, text_color=("#666", "#aaa"))
        self.lib_path.grid(row=1, column=0, padx=18, pady=(0, 16), sticky="ew")

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="ew")
        ctk.CTkButton(actions, text="Download / Update from MacStories", command=self.library_update).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Use custom Frames folder", fg_color="transparent", border_width=1, command=self.library_custom).pack(side="left", padx=8)
        ctk.CTkButton(actions, text="Reset to bundled / downloaded", fg_color="transparent", border_width=1, command=self.library_reset).pack(side="left", padx=8)

        self.lib_progress = ctk.CTkProgressBar(page)
        self.lib_progress.grid(row=3, column=0, padx=28, pady=(18, 4), sticky="ew")
        self.lib_progress.set(0)
        self.lib_detail = ctk.CTkLabel(page, text="", anchor="w", text_color=("#666", "#aaa"))
        self.lib_detail.grid(row=4, column=0, padx=30, pady=(0, 14), sticky="ew")

        info = ctk.CTkFrame(page, corner_radius=16)
        info.grid(row=5, column=0, padx=28, pady=8, sticky="ew")
        ctk.CTkLabel(info, text="What is supported", font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(info, justify="left", anchor="w", wraplength=1000,
                     text="• Automatic resolution detection and overlapping-resolution variants\n"
                          "• iPhone, iPad, Apple Watch, MacBook, iMac and Studio Display assets present in NewFrames.json\n"
                          "• Portrait / landscape frames, official color variants and masks\n"
                          "• Mixed-device proportional scaling using physical-height metadata\n"
                          "• One-shot merge, sequential batches, individual exports, random colors, manual override and your original tight-grid mode").pack(
            anchor="w", padx=18, pady=(0, 18)
        )
        return page

    def refresh_library_status(self):
        path = self.assets.resolve(); count = self.assets.frame_count()
        if path:
            self.lib_status.configure(text=f"Frame library ready  •  {count} PNG assets")
            self.lib_path.configure(text=str(path))
        else:
            self.lib_status.configure(text="Frame library not installed")
            self.lib_path.configure(text="Use the update button to download Apple Frames 4 assets.")
        self._update_asset_badge()

    def library_update(self):
        self.lib_progress.set(0); self.lib_detail.configure(text="Starting download…")
        def worker():
            try:
                self.assets.download_latest(
                    progress_cb=lambda p: self.ui(lambda: self.lib_progress.set(p / 100)),
                    status_cb=lambda s: self.ui(lambda: self.lib_detail.configure(text=s))
                )
                self._load_engine()
                self.ui(self.refresh_library_status)
                self.ui(lambda: self.lib_detail.configure(text="Frame library updated successfully."))
                self.ui(lambda: messagebox.showinfo(APP_TITLE, "Frame library updated successfully."))
            except Exception as exc:
                self.ui(lambda e=exc: self.lib_detail.configure(text=f"Update failed: {e}"))
                self.ui(lambda e=exc: messagebox.showerror(APP_TITLE, f"Frame library update failed:\n\n{e}"))
        threading.Thread(target=worker, daemon=True).start()

    def library_custom(self):
        p = filedialog.askdirectory(title="Choose a Frames folder containing NewFrames.json")
        if not p: return
        try:
            self.assets.set_custom_path(Path(p)); self._load_engine(); self.refresh_library_status()
            messagebox.showinfo(APP_TITLE, "Custom frame library selected.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def library_reset(self):
        try:
            self.assets.set_custom_path(None); self._load_engine(); self.refresh_library_status()
            messagebox.showinfo(APP_TITLE, "Custom override cleared.")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))


def main():
    app = AppleFramesStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
