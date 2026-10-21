#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shadow of the Colossus launcher for Linux (GTK4/libadwaita).

Replaces the Tkinter launcher (sotc_launcher_win.py) on Linux: game folder and saves, modes,
display and diagnostics, all written to the environment that run-portable.sh/sotc.py read.
Settings live in $XDG_CONFIG_HOME/sotc-launcher/settings.json.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

APP_DIR = Path(__file__).resolve().parent
PORT_DIR = APP_DIR.parent
sys.path.insert(0, str(PORT_DIR / 'scripts'))
sys.path.insert(0, str(APP_DIR))
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'sotc-launcher'
CONFIG_FILE = CONFIG_DIR / 'settings.json'
GAME_ID, GAME_VERSION = 'CUSA08809', '01.01'
SYS_MODULES = ('libSceUlt.sprx', 'libSceNgs2.sprx')
ICON = APP_DIR / 'sotc.png'
MAX_LOG_LINES = 6000

NAV = [('play', 'Jogar'), ('game', 'Jogo e saves'), ('graphics', 'Imagem e FPS'),
       ('controls', 'Controles'), ('advanced', 'Avançado'), ('log', 'Registro')]

OUTPUTS = [('1280x720', '1280 × 720 (720p)'), ('1920x1080', '1920 × 1080 (1080p)'),
           ('2560x1440', '2560 × 1440 (1440p)'), ('3840x2160', '3840 × 2160 (4K)')]
UPSCALERS = [('fsr1', 'FSR 1 (AMD, qualquer placa)'), ('bilinear', 'Bilinear (simples)')]
SHARPNESS = [('0', 'Alta'), ('250', 'Média (padrão)'), ('600', 'Baixa'), ('off', 'Desligada')]
MOUSE_SENS = [('0.5', '0,5 (lenta)'), ('0.75', '0,75'), ('1.0', '1,0 (padrão)'),
              ('1.5', '1,5'), ('2.0', '2,0 (rápida)')]
PRESENT_MODES = [('Mailbox', 'Mailbox (baixa latência, sem cortes)'), ('Fifo', 'FIFO (VSync)'),
                 ('Immediate', 'Immediate (pode cortar a imagem)')]
LANGUAGES = [('', 'Automático (o do jogo)'), ('7', 'Português (Portugal)'),
             ('15', 'Português (Brasil)'), ('1', 'Inglês'), ('3', 'Espanhol'),
             ('2', 'Francês'), ('4', 'Alemão'), ('5', 'Italiano'), ('0', 'Japonês')]
READBACKS = [('', 'Precisas (padrão; o jogo precisa)'), ('1', 'Relaxadas (pode travar)')]
GPU_SUBMIT = [('auto', 'Automático (ligado em NVIDIA)'),
              ('on', 'Ligado em qualquer placa (AMD/Intel: experimental)'), ('off', 'Desligado')]
FRAMEGEN = [('off', 'Desligada (F8 liga no jogo)'), ('fsr', 'FSR 3 (ligada ao iniciar)'),
            ('auto', 'Automática')]
EFFECTS = [('fx_vignette', 'Vinheta (cantos escurecidos)', 'r_vignetteOverrideEnable=1 r_vignetteEnable=0'),
           ('fx_fog', 'Névoa atmosférica', 'fog_enable=0'),
           ('fx_ssao', 'Oclusão ambiente (SSAO)', 'AO_Mode=0')]

KEY_INPUTS = [
    ('move_up', 'W', 'Andar para frente'), ('move_down', 'S', 'Andar para trás'),
    ('move_left', 'A', 'Andar para a esquerda'), ('move_right', 'D', 'Andar para a direita'),
    ('look_up', 'Up', 'Câmera para cima'), ('look_down', 'Down', 'Câmera para baixo'),
    ('look_left', 'Left', 'Câmera para a esquerda'), ('look_right', 'Right', 'Câmera para a direita'),
    ('cross', 'Space', '✕'), ('circle', 'Left Shift', '○'), ('square', 'E', '□'),
    ('triangle', 'Q', '△'), ('l1', '1', 'L1'), ('r1', '3', 'R1'), ('l2', 'R', 'L2'),
    ('r2', 'F', 'R2'), ('l3', 'Z', 'L3'), ('r3', 'C', 'R3'),
    ('options', 'Return', 'Options'), ('touchpad', 'Tab', 'Touchpad (esquerda)'),
    ('touchpad_right', 'Backspace', 'Touchpad (direita)'),
    ('up', 'I', 'Direcional ↑'), ('down', 'K', 'Direcional ↓'),
    ('left', 'J', 'Direcional ←'), ('right', 'L', 'Direcional →'),
]

DEFAULTS = {
    'game_dir': str(PORT_DIR.parent / GAME_ID), 'sys_modules': '', 'dlc_dir': '',
    'user_dir': str(PORT_DIR / 'user'), 'af16': True, 'fps60': False, 'fps_unlocked': False,
    'fullscreen': False, 'present_mode': 'Mailbox', 'language': '', 'player_name': '',
    'show_fps': False, 'readbacks': '', 'extra_env': '', 'gamepad': '',
    'output_res': '1920x1080', 'upscaler': 'fsr1', 'sharpness': '250', 'mouse': True,
    'mouse_sens': '1.0', 'mouse_invert': False, 'neo': False, 'fx_vignette': True,
    'fx_fog': True, 'fx_ssao': True, 'engine_cvars': '', 'perf_culling': True,
    'perf_record_thread': True, 'perf_fastbind': True, 'perf_dma': True, 'dma_auto': True, 'gpu_submit': 'auto', 'keys': {},
    'framegen': 'off', 'mangohud': True, 'profile': False, 'rebuild_on_play': False,
}

