"""Edición Studio — AudioSplit TTS + CapCut Generator.

Interfaz basada en las vistas de diseño: Inicio, Archivos, Ajustes y Resultado.
Requiere:  pip install customtkinter pillow
"""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

try:
    from PIL import Image, ImageDraw
except ImportError:  # sin Pillow la app funciona, solo sin iconos
    Image = None

from workflow import Options, run, sticker_settings, validate

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

FONT = 'Segoe UI' if sys.platform == 'win32' else 'SF Pro Text' if sys.platform == 'darwin' else 'DejaVu Sans'
try:  # misma fuente para los widgets que no la indican
    ctk.ThemeManager.theme['CTkFont']['family'] = FONT
except Exception:
    pass
MONO = 'Consolas' if sys.platform == 'win32' else 'Menlo' if sys.platform == 'darwin' else 'DejaVu Sans Mono'
CONFIG = Path.home() / '.edicion_studio.json'

# ----------------------------------------------------------------- paleta
BG = '#0e1628'
SIDE = '#0b1222'
CARD = '#141e33'
PANEL = '#18233b'
FIELD = '#1c2842'
BORDER = '#24314d'
FIELD_BORDER = '#2c3a5a'
TEXT = '#e6edf7'
MUTED = '#94a3b8'
DIM = '#5b6b86'
ACCENT = '#2f7cf6'
ACCENT_HOVER = '#1f6ae0'
ACCENT_TINT = '#1b3463'
SOFT = '#243150'
SOFT_HOVER = '#2e3d62'
OK = '#22c55e'
BAD = '#ef4444'
INFO = '#60a5fa'
INFO_BG = '#132a4f'
INFO_BORDER = '#1f3f74'

DOC_TYPES = [('Documentos', '*.txt *.docx')]
AUDIO_TYPES = [('Audios', '*.mp3 *.wav *.m4a *.aac *.flac *.ogg')]
VIDEO_TYPES = [('Videos', '*.mp4 *.webm *.mov *.mkv')]
AUDIO_SUFFIXES = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}

FLOWS = ('combined', 'split', 'capcut')
DEFAULTS = {
    'document': '', 'narration': '', 'document2': '', 'narration2': '',
    'output': '', 'name': 'Proyecto_CapCut',
    'fmt': 'mp3', 'model': 'small', 'margin': '0.08',
    'videos_per_chapter': '4', 'trim': '0.5',
    'sticker_ids': '', 'sticker_interval': '10', 'sticker_duration': '3',
    'generic_video': '', 'generic_audio': '', 'generic_end_video': '', 'generic_end_audio': '',
}

# Etapas que se muestran en "Resultado". workflow.run solo emite mensajes de texto,
# así que una etapa se activa cuando un mensaje contiene alguna de sus palabras
# clave. Ajústalas a los mensajes reales de tu workflow.
STAGES = {
    'combined': [
        ('Transcripción y corte de audios', ()),
        ('Exportación de audios por párrafo', ('export', 'párrafo', 'parrafo', 'guardando')),
        ('Montaje del proyecto de CapCut', ('capcut', 'borrador', 'draft', 'montaje')),
    ],
    'split': [
        ('Transcripción y alineación', ()),
        ('Exportación de audios por párrafo', ('export', 'párrafo', 'parrafo', 'guardando')),
    ],
    'capcut': [
        ('Preparación de audios y videos', ()),
        ('Montaje del proyecto de CapCut', ('capcut', 'borrador', 'draft', 'montaje')),
    ],
}
DONE_TEXT = {
    'combined': 'Los audios se cortaron y se generó el borrador de CapCut correctamente.',
    'split': 'Los audios se cortaron por párrafos y se generaron los reportes de alineación.',
    'capcut': 'Se generó el borrador de CapCut con tus audios y videos.',
}


# ----------------------------------------------------------------- utilidades
_fonts = {}


def F(size=13, bold=False, family=None):
    key = (size, bold, family)
    if key not in _fonts:
        _fonts[key] = ctk.CTkFont(family=family or FONT, size=size, weight='bold' if bold else 'normal')
    return _fonts[key]


