import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import fitz  # PyMuPDF
from PIL import Image, ImageTk, ImageOps, ImageEnhance

from profiles import (
    DEVICE_PROFILES,
    DEFAULT_PROFILE,
    build_profile,
    save_custom_profiles,
    get_last_profile,
    save_last_profile,
)

THUMB_SIZE = 256


class ExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Extractor y Editor de Partituras para eBooks")
        self.root.geometry("1100x750")

        # Variables de estado
        self.doc = None
        self.pdf_path = ""
        self.current_page = 0
        self.rotation = 0
        self.crop_start = None
        self.crop_rect = None
        self.selected_box = None
        self.image_offset_x = 0
        self.image_offset_y = 0
        self.thumb_images = []
        self.thumb_labels = []
        self.contrast = tk.DoubleVar(value=1.0)
        self.fine_rotation = tk.DoubleVar(value=0.0)
        self.fixed_ratio_crop = tk.BooleanVar(value=False)
        self._ratio_drag_mode = None  # "move" or "resize"
        self._ratio_drag_start = None
        self._ratio_rect_coords = None  # (x0, y0, x1, y1) in canvas coords
        initial_key = get_last_profile()
        self.profile_key = tk.StringVar(value=initial_key)
        self.active_profile = DEVICE_PROFILES[initial_key]

        self.setup_ui()

    # ── UI setup ────────────────────────────────────────────────────────

    def setup_ui(self):
        # Panel Izquierdo: Controles
        left_panel = ttk.Frame(self.root, padding=10, width=300)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        left_panel.pack_propagate(False)

        controls_frame = ttk.Frame(left_panel)
        controls_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Button(controls_frame, text="Cargar PDF Completo", command=self.load_pdf).pack(fill=tk.X, pady=5)

        # Perfil de dispositivo
        ttk.Label(controls_frame, text="Dispositivo", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5, 0))
        self._profile_names = [p["name"] for p in DEVICE_PROFILES.values()]
        self._profile_keys = list(DEVICE_PROFILES.keys())
        self.profile_display = tk.StringVar(value=self.active_profile["name"])
        profile_row = ttk.Frame(controls_frame)
        profile_row.pack(fill=tk.X, pady=5)
        self.profile_combo = ttk.Combobox(profile_row, textvariable=self.profile_display, values=self._profile_names, state="readonly")
        self.profile_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_change)
        ttk.Button(profile_row, text="+", width=3, command=self.add_custom_profile).pack(side=tk.LEFT, padx=(4, 0))

        # Info de Página
        self.lbl_page = ttk.Label(controls_frame, text="Página: -- / --", font=("Arial", 11, "bold"))
        self.lbl_page.pack(pady=5)

        # Navegación
        nav_frame = ttk.Frame(controls_frame)
        nav_frame.pack(fill=tk.X, pady=5)
        ttk.Button(nav_frame, text="◀ Ant", command=self.prev_page).pack(side=tk.LEFT, expand=True)
        ttk.Button(nav_frame, text="Sig ▶", command=self.next_page).pack(side=tk.RIGHT, expand=True)

        ttk.Button(controls_frame, text="🔄 Girar 90°", command=self.rotate_page).pack(fill=tk.X, pady=5)

        # Opciones adicionales (collapsible)
        self._extra_opts_visible = tk.BooleanVar(value=False)
        extra_header = ttk.Frame(controls_frame)
        extra_header.pack(fill=tk.X, pady=(10, 0))
        self._extra_toggle_btn = ttk.Button(
            extra_header, text="▶ Opciones adicionales", command=self._toggle_extra_opts,
        )
        self._extra_toggle_btn.pack(fill=tk.X)

        self._extra_opts_frame = ttk.Frame(controls_frame)
        # Contrast slider
        ttk.Label(self._extra_opts_frame, text="Contraste").pack(anchor=tk.W, pady=(4, 0))
        contrast_row = ttk.Frame(self._extra_opts_frame)
        contrast_row.pack(fill=tk.X)
        self.contrast_scale = ttk.Scale(
            contrast_row, from_=0.5, to=2.0, variable=self.contrast,
            orient=tk.HORIZONTAL, command=lambda _: self._on_adjustment_change(),
        )
        self.contrast_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(contrast_row, text="↺", width=2,
                    command=lambda: self._reset_slider(self.contrast, 1.0)).pack(side=tk.LEFT, padx=(4, 0))

        # Fine rotation slider
        ttk.Label(self._extra_opts_frame, text="Rotación fina (°)").pack(anchor=tk.W, pady=(6, 0))
        rotation_row = ttk.Frame(self._extra_opts_frame)
        rotation_row.pack(fill=tk.X)
        self.fine_rot_scale = ttk.Scale(
            rotation_row, from_=-15.0, to=15.0, variable=self.fine_rotation,
            orient=tk.HORIZONTAL, command=lambda _: self._on_adjustment_change(),
        )
        self.fine_rot_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(rotation_row, text="↺", width=2,
                    command=lambda: self._reset_slider(self.fine_rotation, 0.0)).pack(side=tk.LEFT, padx=(4, 0))

        # Fixed aspect ratio crop
        ttk.Checkbutton(
            self._extra_opts_frame, text="Recorte con ratio del dispositivo",
            variable=self.fixed_ratio_crop, command=self._on_fixed_ratio_toggle,
        ).pack(anchor=tk.W, pady=(8, 0))

        ttk.Separator(controls_frame, orient="horizontal").pack(fill=tk.X, pady=15)

        # Exportación
        ttk.Label(controls_frame, text="Exportar Selección", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        ttk.Button(controls_frame, text="💾 Guardar Página Actual Cortada", command=self.save_cropped_page).pack(fill=tk.X, pady=5)

        # Miniaturas
        ttk.Separator(controls_frame, orient="horizontal").pack(fill=tk.X, pady=(10, 8))
        ttk.Label(controls_frame, text="Miniaturas", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        thumbs_container = ttk.Frame(controls_frame)
        thumbs_container.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self.thumbs_text = tk.Text(
            thumbs_container, bg="#e8e8e8", cursor="arrow",
            wrap=tk.NONE, state=tk.DISABLED, highlightthickness=0,
            borderwidth=0, padx=4, pady=4,
        )
        self.thumbs_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumbs_scroll = ttk.Scrollbar(thumbs_container, orient=tk.VERTICAL, command=self.thumbs_text.yview)
        self.thumbs_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.thumbs_text.configure(yscrollcommand=self.thumbs_scroll.set)

        self.bind_keyboard_shortcuts()

        # Panel Derecho: Visualizador
        self.right_panel = ttk.Frame(self.root, padding=10)
        self.right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(self.right_panel, bg="gray", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_crop_start)
        self.canvas.bind("<B1-Motion>", self.on_crop_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_crop_end)

    # ── Keyboard shortcuts ──────────────────────────────────────────────

    def bind_keyboard_shortcuts(self):
        self.root.bind_all("<Left>", self.on_prev_page_key)
        self.root.bind_all("<Up>", self.on_prev_page_key)
        self.root.bind_all("<Right>", self.on_next_page_key)
        self.root.bind_all("<Down>", self.on_next_page_key)

    def on_prev_page_key(self, _event=None):
        self.prev_page()

    def on_next_page_key(self, _event=None):
        self.next_page()

    # ── Extra options ───────────────────────────────────────────────────

    def _toggle_extra_opts(self):
        if self._extra_opts_visible.get():
            self._extra_opts_frame.pack_forget()
            self._extra_toggle_btn.configure(text="▶ Opciones adicionales")
            self._extra_opts_visible.set(False)
        else:
            self._extra_opts_frame.pack(after=self._extra_toggle_btn.master, fill=tk.X)
            self._extra_toggle_btn.configure(text="▼ Opciones adicionales")
            self._extra_opts_visible.set(True)

    def _reset_slider(self, var, default):
        var.set(default)
        self._on_adjustment_change()

    def _on_adjustment_change(self):
        if self.doc:
            self.render_page()

    def _apply_adjustments(self, img):
        """Apply contrast and fine rotation to an image."""
        contrast = self.contrast.get()
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        fine_rot = self.fine_rotation.get()
        if fine_rot != 0.0:
            img = img.rotate(-fine_rot, expand=True, fillcolor=(255, 255, 255))
        return img

    def _on_fixed_ratio_toggle(self):
        """When toggling the fixed-ratio crop, place or remove the crop rectangle."""
        if self.crop_rect:
            self.canvas.delete(self.crop_rect)
            self.crop_rect = None
        self.selected_box = None
        self._ratio_rect_coords = None
        if self.fixed_ratio_crop.get() and self.doc:
            self._place_ratio_rect()

    def _place_ratio_rect(self):
        """Place a fixed-ratio rectangle centered on the displayed image."""
        if not self.doc or not hasattr(self, 'display_img'):
            return
        prof = self.active_profile
        ratio = prof["screen_w"] / prof["screen_h"]
        img_w = self.display_img.width
        img_h = self.display_img.height

        # Fit the rect inside the image, 80% of the smaller dimension
        if img_w / img_h > ratio:
            rect_h = int(img_h * 0.8)
            rect_w = int(rect_h * ratio)
        else:
            rect_w = int(img_w * 0.8)
            rect_h = int(rect_w / ratio)

        cx = self.image_offset_x + img_w // 2
        cy = self.image_offset_y + img_h // 2
        x0 = cx - rect_w // 2
        y0 = cy - rect_h // 2
        x1 = x0 + rect_w
        y1 = y0 + rect_h
        self._ratio_rect_coords = (x0, y0, x1, y1)
        if self.crop_rect:
            self.canvas.delete(self.crop_rect)
        self.crop_rect = self.canvas.create_rectangle(x0, y0, x1, y1, outline="blue", width=2, dash=(6, 4))
        self._update_selected_box()

    def _update_selected_box(self):
        """Convert current ratio rect canvas coords to orig_img pixel coords."""
        if not self._ratio_rect_coords:
            return
        x0, y0, x1, y1 = self._ratio_rect_coords
        x0_rel = x0 - self.image_offset_x
        y0_rel = y0 - self.image_offset_y
        x1_rel = x1 - self.image_offset_x
        y1_rel = y1 - self.image_offset_y
        self.selected_box = (
            int(x0_rel * self.scale_x),
            int(y0_rel * self.scale_y),
            int(x1_rel * self.scale_x),
            int(y1_rel * self.scale_y),
        )

    # ── Profile management ──────────────────────────────────────────────

    def on_canvas_resize(self, _event=None):
        if self.doc:
            self.render_page()

    def on_profile_change(self, _event=None):
        idx = self._profile_names.index(self.profile_display.get())
        key = self._profile_keys[idx]
        self.profile_key.set(key)
        self.active_profile = DEVICE_PROFILES[key]
        save_last_profile(key)
        if self.doc:
            self.render_page()

    def _refresh_profile_combo(self):
        self._profile_names = [p["name"] for p in DEVICE_PROFILES.values()]
        self._profile_keys = list(DEVICE_PROFILES.keys())
        self.profile_combo["values"] = self._profile_names

    def add_custom_profile(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Nuevo Perfil")
        dlg.resizable(False, False)
        dlg.grab_set()

        fields = {}
        for label, key, default in [
            ("Nombre", "name", ""),
            ("Ancho pantalla (px)", "screen_w", "1264"),
            ("Alto pantalla (px)", "screen_h", "1680"),
            ("Diagonal (pulgadas)", "diagonal", "7"),
        ]:
            row = ttk.Frame(dlg, padding=(10, 4))
            row.pack(fill=tk.X)
            ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True)
            fields[key] = var

        def on_save():
            name = fields["name"].get().strip()
            if not name:
                messagebox.showwarning("Atención", "Escribe un nombre para el perfil.", parent=dlg)
                return
            try:
                sw = int(fields["screen_w"].get())
                sh = int(fields["screen_h"].get())
                diag = float(fields["diagonal"].get())
            except ValueError:
                messagebox.showwarning("Atención", "Ancho y alto deben ser enteros, diagonal un número.", parent=dlg)
                return
            if sw <= 0 or sh <= 0 or diag <= 0:
                messagebox.showwarning("Atención", "Los valores deben ser positivos.", parent=dlg)
                return
            key = "custom_" + name.lower().replace(" ", "_")
            DEVICE_PROFILES[key] = build_profile(name, sw, sh, diag)
            save_custom_profiles()
            self._refresh_profile_combo()
            self.profile_display.set(name)
            self.on_profile_change()
            dlg.destroy()

        btn_frame = ttk.Frame(dlg, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Guardar", command=on_save).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancelar", command=dlg.destroy).pack(side=tk.RIGHT, padx=(0, 5))

    # ── PDF loading ─────────────────────────────────────────────────────

    def load_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("Archivos PDF", "*.pdf")])
        if file_path:
            self.pdf_path = file_path
            try:
                doc = fitz.open(file_path)
                # Validate that pages are accessible
                for i in range(len(doc)):
                    _ = doc[i]
                self.doc = doc
            except Exception:
                messagebox.showwarning(
                    "Documento no compatible",
                    "El documento no puede ser procesado, prueba a imprimir a PDF desde cualquier otra aplicación y vuelve a intentarlo.",
                )
                return
            self.current_page = 0
            self.rotation = 0
            self.selected_box = None
            self.build_thumbnail_ribbon()
            self.render_page()

    # ── Thumbnails ──────────────────────────────────────────────────────

    def build_thumbnail_ribbon(self):
        self.thumb_images = []
        self.thumb_labels = []

        self.thumbs_text.configure(state=tk.NORMAL)
        self.thumbs_text.delete("1.0", tk.END)

        if not self.doc:
            self.thumbs_text.configure(state=tk.DISABLED)
            return

        for i, page in enumerate(self.doc):
            thumb_zoom = 0.2
            thumb_pix = page.get_pixmap(matrix=fitz.Matrix(thumb_zoom, thumb_zoom))
            thumb_img = Image.frombytes("RGB", [thumb_pix.width, thumb_pix.height], thumb_pix.samples)
            thumb_img = ImageOps.contain(thumb_img, (THUMB_SIZE, THUMB_SIZE))
            thumb_tk = ImageTk.PhotoImage(thumb_img)
            self.thumb_images.append(thumb_tk)

            tag_name = f"thumb_{i}"
            if i > 0:
                self.thumbs_text.insert(tk.END, "\n")
            start_mark = self.thumbs_text.index("end-1c")
            self.thumbs_text.insert(tk.END, f"{i + 1}\n")
            self.thumbs_text.image_create(tk.END, image=thumb_tk)
            self.thumbs_text.insert(tk.END, "\n")
            end_mark = self.thumbs_text.index("end-1c")
            self.thumbs_text.tag_add(tag_name, start_mark, end_mark)

            self.thumbs_text.tag_bind(tag_name, "<Button-1>", lambda _e, idx=i: self.go_to_page(idx))
            self.thumbs_text.tag_configure(tag_name, justify=tk.CENTER)

        self.thumbs_text.tag_configure("sel", justify=tk.CENTER)
        self.thumbs_text.configure(state=tk.DISABLED)
        self.highlight_current_thumbnail()

    def highlight_current_thumbnail(self):
        if not self.doc:
            return
        for i in range(len(self.doc)):
            tag_name = f"thumb_{i}"
            if i == self.current_page:
                self.thumbs_text.tag_configure(tag_name, background="#d7ebff")
            else:
                self.thumbs_text.tag_configure(tag_name, background="#e8e8e8")
        self.scroll_to_current_thumbnail()

    def scroll_to_current_thumbnail(self):
        if not self.doc or not self.thumb_images:
            return
        tag_name = f"thumb_{self.current_page}"
        tag_range = self.thumbs_text.tag_ranges(tag_name)
        if tag_range:
            self.thumbs_text.see(tag_range[0])

    # ── Page rendering & navigation ────────────────────────────────────

    def go_to_page(self, page_idx):
        if not self.doc:
            return
        self.current_page = page_idx
        self.rotation = 0
        self.selected_box = None
        self.render_page()

    def render_page(self):
        if not self.doc:
            return

        page = self.doc[self.current_page]
        total_rotation = (page.rotation + self.rotation) % 360

        zoom = self.active_profile["render_zoom"]
        mat = fitz.Matrix(zoom, zoom).prerotate(total_rotation)
        pix = page.get_pixmap(matrix=mat)

        self.orig_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.orig_img = self._apply_adjustments(self.orig_img)

        self.display_img = self.orig_img.copy()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w > 1 and canvas_h > 1:
            preview_max = (canvas_w, canvas_h)
        else:
            preview_max = self.active_profile["preview_max"]
        self.display_img.thumbnail(preview_max)

        self.scale_x = self.orig_img.width / self.display_img.width
        self.scale_y = self.orig_img.height / self.display_img.height

        self.tk_img = ImageTk.PhotoImage(self.display_img)
        self.canvas.delete("all")

        canvas_w = max(self.canvas.winfo_width(), self.display_img.width)
        canvas_h = max(self.canvas.winfo_height(), self.display_img.height)
        self.image_offset_x = max((canvas_w - self.display_img.width) // 2, 0)
        self.image_offset_y = max((canvas_h - self.display_img.height) // 2, 0)

        self.canvas.create_image(self.image_offset_x, self.image_offset_y, anchor=tk.NW, image=self.tk_img)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))

        self.lbl_page.config(text=f"Página: {self.current_page + 1} / {len(self.doc)}")
        self.highlight_current_thumbnail()
        self.crop_rect = None

        if self.fixed_ratio_crop.get():
            self._place_ratio_rect()

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.rotation = 0
            self.selected_box = None
            self.render_page()

    def next_page(self):
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.rotation = 0
            self.selected_box = None
            self.render_page()

    def rotate_page(self):
        if self.doc:
            self.rotation = (self.rotation + 90) % 360
            self.selected_box = None
            self.render_page()

    # ── Crop logic ──────────────────────────────────────────────────────

    def _near_corner(self, x, y, margin=12):
        """Check if (x, y) is near the bottom-right corner of the ratio rect."""
        if not self._ratio_rect_coords:
            return False
        _, _, rx1, ry1 = self._ratio_rect_coords
        return abs(x - rx1) < margin and abs(y - ry1) < margin

    def on_crop_start(self, event):
        if not self.doc:
            return

        img_x0 = self.image_offset_x
        img_y0 = self.image_offset_y
        img_x1 = img_x0 + self.display_img.width
        img_y1 = img_y0 + self.display_img.height

        if not (img_x0 <= event.x <= img_x1 and img_y0 <= event.y <= img_y1):
            self.crop_start = None
            return

        # Fixed-ratio mode: determine if move or resize
        if self.fixed_ratio_crop.get() and self._ratio_rect_coords:
            self._ratio_drag_start = (event.x, event.y)
            if self._near_corner(event.x, event.y):
                self._ratio_drag_mode = "resize"
            else:
                rx0, ry0, rx1, ry1 = self._ratio_rect_coords
                if rx0 <= event.x <= rx1 and ry0 <= event.y <= ry1:
                    self._ratio_drag_mode = "move"
                else:
                    self._ratio_drag_mode = None
            return

        # Free crop mode
        self.crop_start = (event.x, event.y)
        if self.crop_rect:
            self.canvas.delete(self.crop_rect)
        self.crop_rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)

    def on_crop_drag(self, event):
        # Fixed-ratio mode
        if self.fixed_ratio_crop.get() and self._ratio_drag_start and self._ratio_drag_mode:
            dx = event.x - self._ratio_drag_start[0]
            dy = event.y - self._ratio_drag_start[1]
            self._ratio_drag_start = (event.x, event.y)
            x0, y0, x1, y1 = self._ratio_rect_coords
            img_x0 = self.image_offset_x
            img_y0 = self.image_offset_y
            img_x1 = img_x0 + self.display_img.width
            img_y1 = img_y0 + self.display_img.height

            if self._ratio_drag_mode == "move":
                rw, rh = x1 - x0, y1 - y0
                nx0 = min(max(x0 + dx, img_x0), img_x1 - rw)
                ny0 = min(max(y0 + dy, img_y0), img_y1 - rh)
                self._ratio_rect_coords = (nx0, ny0, nx0 + rw, ny0 + rh)
            elif self._ratio_drag_mode == "resize":
                prof = self.active_profile
                ratio = prof["screen_w"] / prof["screen_h"]
                new_x1 = min(max(x1 + dx, x0 + 20), img_x1)
                new_w = new_x1 - x0
                new_h = int(new_w / ratio)
                if y0 + new_h > img_y1:
                    new_h = img_y1 - y0
                    new_w = int(new_h * ratio)
                self._ratio_rect_coords = (x0, y0, x0 + new_w, y0 + new_h)

            self.canvas.coords(self.crop_rect, *self._ratio_rect_coords)
            self._update_selected_box()
            return

        # Free crop mode
        if self.crop_start:
            x0, y0 = self.crop_start
            min_x = self.image_offset_x
            min_y = self.image_offset_y
            max_x = self.image_offset_x + self.display_img.width
            max_y = self.image_offset_y + self.display_img.height
            clamped_x = min(max(event.x, min_x), max_x)
            clamped_y = min(max(event.y, min_y), max_y)
            self.canvas.coords(self.crop_rect, x0, y0, clamped_x, clamped_y)

    def on_crop_end(self, event):
        # Fixed-ratio mode: just finalize
        if self.fixed_ratio_crop.get() and self._ratio_drag_start:
            self._ratio_drag_start = None
            self._ratio_drag_mode = None
            self._update_selected_box()
            return

        # Free crop mode
        if self.crop_start:
            x0, y0 = self.crop_start
            min_x = self.image_offset_x
            min_y = self.image_offset_y
            max_x = self.image_offset_x + self.display_img.width
            max_y = self.image_offset_y + self.display_img.height
            x1 = min(max(event.x, min_x), max_x)
            y1 = min(max(event.y, min_y), max_y)

            x0_rel = x0 - self.image_offset_x
            y0_rel = y0 - self.image_offset_y
            x1_rel = x1 - self.image_offset_x
            y1_rel = y1 - self.image_offset_y

            self.selected_box = (
                int(min(x0_rel, x1_rel) * self.scale_x),
                int(min(y0_rel, y1_rel) * self.scale_y),
                int(max(x0_rel, x1_rel) * self.scale_x),
                int(max(y0_rel, y1_rel) * self.scale_y)
            )

    # ── Export ──────────────────────────────────────────────────────────

    def save_cropped_page(self):
        if not self.doc:
            return

        if self.selected_box:
            final_img = self.orig_img.crop(self.selected_box)
        else:
            final_img = self.orig_img

        initial_name = ""
        if self.pdf_path:
            base = os.path.splitext(os.path.basename(self.pdf_path))[0]
            initial_name = f"{base}_extracted"

        save_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("Documento PDF", "*.pdf")],
            initialfile=initial_name,
        )
        if save_path:
            final_img.save(save_path, "PDF", resolution=self.active_profile["export_dpi"])
            messagebox.showinfo("Éxito", "¡Partitura para el atril guardada correctamente!")
