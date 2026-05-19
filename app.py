import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import fitz  # PyMuPDF
from PIL import Image, ImageTk, ImageOps

from profiles import (
    DEVICE_PROFILES,
    DEFAULT_PROFILE,
    build_profile,
    save_custom_profiles,
    get_last_profile,
    save_last_profile,
)

THUMB_SIZE = 128


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
            self.doc = fitz.open(file_path)
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
            thumb_img = Image.frombytes("RGB", [thumb_pix.width, thumb_pix.height], thumb_pix.tobytes("ppm"))
            thumb_img = ImageOps.contain(thumb_img, (THUMB_SIZE, THUMB_SIZE))
            bg = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), "white")
            offset = ((THUMB_SIZE - thumb_img.width) // 2, (THUMB_SIZE - thumb_img.height) // 2)
            bg.paste(thumb_img, offset)
            thumb_tk = ImageTk.PhotoImage(bg)
            self.thumb_images.append(thumb_tk)

            tag_name = f"thumb_{i}"
            if i > 0:
                self.thumbs_text.insert(tk.END, "\n")
            start_mark = self.thumbs_text.index("end-1c")
            self.thumbs_text.insert(tk.END, f"  {i + 1}\n")
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

        img_data = pix.tobytes("ppm")
        self.orig_img = Image.frombytes("RGB", [pix.width, pix.height], img_data)

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

        self.crop_start = (event.x, event.y)
        if self.crop_rect:
            self.canvas.delete(self.crop_rect)
        self.crop_rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2)

    def on_crop_drag(self, event):
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

        save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("Documento PDF", "*.pdf")])
        if save_path:
            final_img.save(save_path, "PDF", resolution=self.active_profile["export_dpi"])
            messagebox.showinfo("Éxito", "¡Partitura para el atril guardada correctamente!")