def natural_key(path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', Path(path).name)]


def shorten(text, limit=42):
    return text if len(text) <= limit else text[:limit // 2 - 1] + '…' + text[-(limit // 2 - 1):]


def fmt_time(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


def fmt_size(size):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024


# ----------------------------------------------------------------- iconos
def _paint(name, d, s, c):
    """Dibuja un icono en un lienzo de s×s píxeles."""
    w = max(2, round(s * 0.075))
    P = lambda *xs: [v * s for v in xs]
    clear = (0, 0, 0, 0)
    if name == 'scissors':
        r = 0.14
        for cx in (0.3, 0.7):
            d.ellipse(P(cx - r, 0.72 - r, cx + r, 0.72 + r), outline=c, width=w)
        d.line(P(0.38, 0.6, 0.74, 0.07), fill=c, width=w)
        d.line(P(0.62, 0.6, 0.26, 0.07), fill=c, width=w)
    elif name == 'wave':
        heights = [0.22, 0.45, 0.7, 0.92, 0.6, 0.36, 0.78, 0.5, 0.26]
        bw = s * 0.055
        for i, h in enumerate(heights):
            x = s * (0.1 + i * 0.8 / (len(heights) - 1))
            d.rounded_rectangle([x - bw / 2, s * (0.5 - h / 2), x + bw / 2, s * (0.5 + h / 2)], radius=bw / 2, fill=c)
    elif name == 'film':
        d.rounded_rectangle(P(0.08, 0.14, 0.92, 0.86), radius=s * 0.08, outline=c, width=w)
        d.line(P(0.28, 0.14, 0.28, 0.86), fill=c, width=w)
        d.line(P(0.72, 0.14, 0.72, 0.86), fill=c, width=w)
        for y in (0.3, 0.5, 0.7):
            for x in (0.18, 0.82):
                d.rectangle(P(x - 0.035, y - 0.04, x + 0.035, y + 0.04), fill=c)
    elif name == 'home':
        d.line(P(0.1, 0.5, 0.5, 0.14, 0.9, 0.5), fill=c, width=w, joint='curve')
        d.line(P(0.24, 0.42, 0.24, 0.86, 0.76, 0.86, 0.76, 0.42), fill=c, width=w, joint='curve')
        d.line(P(0.43, 0.86, 0.43, 0.62, 0.57, 0.62, 0.57, 0.86), fill=c, width=w)
    elif name == 'headphones':
        d.arc(P(0.14, 0.12, 0.86, 0.84), 180, 360, fill=c, width=w)
        d.line(P(0.14, 0.48, 0.14, 0.62), fill=c, width=w)
        d.line(P(0.86, 0.48, 0.86, 0.62), fill=c, width=w)
        d.rounded_rectangle(P(0.1, 0.52, 0.34, 0.88), radius=s * 0.06, fill=c)
        d.rounded_rectangle(P(0.66, 0.52, 0.9, 0.88), radius=s * 0.06, fill=c)
    elif name == 'layers':
        d.rounded_rectangle(P(0.08, 0.08, 0.62, 0.62), radius=s * 0.07, outline=c, width=w)
        d.rounded_rectangle(P(0.38, 0.38, 0.92, 0.92), radius=s * 0.07, fill=c)
    elif name == 'gear':
        import math
        for k in range(8):
            a = k * math.pi / 4
            d.line([s / 2 + math.cos(a) * s * 0.2, s / 2 + math.sin(a) * s * 0.2,
                    s / 2 + math.cos(a) * s * 0.44, s / 2 + math.sin(a) * s * 0.44], fill=c, width=round(w * 1.7))
        d.ellipse(P(0.2, 0.2, 0.8, 0.8), fill=c)
        d.ellipse(P(0.37, 0.37, 0.63, 0.63), fill=clear)
    elif name == 'info':
        d.ellipse(P(0.08, 0.08, 0.92, 0.92), outline=c, width=w)
        d.ellipse(P(0.44, 0.24, 0.56, 0.36), fill=c)
        d.line(P(0.5, 0.45, 0.5, 0.74), fill=c, width=w)
    elif name == 'check':
        d.ellipse(P(0.02, 0.02, 0.98, 0.98), fill=c)
        d.line(P(0.27, 0.52, 0.43, 0.68, 0.74, 0.36), fill=BG, width=round(w * 1.3), joint='curve')
    elif name == 'cross':
        d.ellipse(P(0.02, 0.02, 0.98, 0.98), fill=c)
        d.line(P(0.33, 0.33, 0.67, 0.67), fill=BG, width=round(w * 1.3))
        d.line(P(0.67, 0.33, 0.33, 0.67), fill=BG, width=round(w * 1.3))
    elif name == 'ring':
        d.ellipse(P(0.1, 0.1, 0.9, 0.9), outline=c, width=round(w * 1.2))
    elif name == 'folder':
        d.polygon(P(0.06, 0.2, 0.38, 0.2, 0.47, 0.31, 0.94, 0.31, 0.94, 0.84, 0.06, 0.84), fill=c)
    elif name == 'file':
        d.line(P(0.22, 0.08, 0.6, 0.08, 0.8, 0.28, 0.8, 0.92, 0.22, 0.92, 0.22, 0.08), fill=c, width=w, joint='curve')
        d.line(P(0.58, 0.08, 0.58, 0.3, 0.8, 0.3), fill=c, width=w)
    elif name == 'bolt':
        d.polygon(P(0.58, 0.04, 0.18, 0.56, 0.46, 0.56, 0.38, 0.96, 0.82, 0.4, 0.53, 0.4), fill=c)
    elif name == 'list':
        for y in (0.26, 0.5, 0.74):
            d.ellipse(P(0.1, y - 0.07, 0.24, y + 0.07), fill=c)
            d.line(P(0.36, y, 0.9, y), fill=c, width=w)
    elif name == 'edit':
        d.line(P(0.62, 0.14, 0.14, 0.14, 0.14, 0.86, 0.86, 0.86, 0.86, 0.4), fill=c, width=w, joint='curve')
        d.line(P(0.42, 0.58, 0.88, 0.12), fill=c, width=round(w * 1.4))
    elif name == 'arrow':
        d.line(P(0.12, 0.5, 0.86, 0.5), fill=c, width=w)
        d.line(P(0.58, 0.22, 0.86, 0.5, 0.58, 0.78), fill=c, width=w, joint='curve')


class Icons:
    def __init__(self):
        self.cache = {}

    def __call__(self, name, size=18, color=TEXT):
        if Image is None:
            return None
        key = (name, size, color)
        if key not in self.cache:
            big = 160
            img = Image.new('RGBA', (big, big), (0, 0, 0, 0))
            if name != 'blank':
                _paint(name, ImageDraw.Draw(img), big, color)
            img = img.resize((size * 2, size * 2), Image.LANCZOS)
            self.cache[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
        return self.cache[key]


icons = Icons()


# ----------------------------------------------------------------- componentes
def soft_button(parent, text, command, width=90, height=38, image=None):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height, corner_radius=8,
                         fg_color=SOFT, hover_color=SOFT_HOVER, text_color=TEXT, font=F(13), image=image,
                         text_color_disabled=DIM)


def accent_button(parent, text, command, width=150, height=44):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height, corner_radius=10,
                         fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color='white', font=F(14, True),
                         text_color_disabled='#a9c4f5')


def field_label(parent, text):
    return ctk.CTkLabel(parent, text=text, text_color=MUTED, font=F(12), anchor='w', height=18)


def card(parent, title, number=None, icon=None, pady=(0, 12)):
    """Tarjeta con encabezado. Devuelve el contenedor del cuerpo."""
    frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
    frame.pack(fill='x', pady=pady, padx=(0, 6))
    head = ctk.CTkFrame(frame, fg_color='transparent')
    head.pack(fill='x', padx=18, pady=(14, 10))
    if icon:
        ctk.CTkLabel(head, text='', image=icons(icon, 22, INFO), width=26).pack(side='left', padx=(0, 10))
    ctk.CTkLabel(head, text=f'{number}.  {title}' if number else title, font=F(16, True), anchor='w').pack(side='left')
    body = ctk.CTkFrame(frame, fg_color='transparent')
    body.pack(fill='x', padx=18, pady=(0, 16))
    body.card = frame
    return body


class StatusLine(ctk.CTkLabel):
    """Línea de estado con icono: ✓ válido, ✕ error, ○ pendiente."""
    STYLE = {'ok': ('check', OK, '✓ '), 'bad': ('cross', BAD, '✕ '), 'muted': ('ring', MUTED, '○ ')}

    def __init__(self, master):
        super().__init__(master, text='', image=icons('blank', 16), compound='left', anchor='w', font=F(12), height=22)

    def set(self, kind, text=''):
        if kind is None:
            self.configure(text='', image=icons('blank', 16))
            return
        icon, color, glyph = self.STYLE[kind]
        image = icons(icon, 16, color)
        self.configure(text=('  ' if image else glyph) + text, text_color=color, image=image)


class Note(ctk.CTkFrame):
    """Nota informativa pequeña o banner destacado."""

    def __init__(self, master, text, banner=False):
        super().__init__(master, fg_color=INFO_BG if banner else 'transparent', corner_radius=10,
                         border_width=1 if banner else 0, border_color=INFO_BORDER)
        self.banner = banner
        self.grid_columnconfigure(1, weight=1)
        size = 20 if banner else 15
        self.icon = ctk.CTkLabel(self, text='' if Image else 'ⓘ', image=icons('info', size, INFO), width=size + 4)
        self.icon.grid(row=0, column=0, sticky='n', padx=(16 if banner else 0, 10), pady=(14 if banner else 2, 14 if banner else 0))
        self.label = ctk.CTkLabel(self, text=text, text_color='#cfe0ff' if banner else MUTED, font=F(13 if banner else 12),
                                  anchor='w', justify='left', wraplength=600)
        self.label.grid(row=0, column=1, sticky='w', padx=(0, 16 if banner else 0), pady=(12 if banner else 0, 12 if banner else 0))
        self.bind('<Configure>', lambda e: self.label.configure(wraplength=max(200, e.width - 70)))

    def set_kind(self, kind):
        color = BAD if kind == 'bad' else INFO
        self.icon.configure(image=icons('info', 15, color))
        self.label.configure(text_color=BAD if kind == 'bad' else MUTED)


class FileField(ctk.CTkFrame):
    """Campo de selección de archivo(s) o carpeta con botón Buscar."""
    PLACEHOLDER = {'file': 'Seleccionar archivo…', 'files': 'Seleccionar archivos…', 'folder': 'Seleccionar carpeta…'}

    def __init__(self, master, label, kind='file', filetypes=None, var=None, on_change=None):
        super().__init__(master, fg_color='transparent')
        self.kind, self.filetypes, self.on_change = kind, filetypes, on_change
        self.var = var if var is not None else tk.StringVar()
        self.paths = ()
        self.enabled = True
        self.grid_columnconfigure(0, weight=1)
        self.label = field_label(self, label)
        self.label.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        self.box = ctk.CTkFrame(self, fg_color=FIELD, border_color=FIELD_BORDER, border_width=1, corner_radius=8, height=38)
        self.box.grid(row=1, column=0, sticky='ew')
        self.box.pack_propagate(False)
        self.text = ctk.CTkLabel(self.box, text='', anchor='w', font=F(13), cursor='hand2')
        self.text.pack(side='left', fill='both', expand=True, padx=(12, 4), pady=2)
        self.clear_btn = ctk.CTkButton(self.box, text='✕', width=24, height=24, corner_radius=6, fg_color='transparent',
                                       hover_color=SOFT, text_color=MUTED, font=F(11), command=self.clear)
        self.button = soft_button(self, 'Buscar', self.choose, width=76)
        self.button.grid(row=1, column=1, padx=(8, 0))
        self.text.bind('<Button-1>', lambda e: self.choose())
        self.var.trace_add('write', lambda *_: self._changed())
        self.refresh()

    def has_value(self):
        return bool(self.paths) if self.kind == 'files' else bool(self.var.get().strip())

    def choose(self):
        if not self.enabled:
            return
        if self.kind == 'folder':
            value = filedialog.askdirectory()
            if value:
                self.var.set(value)
        elif self.kind == 'file':
            value = filedialog.askopenfilename(filetypes=self.filetypes)
            if value:
                self.var.set(value)
        else:
            paths = filedialog.askopenfilenames(filetypes=self.filetypes)
            if paths:
                self.set_paths(paths)

    def set_paths(self, paths):
        self.paths = tuple(sorted(paths, key=natural_key))
        self._changed()

    def clear(self):
        if self.kind == 'files':
            self.set_paths(())
        else:
            self.var.set('')

    def _changed(self):
        self.refresh()
        if self.on_change:
            self.on_change()

    def refresh(self):
        missing = False
        if self.kind == 'files':
            n = len(self.paths)
            text = f'{n} archivo{"s" if n != 1 else ""} seleccionado{"s" if n != 1 else ""}' if n else ''
        else:
            value = self.var.get().strip()
            text = ''
            if value:
                text = shorten(Path(value).name) if self.kind == 'file' else '…' + value[-46:] if len(value) > 48 else value
                missing = not os.path.exists(value)
        self.text.configure(text=text or self.PLACEHOLDER[self.kind], text_color=TEXT if text and self.enabled else DIM)
        self.box.configure(border_color=BAD if missing and self.enabled else FIELD_BORDER)
        if text and self.enabled:
            self.clear_btn.pack(side='right', padx=(0, 6), before=self.text)
        else:
            self.clear_btn.pack_forget()

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self.button.configure(state='normal' if enabled else 'disabled')
        self.label.configure(text_color=MUTED if enabled else DIM)
        self.text.configure(cursor='hand2' if enabled else 'arrow')
        self.refresh()


class NumberField(ctk.CTkFrame):
    """Entrada numérica con flechas ▲▼ (equivalente a un spinbox)."""

    def __init__(self, master, var, lo, hi, step, decimals):
        super().__init__(master, fg_color='transparent')
        self.var, self.lo, self.hi, self.step, self.decimals = var, lo, hi, step, decimals
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(self, textvariable=var, height=38, corner_radius=8, fg_color=FIELD, border_color=FIELD_BORDER,
                     border_width=1, font=F(13)).grid(row=0, column=0, rowspan=2, sticky='ew')
        for row, (glyph, direction) in enumerate((('▲', 1), ('▼', -1))):
            ctk.CTkButton(self, text=glyph, width=26, height=18, corner_radius=4, fg_color=SOFT, hover_color=SOFT_HOVER,
                          font=F(8), text_color=MUTED, command=lambda d=direction: self.bump(d)
                          ).grid(row=row, column=1, padx=(4, 0), pady=(0, 1) if row == 0 else (1, 0))

    def bump(self, direction):
        try:
            value = float(self.var.get().replace(',', '.'))
        except ValueError:
            value = self.lo
        value = round(value + direction * self.step, self.decimals)
        value = max(self.lo, value if self.hi is None else min(self.hi, value))
        self.var.set(f'{value:.{self.decimals}f}' if self.decimals else str(int(value)))


def option_menu(parent, var, values, display=str):
    """CTkOptionMenu que muestra `display(valor)` y guarda el valor real en var."""
    labels = [display(v) for v in values]
    menu = ctk.CTkOptionMenu(parent, values=labels, height=38, corner_radius=8, font=F(13), dropdown_font=F(13),
                             fg_color=FIELD, button_color=FIELD, button_hover_color=SOFT, text_color=TEXT,
                             dropdown_fg_color=PANEL, dropdown_hover_color=SOFT, dropdown_text_color=TEXT,
                             command=lambda label: var.set(values[labels.index(label)]))
    sync = lambda *_: menu.set(display(var.get()) if var.get() in values else labels[0])
    var.trace_add('write', sync)
    sync()
    return menu


# ----------------------------------------------------------------- resultado
class ResultPage(ctk.CTkScrollableFrame):
    def __init__(self, master, flow):
        super().__init__(master, fg_color='transparent')
        self.flow = flow
        self.stages = []
        self.current = -1
        self.running = False
        self.t0 = 0

        head = ctk.CTkFrame(self, fg_color='transparent')
        head.pack(fill='x', pady=(4, 16), padx=(4, 6))
        self.h_icon = ctk.CTkLabel(head, text='', image=icons('info', 44, DIM), width=48)
        self.h_icon.pack(side='left', padx=(0, 16))
        texts = ctk.CTkFrame(head, fg_color='transparent')
        texts.pack(side='left', fill='x', expand=True)
        self.h_title = ctk.CTkLabel(texts, text='Aún no hay resultados', font=F(20, True), anchor='w')
        self.h_title.pack(fill='x')
        self.h_sub = ctk.CTkLabel(texts, text='Completa Archivos y Ajustes, y pulsa Iniciar.', text_color=MUTED,
                                  anchor='w', justify='left', wraplength=640)
        self.h_sub.pack(fill='x')
        texts.bind('<Configure>', lambda e: self.h_sub.configure(wraplength=max(240, e.width - 10)))

        self.stage_card = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        self.bottom = ctk.CTkFrame(self, fg_color='transparent')
        self.bottom.grid_columnconfigure((0, 1), weight=1, uniform='bottom')
        self.log_btn = ctk.CTkButton(self, text='Ver registro  ▾', command=self.toggle_log, width=140, height=32, anchor='w',
                                     fg_color='transparent', hover_color=PANEL, text_color=MUTED, font=F(12))
        self.logbox = ctk.CTkTextbox(self, height=220, state='disabled', wrap='word', corner_radius=12, fg_color='#0a1020',
                                     text_color='#dce6f5', font=F(12, family=MONO), border_width=1, border_color=BORDER)
        self.logbox.tag_config('time', foreground='#6b7a95')
        self.logbox.tag_config('error', foreground='#fca5a5')
        self.logbox.tag_config('done', foreground='#86efac')
        self.log_visible = False

    # -- registro
    def toggle_log(self, show=None):
        self.log_visible = (not self.log_visible) if show is None else show
        if self.log_visible:
            self.logbox.pack(fill='x', pady=(4, 8), padx=(0, 6))
        else:
            self.logbox.pack_forget()
        self.log_btn.configure(text='Ocultar registro  ▴' if self.log_visible else 'Ver registro  ▾')

    def write(self, text, tag=None):
        self.logbox.configure(state='normal')
        self.logbox.insert('end', time.strftime('[%H:%M:%S] '), 'time')
        if tag:
            self.logbox.insert('end', text + '\n', tag)
        else:
            self.logbox.insert('end', text + '\n')
        self.logbox.see('end')
        self.logbox.configure(state='disabled')

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.logbox.get('1.0', 'end').strip())

    # -- etapas
    def start(self, stages):
        for child in self.stage_card.winfo_children():
            child.destroy()
        self.stages = []
        for i, (title, keys) in enumerate(stages):
            row = ctk.CTkFrame(self.stage_card, fg_color='transparent')
            row.pack(fill='x', padx=18, pady=(16 if i == 0 else 6, 16 if i == len(stages) - 1 else 6))
            row.grid_columnconfigure(2, weight=1)
            icon = ctk.CTkLabel(row, text='', image=icons('ring', 22, DIM), width=26)
            icon.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky='n', pady=(2, 0))
            ctk.CTkLabel(row, text=title, font=F(13, True), anchor='w', width=270).grid(row=0, column=1, sticky='w')
            bar = ctk.CTkProgressBar(row, height=6, corner_radius=3, progress_color=FIELD, fg_color=FIELD)
            bar.set(0)
            bar.grid(row=0, column=2, sticky='ew', padx=14)
            clock = ctk.CTkLabel(row, text='--:--', text_color=MUTED, font=F(12), width=64, anchor='e')
            clock.grid(row=0, column=3)
            detail = ctk.CTkLabel(row, text='', text_color=DIM, font=F(11), anchor='w', height=16)
            detail.grid(row=1, column=1, columnspan=3, sticky='w')
            self.stages.append({'keys': keys, 'icon': icon, 'bar': bar, 'clock': clock, 'detail': detail, 'started': None})
        self.h_icon.configure(image=icons('ring', 44, ACCENT))
        self.h_title.configure(text='Procesando tu proyecto…')
        self.h_sub.configure(text='Puedes seguir el avance aquí. No cierres la aplicación.')
        self.stage_card.pack(fill='x', pady=(0, 12), padx=(0, 6), before=self.log_btn if self.log_btn.winfo_ismapped() else None)
        self.bottom.pack_forget()
        if not self.log_btn.winfo_ismapped():
            self.log_btn.pack(anchor='w', pady=(0, 2))
        self.logbox.configure(state='normal')
        self.logbox.delete('1.0', 'end')
        self.logbox.configure(state='disabled')
        self.current = -1
        self.t0 = time.time()
        self.running = True
        self.activate(0)
        self.tick()

    def activate(self, index):
        for j in range(max(self.current, 0), index):
            self.complete(j)
        self.current = index
        stage = self.stages[index]
        stage['started'] = time.time()
        stage['icon'].configure(image=icons('ring', 22, ACCENT))
        stage['bar'].configure(mode='indeterminate', progress_color=ACCENT)
        stage['bar'].start()

    def complete(self, index):
        stage = self.stages[index]
        if stage.get('finished'):
            return
        stage['finished'] = True
        stage['bar'].stop()
        stage['bar'].configure(mode='determinate', progress_color=ACCENT)
        stage['bar'].set(1)
        stage['icon'].configure(image=icons('check', 22, OK))
        stage['detail'].configure(text='')
        if stage['started']:
            stage['clock'].configure(text=fmt_time(time.time() - stage['started']))
        else:
            stage['clock'].configure(text='—')

    def tick(self):
        if not self.running:
            return
        stage = self.stages[self.current]
        stage['clock'].configure(text=fmt_time(time.time() - stage['started']))
        self.h_sub.configure(text=f'Tiempo transcurrido: {fmt_time(time.time() - self.t0)}  ·  No cierres la aplicación.')
        self.after(1000, self.tick)

    def on_log(self, message):
        self.write(message)
        low = message.lower()
        for i in range(self.current + 1, len(self.stages)):
            if any(k in low for k in self.stages[i]['keys']):
                self.activate(i)
                break
        self.stages[self.current]['detail'].configure(text=shorten(message, 96))

    def done(self, dest, stats, files):
        self.running = False
        for i in range(len(self.stages)):
            self.complete(i)
        self.h_icon.configure(image=icons('check', 44, OK))
        self.h_title.configure(text='Proceso completado')
        self.h_sub.configure(text=DONE_TEXT[self.flow.mode])
        self.write('Archivos guardados en: ' + dest, 'done')
        self.build_bottom(stats, files)

    def error(self, message):
        self.running = False
        stage = self.stages[self.current]
        stage['bar'].stop()
        stage['bar'].configure(mode='determinate', progress_color=BAD)
        stage['bar'].set(1)
        stage['icon'].configure(image=icons('cross', 22, BAD))
        stage['detail'].configure(text=shorten(message, 96), text_color=BAD)
        self.h_icon.configure(image=icons('cross', 44, BAD))
        self.h_title.configure(text='No se pudo completar')
        self.h_sub.configure(text=message + '\nSi se creó una carpeta de salida, se conserva para revisión. Usa otro nombre al reintentar.')
        self.write(message, 'error')
        self.toggle_log(True)

    def build_bottom(self, stats, files):
        for child in self.bottom.winfo_children():
            child.destroy()
        left = ctk.CTkFrame(self.bottom, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        ctk.CTkLabel(left, text='Estadísticas', font=F(15, True), anchor='w').pack(fill='x', padx=18, pady=(14, 8))
        for label, value in stats:
            row = ctk.CTkFrame(left, fg_color='transparent')
            row.pack(fill='x', padx=18, pady=2)
            ctk.CTkLabel(row, text=label, text_color=MUTED, anchor='w', font=F(13)).pack(side='left')
            ctk.CTkLabel(row, text=str(value), anchor='e', font=F(13, True)).pack(side='right')
        ctk.CTkFrame(left, height=12, fg_color='transparent').pack()

        right = ctk.CTkFrame(self.bottom, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky='nsew', padx=(6, 6))
        ctk.CTkLabel(right, text='Archivos generados', font=F(15, True), anchor='w').pack(fill='x', padx=18, pady=(14, 8))
        root_name, entries, more = files
        ctk.CTkLabel(right, text='  ' + root_name, image=icons('folder', 16, '#f5b942'), compound='left', anchor='w',
                     font=F(13, True)).pack(fill='x', padx=18, pady=(0, 2))
        for kind, name, info in entries:
            row = ctk.CTkFrame(right, fg_color='transparent')
            row.pack(fill='x', padx=(40, 18), pady=1)
            color = '#f5b942' if kind == 'folder' else MUTED
            ctk.CTkLabel(row, text='  ' + shorten(name, 30), image=icons(kind, 15, color), compound='left', anchor='w',
                         font=F(12)).pack(side='left')
            ctk.CTkLabel(row, text=info, text_color=MUTED, anchor='e', font=F(12)).pack(side='right')
        if more:
            ctk.CTkLabel(right, text=f'… y {more} elementos más', text_color=DIM, anchor='w', font=F(12)).pack(fill='x', padx=40)
        if not entries:
            ctk.CTkLabel(right, text='No se encontraron archivos.', text_color=DIM, anchor='w').pack(fill='x', padx=40)
        ctk.CTkFrame(right, height=12, fg_color='transparent').pack()
        self.bottom.pack(fill='x', pady=(0, 8), before=self.log_btn)


# ----------------------------------------------------------------- flujos
class FlowView(ctk.CTkFrame):
    TABS = ('Archivos', 'Ajustes', 'Resultado')

    def __init__(self, master, app, mode):
        super().__init__(master, fg_color='transparent')
        self.app, self.mode = app, mode
        self.vars = {k: tk.StringVar(value=v) for k, v in DEFAULTS.items()}
        self.part_count = tk.StringVar(value='Una parte')
        self.strict = tk.BooleanVar(value=False)
        self.tab = 0
        self.state = 'empty'  # empty | running | done | error
        self.last_dest = ''
        self.job = {}
        self.videos_field = self.audios_field = None
        self.part_widgets = {}
        self.generic_fields = []
        self.generic_note = None
        self.sticker_note = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.build_tabbar()
        self.pages = [ctk.CTkScrollableFrame(self, fg_color='transparent') for _ in range(2)]
        self.result = ResultPage(self, self)
        self.pages.append(self.result)
        self.build_files(self.pages[0])
        self.build_settings(self.pages[1])
        self.build_footer()
        for var in self.vars.values():
            var.trace_add('write', lambda *_: self.on_inputs())
        self.part_count.trace_add('write', lambda *_: self.on_inputs())
        self.show_tab(0)
        self.on_inputs()

    # -- estructura
    def build_tabbar(self):
        bar = ctk.CTkFrame(self, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)
        bar.grid(row=0, column=0, sticky='ew', pady=(0, 14))
        self.tab_buttons = []
        for i, name in enumerate(self.TABS):
            bar.grid_columnconfigure(i, weight=1, uniform='tabs')
            cell = ctk.CTkFrame(bar, fg_color='transparent')
            cell.grid(row=0, column=i, sticky='ew', padx=6, pady=(6, 4))
            button = ctk.CTkButton(cell, text=name, height=40, corner_radius=8, font=F(14), fg_color='transparent',
                                   hover_color=PANEL, text_color=MUTED, command=lambda i=i: self.show_tab(i))
            button.pack(fill='x')
            line = ctk.CTkFrame(cell, height=3, corner_radius=2, fg_color=CARD)
            line.pack(fill='x', padx=10, pady=(2, 0))
            self.tab_buttons.append((button, line))

    def build_footer(self):
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=2, column=0, sticky='ew', pady=(12, 0))
        footer.grid_columnconfigure(1, weight=1)
        self.btn_back = soft_button(footer, '←  Atrás', self.back, width=170, height=44)
        self.btn_back.grid(row=0, column=0, sticky='w')
        self.hint = ctk.CTkLabel(footer, text='', text_color=MUTED, font=F(12), anchor='e', justify='right')
        self.hint.grid(row=0, column=1, sticky='e', padx=14)
        self.btn_open = soft_button(footer, '  Abrir carpeta', self.open_folder, width=160, height=44, image=icons('folder', 16, TEXT))
        self.btn_open.grid(row=0, column=2, padx=(0, 10))
        self.btn_next = accent_button(footer, 'Siguiente  →', self.next, width=170)
        self.btn_next.grid(row=0, column=3)

    def build_files(self, page):
        n = 0
        if self.mode != 'capcut':
            n += 1
            self.build_parts(page, n)
        if self.mode == 'split':
            Note(page, 'Este flujo solo corta los audios por párrafos y genera reportes de alineación.\n'
                       'No se requieren videos ni se genera un proyecto de CapCut.', banner=True).pack(fill='x', pady=(0, 12), padx=(0, 6))
        if self.mode == 'capcut':
            n += 1
            self.audios_field = self.build_media(page, n, 'Audios existentes', 'Seleccionar audios (MP3, WAV, M4A, AAC, FLAC, OGG)', AUDIO_TYPES, 'audios')
        if self.mode != 'split':
            n += 1
            self.videos_field = self.build_media(page, n, 'Videos principales', 'Seleccionar videos (MP4, WEBM, MOV, MKV)', VIDEO_TYPES, 'videos')
        if self.mode == 'capcut':
            n += 1
            self.build_generic(page, number=n)
        self.build_output(page, n + 1)

    def build_parts(self, page, number):
        body = card(page, 'Partes de narración', number=number)
        radios = ctk.CTkFrame(body, fg_color='transparent')
        radios.pack(fill='x', pady=(0, 12))
        for text in ('Una parte', 'Dos partes'):
            ctk.CTkRadioButton(radios, text=text, variable=self.part_count, value=text, font=F(13), fg_color=ACCENT,
                               hover_color=ACCENT_HOVER, border_color=FIELD_BORDER, radiobutton_width=20,
                               radiobutton_height=20).pack(side='left', padx=(0, 48))
        grid = ctk.CTkFrame(body, fg_color='transparent')
        grid.pack(fill='x')
        grid.grid_columnconfigure((0, 1), weight=1, uniform='parts')
        for i, (title, suffix) in enumerate([('Parte 1', ''), ('Parte 2 (opcional)', '2')]):
            panel = ctk.CTkFrame(grid, fg_color=PANEL, corner_radius=10, border_width=1, border_color=BORDER)
            panel.grid(row=0, column=i, sticky='nsew', padx=(0, 8) if i == 0 else (8, 0))
            heading = ctk.CTkLabel(panel, text=title, font=F(14, True), anchor='w')
            heading.pack(fill='x', padx=14, pady=(12, 8))
            doc = FileField(panel, f'Documento {i + 1} (TXT o DOCX)', 'file', DOC_TYPES, self.vars['document' + suffix])
            doc.pack(fill='x', padx=14, pady=(0, 10))
            audio = FileField(panel, f'Audio {i + 1} (MP3, WAV, M4A, FLAC, OGG, AAC)', 'file', AUDIO_TYPES, self.vars['narration' + suffix])
            audio.pack(fill='x', padx=14, pady=(0, 6))
            status = StatusLine(panel)
            status.pack(fill='x', padx=14, pady=(0, 10))
            self.part_widgets[suffix] = (heading, doc, audio, status)

    def build_media(self, page, number, title, label, types, noun):
        body = card(page, title, number=number)
        field = FileField(body, label, 'files', types, on_change=self.on_inputs)
        field.pack(fill='x')
        ctk.CTkLabel(body, text='Se ordenarán por nombre: 1, 2, 10…', text_color=MUTED, font=F(12), anchor='w').pack(fill='x', pady=(6, 0))
        field.status = StatusLine(body)
        field.status.pack(fill='x', pady=(2, 0))
        field.noun = noun
        return field

    def build_generic(self, page, number=None, icon=None):
        body = card(page, 'Bloques genéricos opcionales', number=number, icon=icon)
        grid = ctk.CTkFrame(body, fg_color='transparent')
        grid.pack(fill='x')
        grid.grid_columnconfigure((0, 1), weight=1, uniform='generic')
        items = [('Video después del capítulo 7', 'generic_video', VIDEO_TYPES), ('Audio después del capítulo 7', 'generic_audio', AUDIO_TYPES),
                 ('Video final', 'generic_end_video', VIDEO_TYPES), ('Audio final', 'generic_end_audio', AUDIO_TYPES)]
        for i, (label, key, types) in enumerate(items):
            field = FileField(grid, label, 'file', types, self.vars[key])
            field.grid(row=i // 2, column=i % 2, sticky='ew', padx=(0, 8) if i % 2 == 0 else (8, 0), pady=(0, 10))
            self.generic_fields.append(field)
        self.generic_note = Note(body, 'Cada bloque es opcional: selecciona su video y audio juntos, o deja ambos vacíos.')
        self.generic_note.pack(fill='x', pady=(2, 0))

    def build_stickers(self, page, icon=None):
        body = card(page, 'Stickers de CapCut', icon=icon)
        field_label(body, 'IDs de stickers (separados por coma)').pack(fill='x', pady=(0, 4))
        ctk.CTkEntry(body, textvariable=self.vars['sticker_ids'], height=38, corner_radius=8, fg_color=FIELD,
                     border_color=FIELD_BORDER, border_width=1, font=F(13)).pack(fill='x')
        row = ctk.CTkFrame(body, fg_color='transparent')
        row.pack(fill='x', pady=(12, 0))
        row.grid_columnconfigure((0, 1), weight=1, uniform='sticker')
        col = ctk.CTkFrame(row, fg_color='transparent')
        col.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        field_label(col, 'Cada cuántos segundos').pack(fill='x', pady=(0, 4))
        NumberField(col, self.vars['sticker_interval'], 0.1, None, 0.5, 1).pack(fill='x')
        col = ctk.CTkFrame(row, fg_color='transparent')
        col.grid(row=0, column=1, sticky='ew', padx=(8, 0))
        field_label(col, 'Duración de cada sticker').pack(fill='x', pady=(0, 4))
        NumberField(col, self.vars['sticker_duration'], 0.1, None, 0.5, 1).pack(fill='x')
        self.sticker_note = Note(body, 'Opcional. Pega IDs de stickers de CapCut; se usan en orden y se repiten cada X segundos. La duración no puede superar el intervalo.')
        self.sticker_note.pack(fill='x', pady=(12, 0))

    def build_output(self, page, number):
        body = card(page, 'Destino', number=number)
        grid = ctk.CTkFrame(body, fg_color='transparent')
        grid.pack(fill='x')
        grid.grid_columnconfigure(0, weight=3)
        grid.grid_columnconfigure(1, weight=2)
        FileField(grid, 'Carpeta de salida', 'folder', var=self.vars['output']).grid(row=0, column=0, sticky='ew', padx=(0, 8))
        name = ctk.CTkFrame(grid, fg_color='transparent')
        name.grid(row=0, column=1, sticky='ew', padx=(8, 0))
        field_label(name, 'Nombre del proyecto').pack(fill='x', pady=(0, 4))
        ctk.CTkEntry(name, textvariable=self.vars['name'], height=38, corner_radius=8, fg_color=FIELD,
                     border_color=FIELD_BORDER, border_width=1, font=F(13)).pack(fill='x')
        self.output_note = Note(body, '')
        self.output_note.pack(fill='x', pady=(10, 0))

    def build_settings(self, page):
        if self.mode != 'capcut':
            body = card(page, 'Ajustes del cortador', icon='headphones')
            row = ctk.CTkFrame(body, fg_color='transparent')
            row.pack(fill='x')
            row.grid_columnconfigure((0, 1, 2), weight=1, uniform='cut')
            col = ctk.CTkFrame(row, fg_color='transparent')
            col.grid(row=0, column=0, sticky='ew', padx=(0, 8))
            field_label(col, 'Formato de salida').pack(fill='x', pady=(0, 4))
            option_menu(col, self.vars['fmt'], ['mp3', 'wav'], str.upper).pack(fill='x')
            col = ctk.CTkFrame(row, fg_color='transparent')
            col.grid(row=0, column=1, sticky='ew', padx=8)
            field_label(col, 'Modelo de transcripción').pack(fill='x', pady=(0, 4))
            option_menu(col, self.vars['model'], ['tiny', 'base', 'small', 'medium']).pack(fill='x')
            col = ctk.CTkFrame(row, fg_color='transparent')
            col.grid(row=0, column=2, sticky='ew', padx=(8, 0))
            field_label(col, 'Margen entre cortes').pack(fill='x', pady=(0, 4))
            inner = ctk.CTkFrame(col, fg_color='transparent')
            inner.pack(fill='x')
            NumberField(inner, self.vars['margin'], 0, 2, 0.01, 2).pack(side='left', fill='x', expand=True)
            ctk.CTkLabel(inner, text='segundos\n(0 - 2)', text_color=MUTED, font=F(11), justify='left').pack(side='left', padx=(8, 0))
            Note(body, 'El margen puede producir una pequeña superposición entre audios consecutivos.').pack(fill='x', pady=(12, 0))

        if self.mode != 'split':
            body = card(page, 'Ajustes del montaje', icon='film')
            row = ctk.CTkFrame(body, fg_color='transparent')
            row.pack(fill='x')
            row.grid_columnconfigure((0, 1), weight=1, uniform='mount')
            col = ctk.CTkFrame(row, fg_color='transparent')
            col.grid(row=0, column=0, sticky='ew', padx=(0, 8))
            field_label(col, 'Videos por capítulo').pack(fill='x', pady=(0, 4))
            NumberField(col, self.vars['videos_per_chapter'], 1, None, 1, 0).pack(fill='x')
            col = ctk.CTkFrame(row, fg_color='transparent')
            col.grid(row=0, column=1, sticky='ew', padx=(8, 0))
            field_label(col, 'Recortar inicio de videos').pack(fill='x', pady=(0, 4))
            inner = ctk.CTkFrame(col, fg_color='transparent')
            inner.pack(fill='x')
            NumberField(inner, self.vars['trim'], 0, None, 0.1, 1).pack(side='left', fill='x', expand=True)
            ctk.CTkLabel(inner, text='segundos (≥ 0)', text_color=MUTED, font=F(11)).pack(side='left', padx=(8, 0))
            ctk.CTkSwitch(body, text='Exigir exactamente 40 capítulos', variable=self.strict, onvalue=True, offvalue=False,
                          progress_color=ACCENT, button_color='#e6edf7', fg_color=SOFT, font=F(13), switch_width=44, switch_height=22
                          ).pack(anchor='w', pady=(16, 2))
            ctk.CTkLabel(body, text='Verifica que el proyecto tenga exactamente 40 capítulos.', text_color=MUTED, font=F(12),
                         anchor='w').pack(fill='x', padx=(54, 0))
            self.build_stickers(page, icon='bolt')

        if self.mode == 'combined':
            self.build_generic(page, icon='layers')

    # -- navegación
    def show_tab(self, index):
        self.tab = index
        for i, page in enumerate(self.pages):
            if i == index:
                page.grid(row=1, column=0, sticky='nsew')
            else:
                page.grid_remove()
        for i, (button, line) in enumerate(self.tab_buttons):
            selected = i == index
            button.configure(fg_color=PANEL if selected else 'transparent', text_color=TEXT if selected else MUTED,
                             font=F(14, selected))
            line.configure(fg_color=ACCENT if selected else CARD)
        self.update_footer()

    def back(self):
        self.show_tab(0 if self.tab == 2 and self.state == 'error' else max(0, self.tab - 1))

    def next(self):
        if self.tab == 0:
            self.show_tab(1)
        elif self.tab == 1:
            if self.state == 'running':
                self.show_tab(2)
            else:
                self.launch()
        elif self.state == 'done':
            self.show_tab(0)
            self.app.show('home')

    def update_footer(self):
        if not hasattr(self, 'btn_next'):
            return
        t, s = self.tab, self.state
        show = lambda widget, visible: widget.grid() if visible else widget.grid_remove()
        show(self.btn_open, t == 2 and s == 'done')
        show(self.btn_back, t == 1 or (t == 2 and s in ('empty', 'error')))
        self.btn_back.configure(text='←  Revisar archivos' if t == 2 and s == 'error' else '←  Atrás')
        show(self.btn_next, t < 2 or s == 'done')
        if t == 0:
            self.btn_next.configure(text='Siguiente  →', state='normal')
        elif t == 1:
            self.btn_next.configure(text='Ver progreso  →' if s == 'running' else 'Iniciar  →', state='normal')
        else:
            self.btn_next.configure(text='Finalizar', state='normal')
        if t < 2 and s != 'running':
            missing = self.missing()
            problem = self.generic_problem() or self.sticker_problem()
            if missing:
                self.hint.configure(text='Falta: ' + ', '.join(missing), text_color=MUTED)
            elif problem:
                self.hint.configure(text='Revisa las opciones marcadas', text_color=BAD)
            else:
                self.hint.configure(text='✓ Todo listo · Ctrl+Enter para iniciar', text_color=OK)
        elif s == 'running':
            self.hint.configure(text='Proceso en marcha…', text_color=INFO)
        else:
            self.hint.configure(text='')

    # -- validación en vivo
    def missing(self):
        v = {k: x.get().strip() for k, x in self.vars.items()}
        result = []
        if self.mode != 'capcut':
            parts = [('', 1)] + ([('2', 2)] if self.part_count.get() == 'Dos partes' else [])
            for suffix, n in parts:
                if not v['document' + suffix]:
                    result.append(f'documento {n}')
                if not v['narration' + suffix]:
                    result.append(f'audio {n}')
        if self.audios_field and not self.audios_field.paths:
            result.append('audios')
        if self.videos_field and not self.videos_field.paths:
            result.append('videos')
        if not v['output'] and not self.app.settings.get('default_output'):
            result.append('carpeta de salida')
        return result

    def generic_problem(self):
        if not self.generic_fields:
            return None
        values = [field.has_value() for field in self.generic_fields]
        if any(values[:2]) and not all(values[:2]):
            return 'Completa el video y el audio del bloque tras el capítulo 7, o deja ambos vacíos.'
        if any(values[2:]) and not all(values[2:]):
            return 'Completa el video y el audio del bloque final, o deja ambos vacíos.'
        return None

    def sticker_problem(self):
        if not self.sticker_note:
            return None
        try:
            sticker_settings(self.vars['sticker_ids'].get(), self.vars['sticker_interval'].get(),
                             self.vars['sticker_duration'].get())
        except ValueError as exc:
            return str(exc)
        return None

    def on_inputs(self):
        if not hasattr(self, 'btn_next'):
            return
        two = self.part_count.get() == 'Dos partes'
        for suffix, (heading, doc, audio, status) in self.part_widgets.items():
            enabled = suffix == '' or two
            doc.set_enabled(enabled)
            audio.set_enabled(enabled)
            heading.configure(text_color=TEXT if enabled else DIM)
            d = self.vars['document' + suffix].get().strip()
            a = self.vars['narration' + suffix].get().strip()
            if not enabled or (not d and not a):
                status.set(None)
            elif (d and not os.path.isfile(d)) or (a and not os.path.isfile(a)):
                status.set('bad', 'Archivo no encontrado')
            elif d and a:
                status.set('ok', 'Archivos válidos')
            else:
                status.set('muted', 'Falta el audio' if d else 'Falta el documento')
        for field in (self.videos_field, self.audios_field):
            if field:
                n = len(field.paths)
                field.status.set('ok', f'{n} {field.noun} listos' if n != 1 else f'1 {field.noun[:-1]} listo') if n else field.status.set(None)
        if self.generic_note:
            problem = self.generic_problem()
            self.generic_note.set_kind('bad' if problem else 'info')
            self.generic_note.label.configure(
                text=problem or 'Cada bloque es opcional: selecciona su video y audio juntos, o deja ambos vacíos.')
        if self.sticker_note:
            problem = self.sticker_problem()
            self.sticker_note.set_kind('bad' if problem else 'info')
            self.sticker_note.label.configure(
                text=problem or 'Opcional. Pega IDs de stickers de CapCut; se usan en orden y se repiten cada X segundos. La duración no puede superar el intervalo.')
        default = self.app.settings.get('default_output', '')
        if self.vars['output'].get().strip() or not default:
            self.output_note.label.configure(text='Se creará una carpeta con el nombre del proyecto.')
        else:
            self.output_note.label.configure(text=f'Sin carpeta: se usará la predeterminada ({shorten(default, 50)}).')
        self.update_footer()

    # -- proceso
    def collect(self):
        values = {k: v.get().strip() for k, v in self.vars.items()}
        if self.mode == 'capcut' or self.part_count.get() == 'Una parte':
            values['document2'] = ''
            values['narration2'] = ''
        elif not (values['document2'] and values['narration2']):
            raise ValueError('En Dos partes, carga el documento y el audio de la Parte 2.')
        if not values['output']:
            values['output'] = self.app.settings.get('default_output', '')
        generic = {k: values.pop(k) for k in list(values) if k.startswith('generic_')}
        sticker_ids, sticker_interval, sticker_duration = sticker_settings(
            values.pop('sticker_ids'), values['sticker_interval'], values['sticker_duration'])
        values['sticker_interval'] = sticker_interval
        values['sticker_duration'] = sticker_duration
        for key in ('margin', 'trim'):
            values[key] = float(values[key].replace(',', '.'))
        values['videos_per_chapter'] = int(values['videos_per_chapter'])
        videos = self.videos_field.paths if self.videos_field else ()
        audios = self.audios_field.paths if self.audios_field else ()
        self.job = {'two': bool(values['document2']), 'videos': len(videos), 'audios': len(audios),
                    'vpc': values['videos_per_chapter'], 'stickers': len(sticker_ids)}
        return Options(**values, generic=generic, sticker_ids=tuple(sticker_ids), mode=self.mode, videos=videos,
                       audios=audios, strict=self.strict.get())

    def launch(self):
        if self.app.busy:
            messagebox.showinfo('Proceso en marcha', 'Ya hay un proceso en ejecución. Espera a que termine.')
            return
        try:
            options = self.collect()
            validate(options)
        except Exception as exc:
            messagebox.showerror('Revisa los datos', str(exc))
            return
        self.app.save_config()
        self.state = 'running'
        self.job['start'] = time.time()
        self.result.start(STAGES[self.mode])
        self.show_tab(2)
        self.app.start_job(self, options)

    def on_log(self, message):
        self.result.on_log(message)

    def on_done(self, dest):
        self.state = 'done'
        self.last_dest = dest
        self.result.done(dest, self.stats(dest), self.scan(dest))
        self.show_tab(2)

    def on_error(self, message):
        self.state = 'error'
        self.result.error(message)
        self.show_tab(2)

    @staticmethod
    def root_of(dest):
        root = Path(dest)
        return root.parent if root.is_file() else root

    def stats(self, dest):
        root = self.root_of(dest)
        try:
            files = [p for p in root.rglob('*') if p.is_file()]
        except OSError:
            files = []
        audio_count = sum(p.suffix.lower() in AUDIO_SUFFIXES for p in files)
        rows = []
        if self.mode != 'capcut':
            rows += [('Partes de narración', 2 if self.job.get('two') else 1), ('Audios generados', audio_count)]
        if self.mode == 'capcut':
            rows.append(('Audios utilizados', self.job.get('audios', 0)))
        if self.mode != 'split':
            rows += [('Videos utilizados', self.job.get('videos', 0)), ('Videos por capítulo', self.job.get('vpc', 0))]
            if self.job.get('stickers'):
                rows.append(('Stickers configurados', self.job['stickers']))
        rows += [('Archivos en la salida', len(files)), ('Tiempo de proceso', fmt_time(time.time() - self.job.get('start', time.time())))]
        return rows

    def scan(self, dest, limit=8):
        root = self.root_of(dest)
        try:
            items = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), natural_key(p)))
        except OSError:
            return root.name + '/', [], 0
        entries = []
        for p in items[:limit]:
            if p.is_dir():
                count = sum(1 for q in p.rglob('*') if q.is_file())
                entries.append(('folder', p.name + '/', f'{count} archivo{"s" if count != 1 else ""}'))
            else:
                entries.append(('file', p.name, fmt_size(p.stat().st_size)))
        return root.name + '/', entries, max(0, len(items) - limit)

    def open_folder(self):
        if not self.last_dest:
            return
        target = self.root_of(self.last_dest)
        try:
            if sys.platform == 'win32':
                os.startfile(target)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(target)])
            else:
                subprocess.Popen(['xdg-open', str(target)])
        except Exception as exc:
            messagebox.showerror('No se pudo abrir la carpeta', str(exc))

    # -- persistencia
    def dump(self):
        data = {'vars': {k: v.get() for k, v in self.vars.items()}, 'part_count': self.part_count.get(), 'strict': self.strict.get()}
        if self.app.settings.get('remember_files'):
            data['videos'] = list(self.videos_field.paths) if self.videos_field else []
            data['audios'] = list(self.audios_field.paths) if self.audios_field else []
        return data

    def load(self, data):
        for key, value in data.get('vars', {}).items():
            if key in self.vars and isinstance(value, str):
                self.vars[key].set(value)
        if data.get('part_count') in ('Una parte', 'Dos partes'):
            self.part_count.set(data['part_count'])
        self.strict.set(bool(data.get('strict', False)))
        if self.app.settings.get('remember_files'):
            for field, key in ((self.videos_field, 'videos'), (self.audios_field, 'audios')):
                if field and data.get(key):
                    field.set_paths([p for p in data[key] if os.path.exists(p)])
        self.on_inputs()