CSS = """
window { background-color: #0d0f10; color: #e6e2da; }
.sidebar { background-color: #090b0d; padding: 16px 10px; }
.brand { font-family: Georgia, "Noto Serif", serif; font-size: 18px; color: #f2ead9; }
.brand-sub { font-size: 10px; letter-spacing: 2px; color: #8f9499; }
.nav { background: transparent; }
.nav row { border-radius: 8px; margin: 2px 0; }
.nav row:hover { background-color: #14181c; }
.nav row:selected { background-color: #1d2227; }
.nav label { padding: 9px 12px; color: #c9c4ba; }
.nav row:selected label { color: #f2ead9; }
.page-title { font-family: Georgia, "Noto Serif", serif; font-size: 26px; color: #f2ead9; }
.section { font-family: Georgia, "Noto Serif", serif; font-size: 17px; color: #d7c08a; margin-top: 10px; }
.muted { color: #8f9499; font-size: 12px; }
.small { font-size: 11px; }
.banner-title { font-family: Georgia, "Noto Serif", serif; font-size: 32px; color: #f2ead9; }
.banner-sub { font-size: 12px; color: #d7c08a; }
.banner { background-color: #14171a; }
.banner-shade { background-image: linear-gradient(to bottom, rgba(13,15,16,0), rgba(13,15,16,0.55) 55%, rgba(13,15,16,0.96)); padding: 20px 26px; }
.card { background-color: #14171a; border: 1px solid #242a2f; border-radius: 10px; padding: 14px 16px; }
.check-ok { color: #9fbf8f; }
.check-warn { color: #d9b441; }
.check-bad { color: #d36b5c; }
.check-info { color: #8f9499; }
.entry, entry { background-color: #101317; color: #e6e2da; border: 1px solid #2a3036; border-radius: 6px; padding: 6px 8px; }
entry:focus { border-color: #4f7790; }
button { border-radius: 7px; }
button.play { background-color: #3e5f73; color: #ffffff; font-weight: bold; padding: 9px 30px; }
button.play:hover { background-color: #4f7790; }
button.play:disabled { background-color: #242a2f; color: #6f757a; }
button.stop { background-color: #3a2426; color: #e0a0a0; padding: 8px 18px; }
button.stop:hover { background-color: #4a2c2e; }
button.stop:disabled { background-color: #1b1f23; color: #5a5f64; }
.log { font-family: monospace; font-size: 11px; background-color: #090a0b; color: #c9ccd0; }
"""


def _(text):
    return text


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def ini_values():
    values = {}
    try:
        for line in (PORT_DIR / 'sotc.ini').read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip()
    except OSError:
        pass
    return values


def load_settings():
    raw = load_json(CONFIG_FILE, {})
    settings = {**DEFAULTS, **raw}
    ini = ini_values()
    if 'game_dir' not in raw and ini.get('SOTC_GAME_DIR'):
        settings['game_dir'] = ini['SOTC_GAME_DIR']
    if not Path(settings['game_dir']).is_dir() and Path(ini.get('SOTC_GAME_DIR', '')).is_dir():
        settings['game_dir'] = ini['SOTC_GAME_DIR']
    if not settings.get('dlc_dir') and ini.get('SOTC_DLC_DIR'):
        settings['dlc_dir'] = ini['SOTC_DLC_DIR']
    if not settings.get('sys_modules') and ini.get('SOTC_SYS_MODULES'):
        settings['sys_modules'] = ini['SOTC_SYS_MODULES']
    return settings


_EBOOT_CACHE = {}


def eboot_version(eboot):
    try:
        stat = eboot.stat()
    except OSError:
        return None
    key = (str(eboot), stat.st_size, stat.st_mtime_ns)
    if key not in _EBOOT_CACHE:
        try:
            from prepare import parse_self
            from sotc_modes import is_supported
            elf, _h, ph, _s, _m = parse_self(eboot.read_bytes())
            _EBOOT_CACHE[key] = GAME_VERSION if is_supported(elf, ph) else None
        except (OSError, ValueError, ImportError):
            _EBOOT_CACHE[key] = None
    return _EBOOT_CACHE[key]


def game_info(folder):
    folder = Path(folder or '.')
    if not (folder / 'eboot.bin').is_file():
        return None
    try:
        from prepare import sfo
        values = sfo((folder / 'sce_sys' / 'param.sfo').read_bytes())
        title, version = values.get('TITLE_ID', '?'), values.get('APP_VER', '?')
    except (OSError, ValueError, ImportError):
        title, version = '?', '?'
    return title, eboot_version(folder / 'eboot.bin') or version


def find_sys_modules(configured):
    if configured and all((Path(configured) / m).is_file() for m in SYS_MODULES):
        return configured
    for candidate in (PORT_DIR / 'user' / 'sys_modules',
                      Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'shadPS4' / 'sys_modules'):
        if all((candidate / m).is_file() for m in SYS_MODULES):
            return str(candidate)
    return ''


def dlc_count(root):
    if not root or not Path(root).is_dir():
        return 0
    try:
        from sotc_discovery import dlc_count as count
        return count(root)
    except (ImportError, OSError):
        return 0


def write_key_bindings(keys):
    ini = PORT_DIR / 'sotc.ini'
    try:
        lines = ini.read_text(encoding='utf-8').splitlines()
    except OSError:
        lines = []
    lines = [line for line in lines if not line.startswith('key.') and line != '# key bindings (launcher)']
    custom = dict(keys or {})
    if custom:
        lines.append('# key bindings (launcher)')
        lines += [f'key.{name}={value}' for name, value in sorted(custom.items())]
    ini.write_text('\n'.join(lines) + '\n', encoding='utf-8')


LOGS_KEPT = 5
CRASH_LOGS_KEPT = 20


def open_session_log(log_dir):
    log_dir.mkdir(parents=True, exist_ok=True)
    for i in range(LOGS_KEPT - 1, 0, -1):
        older = log_dir / ('last_run.log' if i == 1 else f'last_run.{i - 1}.log')
        if older.is_file():
            try:
                os.replace(older, log_dir / f'last_run.{i}.log')
            except OSError:
                pass
    return open(log_dir / 'last_run.log', 'w', encoding='utf-8', buffering=1)


def keep_crash_log(log_dir, code):
    if code == 0:
        return
    crashes = log_dir / 'crashes'
    try:
        crashes.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y-%m-%d_%H-%M-%S')
        shutil.copy2(log_dir / 'last_run.log', crashes / f'{stamp}_{code & 0xffffffff:#x}.log')
        for old in sorted(crashes.glob('*.log'))[:-CRASH_LOGS_KEPT]:
            old.unlink()
        for old in sorted(crashes.glob('*.dmp'))[:-5]:
            old.unlink()
    except OSError:
        pass


def install_css():
    provider = Gtk.CssProvider()
    data = CSS.encode('utf-8')
    try:
        provider.load_from_data(data)
    except TypeError:
        provider.load_from_data(data, -1)
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def label(text, cls=None, wrap=True):
    widget = Gtk.Label(label=text, xalign=0)
    widget.set_wrap(wrap)
    if cls:
        widget.add_css_class(cls)
    return widget