# ----------------------------------------------------------------- otras vistas
class HomeView(ctk.CTkFrame):
    CARDS = [
        ('combined', 'scissors', 'Cortar audio y generar CapCut', 'Corta la narración por párrafos y genera un borrador de CapCut en un solo flujo.'),
        ('split', 'wave', 'Solo cortar audio', 'Genera audios por párrafo y reportes de alineación.'),
        ('capcut', 'film', 'Generar CapCut\ncon audios existentes', 'Usa audios ya divididos para crear un borrador de CapCut.'),
    ]
    FEATURES = [
        ('bolt', 'Eficiente', 'Automatiza el proceso en pocos pasos.'),
        ('list', 'Organizado', 'Mantén el orden de tus capítulos y videos.'),
        ('edit', 'Listo para editar', 'Genera un proyecto de CapCut listo para personalizar.'),
    ]

    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        band = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        band.pack(fill='x', pady=(0, 28), padx=(0, 6))
        ctk.CTkLabel(band, text='Edición Studio', font=F(18, True), anchor='w').pack(fill='x', padx=22, pady=(14, 0))
        ctk.CTkLabel(band, text='Corta narraciones por párrafos y genera proyectos de CapCut', text_color=MUTED,
                     anchor='w').pack(fill='x', padx=22, pady=(0, 14))

        ctk.CTkLabel(self, text='Bienvenido a Edición Studio', font=F(28, True), anchor='w').pack(fill='x', padx=4)
        ctk.CTkLabel(self, text='Organiza tus narraciones y crea borradores de CapCut fácilmente.', text_color=MUTED,
                     font=F(14), anchor='w').pack(fill='x', padx=4, pady=(4, 22))

        row = ctk.CTkFrame(self, fg_color='transparent')
        row.pack(fill='x', padx=(0, 6))
        row.grid_columnconfigure((0, 1, 2), weight=1, uniform='home')
        self.cards = []
        for i, (mode, icon, title, desc) in enumerate(self.CARDS):
            c = ctk.CTkFrame(row, fg_color=CARD, corner_radius=16, border_width=2, border_color=BORDER)
            c.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 8, 0 if i == 2 else 8))
            ic = ctk.CTkLabel(c, text='', image=icons(icon, 60, ACCENT), cursor='hand2')
            ic.pack(pady=(30, 14))
            t = ctk.CTkLabel(c, text=title, font=F(15, True), justify='center', cursor='hand2')
            t.pack(padx=16)
            b = ctk.CTkButton(c, text='Iniciar', width=130, height=40, corner_radius=8, fg_color=SOFT, hover_color=ACCENT_HOVER,
                              font=F(13, True), command=lambda m=mode: app.show(m))
            b.pack(side='bottom', pady=(0, 26))
            d = ctk.CTkLabel(c, text=desc, text_color=MUTED, font=F(12), justify='center', wraplength=210, cursor='hand2')
            d.pack(padx=16, pady=(10, 20))
            c.bind('<Configure>', lambda e, d=d: d.configure(wraplength=max(140, e.width - 50)))
            for w in (c, ic, t, d, b):
                w.bind('<Enter>', lambda e, i=i: self.highlight(i), add='+')
            for w in (ic, t, d):
                w.bind('<Button-1>', lambda e, m=mode: app.show(m))
            self.cards.append((c, b))
        self.highlight(0)

        feats = ctk.CTkFrame(self, fg_color=CARD, corner_radius=14, border_width=1, border_color=BORDER)
        feats.pack(fill='x', pady=(28, 4), padx=(0, 6))
        for i, (icon, title, desc) in enumerate(self.FEATURES):
            feats.grid_columnconfigure(i * 2, weight=1, uniform='feat')
            if i:
                ctk.CTkFrame(feats, width=1, height=1, fg_color=BORDER).grid(row=0, column=i * 2 - 1, sticky='ns', pady=18)
            cell = ctk.CTkFrame(feats, fg_color='transparent')
            cell.grid(row=0, column=i * 2, sticky='nsew', padx=20, pady=20)
            cell.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(cell, text='', image=icons(icon, 20, INFO), fg_color=ACCENT_TINT, corner_radius=10, width=40,
                         height=40).grid(row=0, column=0, rowspan=2, sticky='n', padx=(0, 12))
            ctk.CTkLabel(cell, text=title, font=F(14, True), anchor='w').grid(row=0, column=1, sticky='w')
            desc_label = ctk.CTkLabel(cell, text=desc, text_color=MUTED, font=F(12), anchor='w', justify='left', wraplength=200)
            desc_label.grid(row=1, column=1, sticky='w')
            cell.bind('<Configure>', lambda e, l=desc_label: l.configure(wraplength=max(120, e.width - 60)))

    def highlight(self, index):
        for j, (c, b) in enumerate(self.cards):
            c.configure(border_color=ACCENT if j == index else BORDER)
            b.configure(fg_color=ACCENT if j == index else SOFT)