def page_title(title, subtitle=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(label(title, 'page-title', wrap=False))
    if subtitle:
        box.append(label(subtitle, 'muted'))
    return box


class LauncherWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.app = load_settings()
        self.process = None
        self.session = None
        self.stopping = False
        self.gpu_text = '• Verificando a placa de vídeo…'
        self.switches = {}
        self.checks = {}
        self.dma_checks = []
        self.dma_hints = []
        self.gpu_vendor = ''
        self._auto_dma = False
        self.key_entries = {}
        self._keys_dirty = False
        self._save_timer = 0
        self._check_timer = 0
        self.set_title('Shadow of the Colossus — port nativo')
        self.set_default_size(1120, 760)
        self.set_size_request(960, 640)
        install_css()
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.append(self.build_sidebar())
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(140)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        root.append(self.stack)
        self.set_content(root)
        self.build_play()
        self.build_game()
        self.build_graphics()
        self.build_controls()
        self.build_advanced()
        self.build_log()
        self.nav.select_row(self.nav.get_row_at_index(0))
        self.connect('close-request', self.on_close)
        GLib.idle_add(self.refresh_checks)
        threading.Thread(target=self.check_gpu, daemon=True).start()

    # ---- shared widgets -----------------------------------------------------------------------
    def build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(232, -1)
        box.add_css_class('sidebar')
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.set_margin_start(8)
        head.set_margin_bottom(16)
        try:
            icon = Gtk.Picture.new_for_filename(str(ICON))
            icon.set_content_fit(Gtk.ContentFit.CONTAIN)
            icon.set_size_request(52, 52)
            head.append(icon)
        except GLib.Error:
            pass
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        titles.set_valign(Gtk.Align.CENTER)
        titles.append(label('Shadow of the\nColossus', 'brand'))
        titles.append(label('PORT NATIVO · PS4', 'brand-sub', wrap=False))
        head.append(titles)
        box.append(head)
        self.nav = Gtk.ListBox()
        self.nav.add_css_class('nav')
        self.nav.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for name, title in NAV:
            row = Gtk.ListBoxRow()
            row.page_name = name
            row.set_child(label(title, wrap=False))
            self.nav.append(row)
        self.nav.connect('row-selected', self.on_nav)
        box.append(self.nav)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        box.append(spacer)
        footer = label('Linux · GTK4', 'muted small', wrap=False)
        footer.set_margin_start(12)
        box.append(footer)
        return box

    def on_nav(self, _listbox, row):
        if row is not None:
            self.stack.set_visible_child_name(row.page_name)

    def page(self, name, title, subtitle=None):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_top(22)
        body.set_margin_bottom(26)
        body.set_margin_start(28)
        body.set_margin_end(28)
        body.append(page_title(title, subtitle))
        scroll.set_child(body)
        self.stack.add_titled(scroll, name, title)
        return body

    def section(self, parent, text, top=14):
        widget = label(text, 'section', wrap=False)
        widget.set_margin_top(top)
        parent.append(widget)

    def hint(self, parent, text):
        widget = label(text, 'muted')
        parent.append(widget)
        return widget

    def row(self, parent, text, widget, hint=None):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title = label(text, wrap=False)
        title.set_hexpand(True)
        title.set_valign(Gtk.Align.CENTER)
        line.append(title)
        widget.set_valign(Gtk.Align.CENTER)
        line.append(widget)
        box.append(line)
        if hint:
            box.append(label(hint, 'muted'))
        parent.append(box)
        return box

    def set(self, key, value):
        self.app[key] = value
        if key in ('fps60', 'fps_unlocked') and value:
            other = 'fps_unlocked' if key == 'fps60' else 'fps60'
            if self.app.get(other):
                self.app[other] = False
                if other in self.switches:
                    self.switches[other].set_active(False)
        if key == 'perf_dma':
            for button in self.dma_checks:
                if button.get_active() != bool(value):
                    self._auto_dma = True
                    button.set_active(bool(value))
                    self._auto_dma = False
        if key in ('game_dir', 'sys_modules', 'dlc_dir', 'user_dir'):
            self.schedule_checks()
        self.refresh_summary()
        self.schedule_save()

    def switch_row(self, key, text, hint=None):
        switch = Gtk.Switch(active=bool(self.app.get(key, False)))
        switch.connect('notify::active', lambda w, _p: self.set(key, w.get_active()))
        self.switches[key] = switch
        self.row(self._current_parent, text, switch, hint)
        return switch

    def check(self, key, text, hint=None, default=True, parent=None):
        button = Gtk.CheckButton(label=text, active=bool(self.app.get(key, default)))
        button.connect('toggled', lambda w: self.set(key, w.get_active()))
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        holder.append(button)
        if hint:
            holder.append(label(hint, 'muted'))
        (parent or self._current_parent).append(holder)
        return button

    def dma_check(self, text, hint):
        button = Gtk.CheckButton(label=text, active=bool(self.app.get('perf_dma', True)))
        button.connect('toggled', self.on_dma_toggled)
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        holder.append(button)
        note = label(hint, 'muted')
        holder.append(note)
        self._current_parent.append(holder)
        self.dma_checks.append(button)
        self.dma_hints.append(note)
        return button

    def on_dma_toggled(self, button):
        if self._auto_dma:
            return
        self.app['dma_auto'] = False
        self.set('perf_dma', button.get_active())

    def dropdown(self, key, options):
        values = [value for value, _text in options]
        widget = Gtk.DropDown.new_from_strings([text for _value, text in options])
        current = self.app.get(key, values[0])
        widget.set_selected(values.index(current) if current in values else 0)
        widget.set_size_request(240, -1)
        widget.connect('notify::selected', lambda d, _p: self.set(key, values[d.get_selected()]))
        return widget

    def entry(self, key, hint=None, placeholder=''):
        widget = Gtk.Entry(text=str(self.app.get(key, '')))
        widget.set_hexpand(True)
        widget.set_placeholder_text(placeholder)
        widget.connect('changed', lambda w: self.set(key, w.get_text()))
        if hint:
            self.row(self._current_parent, '', widget, hint)
        return widget

    def path_row(self, key, title, hint=None, open_button=True):
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        entry = Gtk.Entry(text=str(self.app.get(key, '')))
        entry.set_hexpand(True)
        entry.connect('changed', lambda w: self.set(key, w.get_text()))
        line.append(entry)
        choose = Gtk.Button(label='Escolher')
        choose.connect('clicked', lambda _b: self.choose_folder(key))
        line.append(choose)
        if open_button:
            opener = Gtk.Button(label='Abrir')
            opener.connect('clicked', lambda _b: self.open_path(self.app.get(key)))
            line.append(opener)
        self.row(self._current_parent, title, line, hint)
        return entry

    def button(self, parent, text, callback, cls=None):
        widget = Gtk.Button(label=text)
        if cls:
            widget.add_css_class(cls)
        widget.connect('clicked', lambda _b: callback())
        parent.append(widget)
        return widget

    def button_row(self, parent, buttons):
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        line.set_margin_top(6)
        for text, callback in buttons:
            line.append(self._make_button(text, callback))
        parent.append(line)

    def _make_button(self, text, callback):
        widget = Gtk.Button(label=text)
        widget.connect('clicked', lambda _b: callback())
        return widget

    # ---- play page ----------------------------------------------------------------------------
    def banner_art(self):
        art = Path(self.app.get('game_dir') or '.') / 'sce_sys' / 'pic1.png'
        return art if art.is_file() else ICON

    def update_banner(self):
        path = self.banner_art()
        if path == self._banner_path:
            return
        try:
            self.banner_pic.set_filename(str(path))
        except GLib.Error:
            return
        self._banner_path = path
        self.banner_pic.set_content_fit(Gtk.ContentFit.CONTAIN if path == ICON else Gtk.ContentFit.COVER)

    def build_play(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay = Gtk.Overlay()
        overlay.add_css_class('banner')
        self.banner_pic = Gtk.Picture.new_for_filename(str(self.banner_art()))
        self.banner_pic.set_size_request(-1, 270)
        self.banner_pic.set_hexpand(True)
        overlay.set_child(self.banner_pic)
        self._banner_path = None
        self.update_banner()
        shade = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.END)
        shade.add_css_class('banner-shade')
        shade.append(label('Shadow of the Colossus', 'banner-title', wrap=False))
        self.banner_info = label('Pasta do jogo não escolhida', 'banner-sub', wrap=False)
        shade.append(self.banner_info)
        overlay.add_overlay(shade)
        page.append(overlay)

        body = Gtk.ScrolledWindow()
        body.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body.set_vexpand(True)
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=28)
        columns.set_margin_top(16)
        columns.set_margin_start(26)
        columns.set_margin_end(26)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_hexpand(True)
        left.append(label('Verificação', 'section', wrap=False))
        for key in ('game', 'dlc', 'sound', 'saves', 'gpu'):
            widget = label('', 'check-info')
            widget.set_max_width_chars(54)
            left.append(widget)
            self.checks[key] = widget
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_hexpand(True)
        right.set_size_request(330, -1)
        right.append(label('Ajustes rápidos', 'section', wrap=False))
        self._current_parent = right
        self.row(right, 'Saída', self.dropdown('output_res', OUTPUTS))
        self.row(right, 'Upscaler', self.dropdown('upscaler', UPSCALERS))
        self.switch_row('fps60', '60 FPS (experimental)')
        self.switch_row('fps_unlocked', 'FPS livre (experimental)')
        self.switch_row('af16', 'Texturas nítidas (filtro 16x)')
        self.switch_row('fullscreen', 'Tela cheia')
        columns.append(left)
        columns.append(right)
        body.set_child(columns)
        page.append(body)

        self.status_label = label('', 'muted')
        self.status_label.set_margin_start(26)
        self.status_label.set_margin_end(26)
        self.status_label.set_margin_top(6)
        page.append(self.status_label)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bar.set_margin_top(6)
        bar.set_margin_bottom(14)
        bar.set_margin_start(26)
        bar.set_margin_end(26)
        self.summary_label = label('', 'muted')
        self.summary_label.set_hexpand(True)
        bar.append(self.summary_label)
        self.stop_button = Gtk.Button(label='Parar')
        self.stop_button.add_css_class('stop')
        self.stop_button.set_sensitive(False)
        self.stop_button.connect('clicked', lambda _b: self.stop_game())
        bar.append(self.stop_button)
        self.play_button = Gtk.Button(label='JOGAR')
        self.play_button.add_css_class('play')
        self.play_button.connect('clicked', lambda _b: self.start_game())
        bar.append(self.play_button)
        page.append(bar)
        self.stack.add_named(page, 'play')
        self._current_parent = None

    # ---- game & saves -------------------------------------------------------------------------
    def build_game(self):
        page = self.page('game', 'Jogo e saves',
                         'O dump do jogo, os módulos de som do seu console e os saves do port.')
        self._current_parent = page
        self.game_info_label = label('', 'muted')
        page.append(self.game_info_label)
        self.section(page, 'Pastas', top=6)
        self.path_row('game_dir', 'Pasta do jogo',
                      'A pasta que contém eboot.bin e sce_sys/param.sfo (ex.: …/CUSA08809).')
        self.path_row('dlc_dir', 'Pasta das DLC',
                      'Opcional: a pasta com as DLC instaladas (o port lista o que houver).')
        self.path_row('sys_modules', 'Módulos de som',
                      'libSceUlt.sprx e libSceNgs2.sprx do seu console. Sem eles o jogo fica mudo.')
        self.section(page, 'Dados do port')
        data_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        data_label = Gtk.Label(label=str(PORT_DIR / 'user'), xalign=0, selectable=True)
        data_label.set_hexpand(True)
        data_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        data_label.set_tooltip_text(str(PORT_DIR / 'user'))
        data_row.append(data_label)
        opener = Gtk.Button(label='Abrir')
        opener.connect('clicked', lambda _b: self.open_path(PORT_DIR / 'user'))
        data_row.append(opener)
        self.row(page, 'Pasta de dados', data_row,
                 'Saves, caches e o last_run.log ficam aqui (run-portable.sh fixa esta pasta).')
        self.section(page, 'Saves')
        self.button_row(page, [('Abrir pasta de saves', self.open_saves),
                               ('Importar save…', self.import_save),
                               ('Verificar de novo', self.refresh_checks)])
        self.hint(page, 'O save fica em user/savedata/1/CUSA08809. Copie a pasta de outro PC ou de '
                        'outra instalação do shadPS4 para cá.')
        self._current_parent = None

    # ---- graphics -----------------------------------------------------------------------------
    def build_graphics(self):
        page = self.page('graphics', 'Imagem e FPS',
                         'Os modos vêm do fork shadPS4 SotC e valem para a versão EU 1.01.')
        self._current_parent = page
        self.section(page, 'Modos', top=4)
        self.check('af16', 'Texturas nítidas (filtro anisotrópico 16x)',
                   'Chão, grama e rochas ficam nítidos à distância, quase sem custo.')
        self.check('fps60', '60 FPS (experimental)',
                   "Tira o limite de 30 FPS do jogo e limita a 60 FPS, como no PS4 Pro.")
        self.check('fps_unlocked', 'FPS livre (experimental)',
                   'Sem limite (até 120 FPS). Pode quebrar algumas lutas (o 5º colosso que sai '
                   'voando, a cena do 2º colosso que não começa).')
        self.section(page, 'Resolução')
        self.row(page, 'Saída', self.dropdown('output_res', OUTPUTS),
                 'O jogo renderiza em 1080p, como no PS4; a imagem é ampliada ou reduzida para a saída.')
        self.row(page, 'Upscaler', self.dropdown('upscaler', UPSCALERS),
                 'FSR 1 amplia com bordas nítidas (acima de 1080p).')
        self.row(page, 'Nitidez (RCAS)', self.dropdown('sharpness', SHARPNESS))
        self.section(page, 'Modo PS4 Pro')
        self.check('neo', 'Apresentar-se como PS4 Pro',
                   'O jogo oferece, no menu Opções > Apresentação, o Modo Grafismo do PS4 Pro. '
                   'Mais pesado: ~25 FPS no campo aberto contra ~38 no modo normal.')
        self.section(page, 'Desempenho')
        self.check('perf_culling', 'Culling sem a GPU (recomendado)',
                   'Desliga o culling de índices feito na GPU: mesma imagem e bem menos esperas. '
                   'No santuário: ~22 → ~28 FPS.')
        self.check('perf_record_thread', 'Comandos Vulkan em thread própria (recomendado)',
                   'Grava e envia os comandos da GPU em outra thread. Desligue se notar travamentos.')
        self.check('perf_fastbind', 'Reutilizar binds entre desenhos (recomendado)',
                   'Não refaz os binds quando o desenho seguinte usa o mesmo pipeline, recursos e '
                   'uniforms. Medido no Santuário e no caminho até o 1º colosso: ~25 → 30 FPS com '
                   'frametime cravado em 33,3 ms. Desligue se aparecer textura ou sombra estranha.')
        self.dma_check('Reflexos completos da água (acesso direto à memória)',
                       'Em AMD/Intel fica desligado automaticamente: o DMA desenhava listras nas '
                       'sombras e na água (issues #57/#28). Marque para forçar '
                       'BB_DIRECT_MEMORY_ACCESS=1 (as listras voltam).')
        self.row(page, 'Envio de trabalho à GPU', self.dropdown('gpu_submit', GPU_SUBMIT),
                 'Em AMD/Intel use "Ligado" só para testar e volte para "Automático" se a tela ficar preta.')
        self.section(page, 'Efeitos')
        for key, title, _off in EFFECTS:
            self.check(key, title, default=True)
        self.hint(page, 'O motion blur, o brilho e os filtros ficam no menu do próprio jogo '
                        '(Opções > Apresentação).')
        self.section(page, 'Tela')
        self.check('fullscreen', 'Tela cheia')
        self.row(page, 'Apresentação', self.dropdown('present_mode', PRESENT_MODES))
        self._current_parent = None

    # ---- controls -----------------------------------------------------------------------------
    def build_controls(self):
        page = self.page('controls', 'Controles', 'Mouse, controle e teclado.')
        self._current_parent = page
        self.section(page, 'Mouse', top=4)
        self.switch_row('mouse', 'Usar o mouse para a câmera')
        self.row(page, 'Sensibilidade', self.dropdown('mouse_sens', MOUSE_SENS))
        self.switch_row('mouse_invert', 'Inverter o eixo vertical')
        self.section(page, 'Controle')
        self.entry('gamepad', 'Nome ou GUID do controle (vazio: o primeiro que o SDL encontrar).',
                   placeholder='ex.: Xbox Wireless Controller')
        self.section(page, 'Teclado')
        self.hint(page, 'Nomes de tecla do SDL: W, A, Space, Left Shift, Return, Up, Keypad 1. '
                        'Deixe vazio para a tecla não fazer nada.')
        grid = Gtk.Grid(column_spacing=16, row_spacing=6, margin_top=6)
        keys = self.app.get('keys') or {}
        for index, (name, default, text) in enumerate(KEY_INPUTS):
            column = (index % 2) * 2
            row = index // 2
            title = label(text, wrap=False)
            title.set_size_request(150, -1)
            entry = Gtk.Entry(text=keys.get(name, default))
            entry.set_size_request(110, -1)
            entry.connect('changed', lambda w, n=name: self.key_changed(n, w.get_text()))
            grid.attach(title, column, row, 1, 1)
            grid.attach(entry, column + 1, row, 1, 1)
            self.key_entries[name] = entry
        page.append(grid)
        self.button_row(page, [('Restaurar padrão', self.reset_keys),
                               ('Salvar teclas', self.save_keys)])
        self.hint(page, 'As teclas são gravadas em sotc.ini (BB_CONFIG) quando o launcher salva.')
        self._current_parent = None

    def key_changed(self, name, value):
        keys = dict(self.app.get('keys') or {})
        keys[name] = value.strip()
        self.app['keys'] = keys
        self._keys_dirty = True
        self.schedule_save()

    def reset_keys(self):
        self.app['keys'] = {}
        for name, default, _text in KEY_INPUTS:
            self.key_entries[name].set_text(default)
        self._keys_dirty = True
        self.set_status('Teclas restauradas para o padrão.')
        self.schedule_save()

    def save_keys(self):
        write_key_bindings(self.app.get('keys') or {})
        self._keys_dirty = False
        self.set_status('Teclas gravadas em sotc.ini.')

    # ---- advanced -----------------------------------------------------------------------------
    def build_advanced(self):
        page = self.page('advanced', 'Avançado', 'Diagnóstico e opções de teste.')
        self._current_parent = page
        self.section(page, 'Desempenho', top=4)
        self.check('perf_culling', 'Culling sem a GPU (recomendado)')
        self.check('perf_record_thread', 'Comandos Vulkan em thread própria (recomendado)')
        self.check('perf_fastbind', 'Reutilizar binds entre desenhos (recomendado)')
        self.dma_check('Reflexos completos da água (DMA)',
                       'Desligado automaticamente em AMD/Intel desde a opt8. Marcar força '
                       'BB_DIRECT_MEMORY_ACCESS=1 e pode trazer as listras de volta.')
        self.row(page, 'Envio de trabalho à GPU', self.dropdown('gpu_submit', GPU_SUBMIT))
        self.section(page, 'Testes')
        self.row(page, 'Geração de quadros (FSR 3)', self.dropdown('framegen', FRAMEGEN),
                 'F8 liga/desliga no jogo. "Off" mantém a apresentação como era.')
        self.switch_row('mangohud', 'MangoHud (overlay de desempenho)',
                        'Precisa do mangohud instalado; o run-portable.sh cuida do resto.')
        self.switch_row('show_fps', 'FPS no registro (a cada 5 s)')
        self.switch_row('profile', 'Criar perfil do GpuDraw ao iniciar',
                        'Grava user/profile-<data>.txt: 10 s de espera e 30 s de amostra em shadPS4:GpuDraw.')
        self.row(page, 'Leituras da GPU', self.dropdown('readbacks', READBACKS))
        self.entry('extra_env', 'Pares NOME=valor separados por espaço.',
                   placeholder='SOTC_VCACHE=0 VK_LOADER_DEBUG=error')
        self.entry('engine_cvars', 'Cvars do motor separados por espaço.',
                   placeholder='doIndexBufferCulling=0 fog_enable=0')
        self.section(page, 'Lançador')
        self.switch_row('rebuild_on_play', 'Recompilar antes de jogar',
                        'Roda build.sh (BB_PGO=off BB_LTO=ON) antes do run-portable.sh. '
                        'Desligado usa o binário já compilado em out/.')
        self.button_row(page, [('Recompilar agora', self.rebuild),
                               ('Limpar cache de shaders', self.clear_cache),
                               ('Abrir pasta do port', lambda: self.open_path(PORT_DIR)),
                               ('Abrir último log', self.open_last_log)])
        self.hint(page, f'Configuração: {CONFIG_FILE}')
        self._current_parent = None

    # ---- log ----------------------------------------------------------------------------------
    def build_log(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        body.set_margin_top(22)
        body.set_margin_bottom(18)
        body.set_margin_start(24)
        body.set_margin_end(24)
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = page_title('Registro')
        title.set_hexpand(True)
        head.append(title)
        head.append(self._make_button('Copiar', self.copy_log))
        head.append(self._make_button('Limpar', lambda: self.log_buffer.set_text('')))
        body.append(head)
        log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        log_box.set_vexpand(True)
        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_scroll.set_vexpand(True)
        log_scroll.set_min_content_height(420)
        log_scroll.add_css_class('log')
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_view.add_css_class('log')
        self.log_buffer = self.log_view.get_buffer()
        log_scroll.set_child(self.log_view)
        log_box.append(log_scroll)
        body.append(log_box)
        scroll.set_child(body)
        self.stack.add_titled(scroll, 'log', 'Registro')
        self.log_scroll = log_scroll

    # ---- settings / summary -------------------------------------------------------------------
    def refresh_summary(self):
        if not hasattr(self, 'summary_label'):
            return
        a = self.app
        mode = 'FPS livre' if a.get('fps_unlocked') else '60 FPS' if a.get('fps60') else '30 FPS'
        parts = [mode, a.get('output_res', '1920x1080').replace('x', '×'),
                 'FSR 1' if a.get('upscaler') == 'fsr1' else 'Bilinear']
        if a.get('af16'):
            parts.append('AF 16x')
        parts.append('PS4 Pro' if a.get('neo') else 'PS4')
        parts.append('tela cheia' if a.get('fullscreen') else 'janela')
        if a.get('framegen') in ('fsr', 'auto'):
            parts.append('FSR 3')
        self.summary_label.set_text(' · '.join(parts))

    def schedule_save(self):
        if self._save_timer:
            GLib.source_remove(self._save_timer)
        self._save_timer = GLib.timeout_add(700, self.save)

    def save(self):
        self._save_timer = 0
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self.app, indent=2, ensure_ascii=False) + '\n',
                                   encoding='utf-8')
        except OSError as error:
            self.set_status(f'Não foi possível salvar as opções: {error}', bad=True)
        if self._keys_dirty:
            try:
                write_key_bindings(self.app.get('keys') or {})
                self._keys_dirty = False
            except OSError as error:
                self.set_status(f'Não foi possível gravar sotc.ini: {error}', bad=True)
        return False

    def on_close(self, _window):
        self.save()
        return False

    def set_status(self, text, bad=False):
        if hasattr(self, 'status_label'):
            self.status_label.set_text(text)
            self.status_label.remove_css_class('check-bad')
            if bad:
                self.status_label.add_css_class('check-bad')

    # ---- verification -------------------------------------------------------------------------
    def schedule_checks(self):
        if self._check_timer:
            GLib.source_remove(self._check_timer)
        self._check_timer = GLib.timeout_add(450, self._run_checks)

    def _run_checks(self):
        self._check_timer = 0
        self.refresh_checks()
        return False

    def _style_check(self, widget, text):
        for cls in ('check-ok', 'check-warn', 'check-bad', 'check-info'):
            widget.remove_css_class(cls)
        widget.add_css_class('check-ok' if text.startswith('✓') else
                             'check-warn' if text.startswith('⚠') else
                             'check-bad' if text.startswith('✗') else 'check-info')

    def set_check(self, key, text):
        widget = self.checks[key]
        widget.set_text(text)
        self._style_check(widget, text)

    def refresh_checks(self):
        info = game_info(self.app.get('game_dir'))
        if not info:
            self.set_check('game', '✗ Não há eboot.bin na pasta do jogo (Jogo e saves)')
        elif info == (GAME_ID, GAME_VERSION):
            self.set_check('game', f'✓ {info[0]} versão {info[1]}: todos os modos disponíveis')
        else:
            self.set_check('game', f'⚠ {info[0]} versão {info[1]}: o port foi feito para '
                                   f'{GAME_ID} {GAME_VERSION}; os modos não se aplicam')
        modules = find_sys_modules(self.app.get('sys_modules'))
        if modules:
            self.set_check('sound', '✓ Módulos de som encontrados')
        else:
            self.set_check('sound', '⚠ Sem os módulos de som do seu console: o jogo fica mudo '
                                    '(Jogo e saves)')
        saves = PORT_DIR / 'user' / 'savedata' / '1' / GAME_ID
        if saves.is_dir() and any(saves.iterdir()):
            self.set_check('saves', f'✓ Saves em {saves}')
        else:
            self.set_check('saves', f'• Ainda sem saves: o jogo cria em {saves}')
        count = dlc_count(self.app.get('dlc_dir'))
        self.set_check('dlc', f'✓ DLC: {count} instalada(s)' if count else '• Sem DLC')
        self.set_check('gpu', self.gpu_text)
        self.banner_info.set_text(f'{info[0]} · versão do jogo {info[1]}' if info
                                  else 'Pasta do jogo não escolhida')
        self.update_banner()
        if self.game_info_label:
            self.game_info_label.set_text(
                f'{info[0]} · versão do jogo {info[1]}' if info
                else 'Escolha a pasta do dump (eboot.bin + sce_sys).')
        if self.process is None:
            self.play_button.set_sensitive(bool(info))
            if self.summary_label.get_text() == '':
                self.refresh_summary()
        self.refresh_summary()

    def check_gpu(self):
        text = ''
        exe = PORT_DIR / 'out' / 'bb-gpu-capabilities'
        if exe.is_file():
            try:
                result = subprocess.run([str(exe), '--live-resolution'], capture_output=True,
                                        text=True, timeout=30)
                for line in (result.stdout + result.stderr).splitlines():
                    if line.startswith('GPU: '):
                        text = line[5:].strip()
                        break
            except (OSError, subprocess.SubprocessError):
                text = ''
        if not text:
            try:
                result = subprocess.run(['vulkaninfo', '--summary'], capture_output=True,
                                        text=True, timeout=30)
                for line in result.stdout.splitlines():
                    if 'deviceName' in line and '=' in line:
                        text = line.split('=', 1)[1].strip()
                        break
            except (OSError, subprocess.SubprocessError):
                text = ''
        text = f'✓ Placa: {text}' if text else '⚠ Não foi possível detectar a GPU'
        GLib.idle_add(self._set_gpu, text)

    def _set_gpu(self, text):
        self.gpu_text = text
        self.set_check('gpu', text)
        self.gpu_vendor = self.detect_vendor(text)
        if self.gpu_vendor and self.app.get('dma_auto', True):
            want = self.gpu_vendor == 'nvidia'
            if bool(self.app.get('perf_dma', True)) != want:
                self.set('perf_dma', want)
                self.set_status('DMA ligado (NVIDIA): reflexos completos da água.' if want else
                                'DMA desligado automaticamente (AMD/Intel): evita listras nas '
                                'sombras e na água.')
        return False

    @staticmethod
    def detect_vendor(text):
        low = text.lower()
        if 'amd' in low or 'radeon' in low or 'advanced micro devices' in low:
            return 'amd'
        if 'intel' in low or '8086' in low:
            return 'intel'
        if 'nvidia' in low or '10de' in low:
            return 'nvidia'
        return ''

    # ---- actions ------------------------------------------------------------------------------
    def choose_folder(self, key):
        dialog = Gtk.FileDialog(title='Escolher pasta')
        dialog.set_modal(True)
        dialog.select_folder(self, None, self._folder_selected, key)

    def _folder_selected(self, dialog, result, key):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder and folder.get_path():
            self.set(key, folder.get_path())
            if key == 'game_dir':
                self.refresh_checks()

    def open_path(self, path):
        path = Path(path or '.')
        if not path.exists():
            self.set_status(f'Pasta não encontrada: {path}', bad=True)
            return
        try:
            Gio.AppInfo.launch_default_for_uri(path.resolve().as_uri(), None)
        except GLib.Error as error:
            self.set_status(f'Não foi possível abrir a pasta: {error.message}', bad=True)

    def open_saves(self):
        path = PORT_DIR / 'user' / 'savedata' / '1' / GAME_ID
        path.mkdir(parents=True, exist_ok=True)
        self.open_path(path)

    def import_save(self):
        target = PORT_DIR / 'user' / 'savedata' / '1' / GAME_ID
        dialog = Gtk.FileDialog(title='Escolher a pasta do save')
        dialog.set_modal(True)
        dialog.select_folder(self, None, self._save_folder_selected, str(target))

    def _save_folder_selected(self, dialog, result, target):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if not folder or not folder.get_path():
            return
        source = Path(folder.get_path())
        if source.name != GAME_ID and (source / GAME_ID).is_dir():
            source = source / GAME_ID
        destination = Path(target)
        try:
            destination.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                if item.is_dir():
                    shutil.copytree(item, destination / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, destination / item.name)
        except OSError as error:
            self.set_status(f'Falha ao importar o save: {error}', bad=True)
            return
        self.set_status(f'Save importado de {source}.')
        self.refresh_checks()

    def clear_cache(self):
        cache = PORT_DIR / 'user' / 'cache'
        for folder in (cache / GAME_ID, cache / (GAME_ID + '_nodma'), cache / 'mesa', cache / 'fish'):
            shutil.rmtree(folder, ignore_errors=True)
        self.set_status('Cache de shaders limpo; o jogo compila de novo na próxima vez.')

    def open_last_log(self):
        self.open_path(PORT_DIR / 'user' / 'last_run.log')

    def copy_log(self):
        text = self.log_buffer.get_text(self.log_buffer.get_start_iter(),
                                        self.log_buffer.get_end_iter(), False)
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)
        self.set_status('Registro copiado.')

    # ---- environment / process ----------------------------------------------------------------
    def game_environment(self):
        s = self.app
        env = dict(os.environ)
        env['SOTC_GAME_DIR'] = s['game_dir']
        env['SOTC_USER_DIR'] = str(PORT_DIR / 'user')
        modules = find_sys_modules(s.get('sys_modules'))
        if modules:
            env['SOTC_SYS_MODULES'] = modules
        if s.get('dlc_dir'):
            env['SOTC_DLC_DIR'] = s['dlc_dir']
        fps60 = s.get('fps60') or s.get('fps_unlocked')
        env['SOTC_MODES'] = ','.join(m for m, on in (('af16', s.get('af16')), ('fps60', fps60)) if on)
        if fps60:
            env['SOTC_FPS_CAP'] = '0' if s.get('fps_unlocked') else '60'
        env['BB_FULLSCREEN'] = '1' if s.get('fullscreen') else '0'
        env['BB_PRESENT_MODE'] = s.get('present_mode') or 'Mailbox'
        if s.get('language'):
            env['BB_LANGUAGE'] = s['language']
        if str(s.get('player_name', '')).strip():
            env['BB_USER_NAME'] = str(s['player_name']).strip()
        env['SOTC_FPS'] = '1' if s.get('show_fps') else '0'
        if s.get('readbacks'):
            env['BB_READBACKS'] = s['readbacks']
        cvars = [off for key, _title, off in EFFECTS if not s.get(key, True)]
        if s.get('perf_culling', True):
            cvars += ['doIndexBufferCulling=0', 'doSunShadowIndexBufferCulling=0']
        cvars += str(s.get('engine_cvars', '')).split()
        env['SOTC_CVARS'] = ' '.join(cvars)
        env['SOTC_RECORD_THREAD'] = '1' if s.get('perf_record_thread', True) else '0'
        env['SOTC_FAST_BIND'] = '1' if s.get('perf_fastbind', True) else '0'
        if not s.get('perf_dma', True):
            env['BB_DIRECT_MEMORY_ACCESS'] = '0'
        elif not s.get('dma_auto', True):
            env['BB_DIRECT_MEMORY_ACCESS'] = '1'
        if s.get('gpu_submit') == 'on':
            env['SOTC_FLUSH_US'], env['SOTC_RB_AHEAD'] = '1000', '1'
        elif s.get('gpu_submit') == 'off':
            env['SOTC_FLUSH_EVERY'], env['SOTC_RB_AHEAD'] = '0', '0'
        env['SOTC_NEO'] = '1' if s.get('neo') else '0'
        env['SOTC_OUTPUT_RES'] = s.get('output_res') or '1920x1080'
        env['BB_FSR1'] = '1' if s.get('upscaler', 'fsr1') == 'fsr1' else '0'
        if s.get('sharpness') == 'off':
            env['BB_RCAS'] = '0'
        else:
            env['BB_RCAS'] = '1'
            env['BB_RCAS_ATTENUATION'] = str(s.get('sharpness') or '250')
        env['SOTC_MOUSE'] = '1' if s.get('mouse', True) else '0'
        env['SOTC_MOUSE_SENS'] = str(s.get('mouse_sens') or '1.0')
        env['SOTC_MOUSE_INVERT'] = '1' if s.get('mouse_invert') else '0'
        if str(s.get('gamepad', '')).strip():
            env['BB_GAMEPAD'] = str(s['gamepad']).strip()
        env['BB_CONFIG'] = str(PORT_DIR / 'sotc.ini')
        env['SOTC_MANGOHUD'] = '1' if s.get('mangohud') else '0'
        env['SOTC_FRAMEGEN'] = s.get('framegen') if s.get('framegen') in ('fsr', 'auto') else 'off'
        if s.get('profile'):
            env['SOTC_PROFILE'] = '1'
            env['SOTC_PROFILE_THREAD'] = 'shadPS4:GpuDraw'
            env['SOTC_PROFILE_DELAY'] = '10'
            env['SOTC_PROFILE_SECONDS'] = '30'
            env['SOTC_PROFILE_OUT'] = str(PORT_DIR / 'user' /
                                          f'profile-{time.strftime("%Y%m%d-%H%M%S")}.txt')
        for item in str(s.get('extra_env', '')).split():
            if '=' in item:
                key, value = item.split('=', 1)
                env[key] = value
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        return env

    def start_game(self):
        if self.process is not None:
            return
        if not game_info(self.app.get('game_dir')):
            self.set_status('Escolha primeiro a pasta do jogo (Jogo e saves).', bad=True)
            self.nav.select_row(self.nav.get_row_at_index(1))
            return
        self.save()
        env = self.game_environment()
        env['BB_PREBUILT'] = '1'
        cmd = ['bash', str(PORT_DIR / 'run-portable.sh')]
        if self.app.get('rebuild_on_play'):
            cmd = ['bash', '-c', 'BB_PGO=off BB_LTO=ON bash build.sh && exec bash run-portable.sh']
        try:
            self.session = open_session_log(PORT_DIR / 'user')
        except OSError as error:
            self.set_status(f'Não foi possível abrir o registro: {error}', bad=True)
            self.session = None
        self.append_log('$ ' + ' '.join(cmd))
        try:
            self.process = subprocess.Popen(cmd, cwd=str(PORT_DIR), env=env,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                            start_new_session=True)
        except OSError as error:
            self.process = None
            self.set_status(f'Não foi possível iniciar o jogo: {error}', bad=True)
            return
        self.stopping = False
        self.play_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.set_status('Iniciando…')
        self.nav.select_row(self.nav.get_row_at_index(0))
        threading.Thread(target=self._reader, args=(self.process,), daemon=True).start()

    def rebuild(self):
        if self.process is not None:
            self.set_status('Há um processo em execução; pare antes de recompilar.', bad=True)
            return
        self.save()
        env = self.game_environment()
        env['BB_PGO'] = 'off'
        env['BB_LTO'] = 'ON'
        cmd = ['bash', str(PORT_DIR / 'build.sh')]
        self.append_log('$ BB_PGO=off BB_LTO=ON bash build.sh')
        try:
            self.process = subprocess.Popen(cmd, cwd=str(PORT_DIR), env=env,
                                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                            start_new_session=True)
        except OSError as error:
            self.set_status(f'Não foi possível compilar: {error}', bad=True)
            return
        self.stopping = False
        self.play_button.set_sensitive(False)
        self.stop_button.set_sensitive(True)
        self.set_status('Compilando…')
        self.append_log('Compilando o port (BB_PGO=off BB_LTO=ON)…')
        threading.Thread(target=self._reader, args=(self.process,), daemon=True).start()

    def _reader(self, proc):
        try:
            for line in proc.stdout:
                GLib.idle_add(self.append_log, line.rstrip('\n'))
        except (OSError, ValueError):
            pass
        code = proc.wait()
        GLib.idle_add(self._ended, code)

    def _ended(self, code):
        if self.session:
            try:
                self.session.close()
            except OSError:
                pass
            self.session = None
        self.process = None
        if code:
            keep_crash_log(PORT_DIR / 'user', code)
        self.play_button.set_sensitive(bool(game_info(self.app.get('game_dir'))))
        self.stop_button.set_sensitive(False)
        self.set_status(f'Encerrado (código {code}).' if code else 'Encerrado.')
        self.append_log(f'[encerrado: {code}]')
        return False

    def stop_game(self):
        if self.process is None:
            return
        self.stopping = True
        self.set_status('Parando…')
        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        GLib.timeout_add(3000, self._force_kill)

    def _force_kill(self):
        if self.process is not None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        return False

    def append_log(self, line):
        if self.session:
            try:
                self.session.write(line + '\n')
            except OSError:
                pass
        if not hasattr(self, 'log_buffer'):
            return
        if self.log_buffer.get_line_count() > MAX_LOG_LINES:
            start = self.log_buffer.get_start_iter()
            end = self.log_buffer.get_iter_at_line(500)
            self.log_buffer.delete(start, end)
        self.log_buffer.insert(self.log_buffer.get_end_iter(), line + '\n')
        if line.strip():
            self.status_label.set_text(line.strip()[-180:])
            self.status_label.set_tooltip_text(line.strip())
        adjustment = self.log_scroll.get_vadjustment()
        if adjustment is not None:
            adjustment.set_value(adjustment.get_upper())


class LauncherApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='io.github.bbport.SotcLauncher')
        self.window = None

    def do_activate(self):
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        if self.window is None:
            self.window = LauncherWindow(self)
        self.window.present()

    def do_shutdown(self):
        if self.window is not None:
            self.window.save()
        Adw.Application.do_shutdown(self)


def main():
    Gtk.Window.set_default_icon_name('applications-games')
    app = LauncherApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    raise SystemExit(main())