class ConfigView(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        self.app = app
        ctk.CTkLabel(self, text='Configuración', font=F(26, True), anchor='w').pack(fill='x', padx=4)
        ctk.CTkLabel(self, text='Preferencias generales de Edición Studio.', text_color=MUTED, anchor='w').pack(fill='x', padx=4, pady=(4, 20))
        body = card(self, 'Preferencias', icon='gear')
        self.default_output = tk.StringVar()
        FileField(body, 'Carpeta de salida predeterminada', 'folder', var=self.default_output, on_change=self.changed).pack(fill='x')
        Note(body, 'Se usa en cualquier flujo que no tenga carpeta de salida.').pack(fill='x', pady=(8, 14))
        self.remember = tk.BooleanVar()
        ctk.CTkSwitch(body, text='Recordar videos y audios seleccionados entre sesiones', variable=self.remember, onvalue=True,
                      offvalue=False, command=self.changed, progress_color=ACCENT, button_color='#e6edf7', fg_color=SOFT,
                      font=F(13)).pack(anchor='w')
        body = card(self, 'Datos guardados', icon='info')
        ctk.CTkLabel(body, text=f'Tus ajustes se guardan en:\n{CONFIG}', text_color=MUTED, justify='left', anchor='w').pack(fill='x')
        soft_button(body, 'Restablecer configuración', self.reset, width=210).pack(anchor='w', pady=(12, 0))

    def sync(self):
        self.default_output.set(self.app.settings.get('default_output', ''))
        self.remember.set(bool(self.app.settings.get('remember_files')))

    def changed(self):
        self.app.settings['default_output'] = self.default_output.get().strip()
        self.app.settings['remember_files'] = bool(self.remember.get())
        for mode in FLOWS:
            self.app.views[mode].on_inputs()

    def reset(self):
        if not messagebox.askyesno('Restablecer', '¿Borrar la configuración guardada? Se aplicará al reiniciar la aplicación.'):
            return
        try:
            CONFIG.unlink(missing_ok=True)
        except OSError as exc:
            messagebox.showerror('No se pudo borrar', str(exc))
            return
        self.app.skip_save = True
        messagebox.showinfo('Listo', 'Configuración borrada. Reinicia la aplicación para empezar desde cero.')


class AboutView(ctk.CTkScrollableFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color='transparent')
        box = ctk.CTkFrame(self, fg_color=CARD, corner_radius=16, border_width=1, border_color=BORDER)
        box.pack(fill='x', padx=(0, 6), pady=(20, 0))
        ctk.CTkLabel(box, text='', image=icons('scissors', 64, ACCENT)).pack(pady=(32, 12))
        ctk.CTkLabel(box, text='Edición Studio', font=F(24, True)).pack()
        ctk.CTkLabel(box, text='AudioSplit TTS + CapCut Generator', text_color=MUTED, font=F(14)).pack(pady=(2, 18))
        ctk.CTkLabel(box, text='Corta narraciones por párrafos usando su documento como guía y monta\n'
                               'borradores de CapCut con tus videos, en un solo flujo.', justify='center').pack(padx=24)
        Note(box, 'El borrador de CapCut es experimental: revísalo antes de publicar.', banner=True).pack(padx=40, pady=(22, 32))


# ----------------------------------------------------------------- aplicación
class App(ctk.CTk):
    NAV = [('home', 'Inicio', 'home'), ('split', 'Cortar audio', 'headphones'), ('capcut', 'Generar CapCut', 'film'),
           ('combined', 'Corte + CapCut', 'layers')]
    NAV_BOTTOM = [('config', 'Configuración', 'gear'), ('about', 'Acerca de', 'info')]

    def __init__(self):
        super().__init__(fg_color=BG)
        self.title('Edición Studio — AudioSplit + CapCut')
        self.geometry('1200x840')
        self.minsize(1040, 760)
        self.settings = {'default_output': '', 'remember_files': False}
        self.events = queue.Queue()
        self.busy = False
        self.skip_save = False
        self.job_flow = None
        self.current = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        content = ctk.CTkFrame(self, fg_color='transparent')
        content.grid(row=0, column=1, sticky='nsew', padx=26, pady=22)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)
        self.views = {'home': HomeView(content, self)}
        for mode in FLOWS:
            self.views[mode] = FlowView(content, self, mode)
        self.views['config'] = ConfigView(content, self)
        self.views['about'] = AboutView(content, self)

        self.load_config()
        self.views['config'].sync()
        self.show('home')
        self.bind_all('<Control-Return>', self.shortcut_next)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def build_sidebar(self):
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=SIDE)
        side.grid(row=0, column=0, sticky='ns')
        side.pack_propagate(False)
        ctk.CTkLabel(side, text='' if Image else '✂', image=icons('scissors', 40, ACCENT), font=F(32)).pack(pady=(28, 6))
        ctk.CTkLabel(side, text='Edición Studio', font=F(16, True)).pack(pady=(0, 26))
        self.nav = {}
        for key, label, icon in self.NAV:
            self.nav[key] = self.nav_button(side, key, label, icon)
            self.nav[key].pack(fill='x', padx=12, pady=2)
        for key, label, icon in reversed(self.NAV_BOTTOM):
            self.nav[key] = self.nav_button(side, key, label, icon)
            self.nav[key].pack(side='bottom', fill='x', padx=12, pady=(2, 20 if key == 'about' else 2))
        self.busy_pill = ctk.CTkButton(side, text='●  Proceso en marcha', height=32, corner_radius=16, fg_color=ACCENT_TINT,
                                       hover_color=SOFT, text_color=INFO, font=F(12, True), command=self.show_running)

    def nav_button(self, parent, key, label, icon):
        button = ctk.CTkButton(parent, text='  ' + label, image=icons(icon, 18, MUTED), compound='left', anchor='w',
                               height=42, corner_radius=10, fg_color='transparent', hover_color=PANEL, text_color=MUTED,
                               font=F(13), command=lambda: self.show(key))
        button.icon_name = icon
        return button

    def show(self, key):
        self.current = key
        for name, view in self.views.items():
            if name == key:
                view.grid(row=0, column=0, sticky='nsew')
            else:
                view.grid_remove()
        for name, button in self.nav.items():
            selected = name == key
            button.configure(fg_color=ACCENT_TINT if selected else 'transparent', text_color='white' if selected else MUTED,
                             image=icons(button.icon_name, 18, '#ffffff' if selected else MUTED), font=F(13, selected))

    def show_running(self):
        if self.job_flow:
            self.show(self.job_flow.mode)
            self.job_flow.show_tab(2)

    def shortcut_next(self, _event=None):
        view = self.views.get(self.current)
        if isinstance(view, FlowView) and view.tab < 2:
            view.next()

    # -- trabajo en segundo plano
    def start_job(self, flow, options):
        self.busy = True
        self.job_flow = flow
        self.busy_pill.pack(side='bottom', fill='x', padx=16, pady=(0, 14), after=self.nav['config'])

        def worker():
            try:
                dest = run(options, lambda msg: self.events.put(('log', msg)))
                self.events.put(('done', str(dest)))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                flow = self.job_flow
                if kind == 'log':
                    flow.on_log(value)
                    continue
                self.busy = False
                self.busy_pill.pack_forget()
                if kind == 'done':
                    flow.on_done(value)
                else:
                    flow.on_error(value)
                if self.current != flow.mode:
                    self.bell()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    # -- persistencia
    def load_config(self):
        try:
            data = json.loads(CONFIG.read_text('utf-8'))
        except Exception:
            return
        self.settings.update({k: v for k, v in data.get('settings', {}).items() if k in self.settings})
        flows = data.get('flows')
        if flows is None and 'vars' in data:  # formato de la versión anterior
            flows = {mode: data for mode in FLOWS}
        for mode in FLOWS:
            self.views[mode].load((flows or {}).get(mode, {}))

    def save_config(self):
        if self.skip_save:
            return
        data = {'settings': self.settings, 'flows': {mode: self.views[mode].dump() for mode in FLOWS}}
        try:
            CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
        except OSError:
            pass

    def close(self):
        if self.busy:
            messagebox.showinfo('Proceso en marcha', 'Espera a que termine el procesamiento antes de cerrar.')
            return
        self.save_config()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
