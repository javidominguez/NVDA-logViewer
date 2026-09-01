from pathlib import Path
import shutil
import os
import time
import re
import wx
import json
import hashlib
import nvdaControllerClient
import l10n
from l10n import _

import markdown
import webbrowser

from dataclasses import dataclass, field
from datetime import datetime


# ============================================================================
# REGEX
# ============================================================================

HEADER_RE = re.compile(
    r"^(?P<level>DEBUG|INFO|WARNING|ERROR|DEBUGWARNING|IO)\s+-\s+"
    r"(?P<source>.*?)\s+\((?P<time>\d\d:\d\d:\d\d\.\d+)\)\s+-\s+"
    r"(?P<thread>.*?)\s*(?:\((?P<pid>\d+)\))?:\s*$"
)


# Patrón para Tracebacks: File "Ruta", line Numero,
TRACEBACK_FILE_RE = re.compile(
    r'\s*File "(?P<path>.+)", line (?P<line>\d+),'
)

GLOBAL_PLUGIN_RE = re.compile(
    r"^external:globalPlugins\.([^.]+)(?:\.(.*))?$"
)

APP_MODULE_RE = re.compile(
    r"^external:appModules\.([^.]+)(?:\.(.*))?$"
)


# ============================================================================
# MODELO DE DATOS
# ============================================================================

@dataclass
class LogEntry:
    id: int

    level: str
    source_raw: str
    time_text: str
    thread: str
    pid: int

    message: str = ""
    traceback: list[str] = field(default_factory=list)

    @property
    def source_type(self):
        """
        Tipo de origen:

        NVDA
        Global Plugin
        App Module
        """

        if self.source_raw.startswith("external:globalPlugins."):
            return "Global Plugin"

        if self.source_raw.startswith("external:appModules."):
            return "App Module"

        return "NVDA"

    @property
    def addon(self):
        """
        Nombre del complemento o aplicación.
        """

        match = GLOBAL_PLUGIN_RE.match(self.source_raw)

        if match:
            return match.group(1)

        match = APP_MODULE_RE.match(self.source_raw)

        if match:
            return match.group(1)

        return "NVDA"

    @property
    def module(self):
        """
        Módulo principal.

        Por ejemplo:

            braille.BrailleHandler.setDisplayByName
                -> braille

            core.main
                -> core

            config.ConfigManager._loadConfig
                -> config
        """

        if self.source_type == "NVDA":
            return self.source_raw.split(".", 1)[0]

        if self.source_type == "Global Plugin":
            match = GLOBAL_PLUGIN_RE.match(self.source_raw)

        elif self.source_type == "App Module":
            match = APP_MODULE_RE.match(self.source_raw)

        else:
            return self.source_raw

        if not match:
            return self.source_raw

        remainder = match.group(2)

        if not remainder:
            return self.addon

        return remainder.split(".", 1)[0]

    @property
    def display_emitter(self):
        """
        Nombre del emisor que se muestra en el árbol.
        """

        if self.source_type == "NVDA":
            return "NVDA"

        return self.addon

    @property
    def header_text(self):
        """
        Reconstruye la línea de encabezado original de la entrada.

        Ejemplo:

        INFO - core.main (17:42:04.341) - MainThread (21420):
        """

        return (
            f"{self.level} - "
            f"{self.source_raw} "
            f"({self.time_text}) - "
            f"{self.thread} "
            f"({self.pid}):"
        )

    @property
    def sort_time(self):
        """
        Hora utilizada para ordenar la vista cronológica.
        """

        try:

            return datetime.strptime(
                self.time_text,
                "%H:%M:%S.%f",
            )

        except ValueError:

            return datetime.min


# ============================================================================
# PARSER
# ============================================================================

def parse_log(text):
    """
    Analiza un registro de NVDA.

    Cada línea que coincide con HEADER_RE comienza una nueva entrada.
    Las líneas siguientes pertenecen a esa entrada.
    """

    entries = []

    current = None
    in_traceback = False
    next_id = 1

    for line in text.splitlines():

        match = HEADER_RE.match(line)

        # ----------------------------------------------------------------
        # Nuevo encabezado
        # ----------------------------------------------------------------

        if match:

            if current is not None:
                entries.append(current)

            current = LogEntry(
                id=next_id,
                level=match.group("level"),
                source_raw=match.group("source"),
                time_text=match.group("time"),
                thread=match.group("thread"),
                pid=int(match.group("pid")),
            )

            next_id += 1
            in_traceback = False

            continue

        # ----------------------------------------------------------------
        # Todavía no hemos encontrado una entrada
        # ----------------------------------------------------------------

        if current is None:
            continue

        # ----------------------------------------------------------------
        # Traceback
        # ----------------------------------------------------------------

        if line.strip() == "Traceback (most recent call last):":

            in_traceback = True
            current.traceback.append(line)

        elif in_traceback:

            current.traceback.append(line)

        # ----------------------------------------------------------------
        # Mensaje
        # ----------------------------------------------------------------

        elif current.message:

            current.message += "\n" + line

        else:

            current.message = line

    # Añadir última entrada
    if current is not None:
        entries.append(current)

    return entries


# ============================================================================
# MODELO
# ============================================================================

class LogModel:

    LEVELS = (
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "DEBUGWARNING",
        "IO",
    )

    def __init__(self):

        self.entries = []

    def filtered(self, text_filter, levels):
        """
        Filtra las entradas.

        IMPORTANTE:

        El texto de búsqueda se compara con el encabezado,
        el mensaje y el traceback de la entrada.

        La búsqueda no distingue mayúsculas/minúsculas.
        """

        text_filter = text_filter.strip().casefold()

        result = []

        for entry in self.entries:

            # ------------------------------------------------------------
            # Filtro por nivel
            # ------------------------------------------------------------

            if entry.level not in levels:
                continue

            # ------------------------------------------------------------
            # Filtro por texto
            # ------------------------------------------------------------

            if text_filter:

                # Combina encabezado, mensaje y traceback para la búsqueda
                traceback_text = "\n".join(entry.traceback).casefold()
                content = f"{entry.header_text}\n{entry.message}\n{traceback_text}".casefold()

                if text_filter not in content:
                    continue

            result.append(entry)

        return result


class SettingsDialog(wx.Dialog):
    def __init__(self, parent, settings):
        super().__init__(parent, title=_("Ajustes"))
        self.settings = settings
        self.init_ui()

    def init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Sizer para el Editor
        editor_sizer = wx.BoxSizer(wx.HORIZONTAL)
        editor_sizer.Add(wx.StaticText(self, label=_("Editor de código:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.editor_path = wx.TextCtrl(self, value=self.settings.get('code_editor', ''))
        self.editor_path.Bind(wx.EVT_CHAR, self.on_text_char)
        editor_sizer.Add(self.editor_path, 1, wx.EXPAND | wx.ALL, 5)
        browse_editor = wx.Button(self, label=_("Examinar"))
        browse_editor.Bind(wx.EVT_BUTTON, self.on_browse_editor)
        editor_sizer.Add(browse_editor, 0, wx.ALL, 5)
        sizer.Add(editor_sizer, 0, wx.EXPAND)

        # Sizer para el Código fuente de NVDA
        nvda_sizer = wx.BoxSizer(wx.HORIZONTAL)
        nvda_sizer.Add(wx.StaticText(self, label=_("Código fuente de NVDA:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.nvda_path = wx.TextCtrl(self, value=self.settings.get('nvda_source', ''))
        self.nvda_path.Bind(wx.EVT_CHAR, self.on_text_char)
        nvda_sizer.Add(self.nvda_path, 1, wx.EXPAND | wx.ALL, 5)
        browse_nvda = wx.Button(self, label=_("Examinar"))
        browse_nvda.Bind(wx.EVT_BUTTON, self.on_browse_nvda)
        nvda_sizer.Add(browse_nvda, 0, wx.ALL, 5)
        sizer.Add(nvda_sizer, 0, wx.EXPAND)

        # Sizer para Carpeta de marcadores
        bookmarks_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bookmarks_sizer.Add(wx.StaticText(self, label=_("Carpeta de marcadores:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.bookmarks_path = wx.TextCtrl(self, value=self.settings.get('bookmarks_folder', 'bookmarks'))
        self.bookmarks_path.Bind(wx.EVT_CHAR, self.on_text_char)
        bookmarks_sizer.Add(self.bookmarks_path, 1, wx.EXPAND | wx.ALL, 5)
        browse_bookmarks = wx.Button(self, label=_("Examinar"))
        browse_bookmarks.Bind(wx.EVT_BUTTON, self.on_browse_bookmarks)
        bookmarks_sizer.Add(browse_bookmarks, 0, wx.ALL, 5)
        sizer.Add(bookmarks_sizer, 0, wx.EXPAND)

        # Sizer para Limpieza
        cleanup_sizer = wx.BoxSizer(wx.HORIZONTAL)
        cleanup_sizer.Add(wx.StaticText(self, label=_("Limpiar marcadores no usados en:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.cleanup_days = wx.SpinCtrl(self, value=str(self.settings.get('cleanup_days', 90)), min=1, max=365)
        cleanup_sizer.Add(self.cleanup_days, 0, wx.ALL, 5)
        cleanup_sizer.Add(wx.StaticText(self, label=_("Días")), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        sizer.Add(cleanup_sizer, 0, wx.EXPAND)

        # Botones Aceptar y Cancelar
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, label=_("Aceptar"))
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancelar"))
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Fit()
        self.Centre()

    def on_browse_editor(self, event):
        with wx.FileDialog(self, _("Seleccionar editor"), wildcard=_("Ejecutables (*.exe)|*.exe"), style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.editor_path.SetValue(dlg.GetPath())

    def on_browse_nvda(self, event):
        with wx.DirDialog(self, _("Seleccionar carpeta de NVDA")) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.nvda_path.SetValue(dlg.GetPath())
        
    def on_browse_bookmarks(self, event):
        with wx.DirDialog(self, _("Seleccionar carpeta de marcadores")) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.bookmarks_path.SetValue(dlg.GetPath())
        
    def get_values(self):
        return {
            'code_editor': self.editor_path.GetValue(),
            'nvda_source': self.nvda_path.GetValue(),
            'bookmarks_folder': self.bookmarks_path.GetValue(),
            'cleanup_days': self.cleanup_days.GetValue()
        }

    def on_text_char(self, event):
        key = event.GetKeyCode()
        # Permitir flechas (izquierda y derecha), y control+c (para copiar)
        if key in (wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_HOME, wx.WXK_END) or (event.ControlDown() and key == ord('C')):
            event.Skip()
        else:
            # Ignorar todas las demás teclas
            return

# ============================================================================
# VENTANA PRINCIPAL
# ============================================================================

class MainFrame(wx.Frame):

    def speak(self, text):
        nvdaControllerClient.message(text)

    def __init__(self):

        super().__init__(
            None,
            title=_("Visor de registros de NVDA"),
            size=(1250, 800),
        )

        self.model = LogModel()
        self.settings = self.load_settings()
        self.tree_entries = {}

        # Configuración de marcadores
        bookmarks_folder_path = self.settings.get('bookmarks_folder', 'bookmarks')
        self.bookmarks_folder = Path(bookmarks_folder_path)
        self.bookmarks_folder.mkdir(exist_ok=True)
        
        self.cleanup_old_bookmarks()

        self.current_log_hash = None

        # Flag para saber si los filtros han cambiado
        self.filters_dirty = False

        # Vista actual:
        #
        # source = Por origen
        # time   = Cronológico
        self.current_view = "source"

        self.build_menu()
        self.build_ui()
        self.bind_events()

        self.Centre()

        # ----------------------------------------------------------------
        # Ruta del archivo cargado actualmente
        # ----------------------------------------------------------------

        self.current_file_path = None

        # ----------------------------------------------------------------
        # Cargar automáticamente nvda.log en TEMP si existe
        # ----------------------------------------------------------------

        temp_log = Path.home() / "AppData" / "Local" / "Temp" / "nvda.log"

        if temp_log.exists():

            self.speak(_("Cargando registro"))
            self.load_file(temp_log)

    def get_log_hash(self, path):
        """Calcula el hash MD5 de los primeros 512 caracteres del archivo."""
        if not path.exists():
            return None
        
        with path.open("rb") as f:
            content = f.read(512)
        return hashlib.md5(content).hexdigest()

    def load_bookmarks(self):
        """Carga marcadores para el log actual."""
        # Limpiar menú de marcadores
        while self.bookmarks_menu.GetMenuItemCount() > 0:
            item = self.bookmarks_menu.FindItemByPosition(0)
            self.bookmarks_menu.Remove(item)
            
        self.bookmarks = []
        
        if not self.current_log_hash:
            return
            
        bookmark_file = self.bookmarks_folder / self.current_log_hash
        if not bookmark_file.exists():
            return
            
        with bookmark_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        os.utime(bookmark_file, (time.time(), time.time()))
            
        # Reconstruir el menú
        for entry in data:
            signature = entry['signature']
            label = entry.get('label', _("Marcador sin nombre"))
            
            bookmark_id = wx.NewIdRef()
            bookmark_item = self.bookmarks_menu.Append(bookmark_id, label)
            self.Bind(wx.EVT_MENU, lambda e, sig=signature: self.on_bookmark_selected(sig), bookmark_item)
            
            self.bookmarks.append({'signature': signature, 'menu_id': bookmark_id, 'label': label})

    def save_bookmarks(self):
        """Guarda los marcadores actuales en un archivo."""
        if not self.current_log_hash:
            return
            
        bookmark_file = self.bookmarks_folder / self.current_log_hash
        # IMPORTANTE: Asegurar que se guarda la etiqueta
        data = [{'signature': b['signature'], 'label': b['label']} for b in self.bookmarks]
        
        with bookmark_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load_settings(self):
        path = Path("settings.json")
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        
        # Initial setup if not exists
        settings = {
            'code_editor': str(self.get_vscode_path() or ''),
            'nvda_source': ''
        }
        return settings
    
    def cleanup_old_bookmarks(self):
        """Borra marcadores que no se han modificado en X días."""
        days = self.settings.get('cleanup_days', 90)
        now = datetime.now()
        
        for file in self.bookmarks_folder.glob("*"):
            if not file.is_file():
                continue
                
            # Usar tiempo de modificación
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            if (now - mtime).days > days:
                file.unlink()

    # ========================================================================
    # MENÚ
    # ========================================================================

    def build_menu(self):

        menubar = wx.MenuBar()

        # ----------------------------------------------------------------
        # Archivo
        # ----------------------------------------------------------------

        file_menu = wx.Menu()

        load_menu = wx.Menu()

        self.load_nvda_item = load_menu.Append(
            wx.ID_ANY,
            "nvda.log",
        )

        self.load_nvda_old_item = load_menu.Append(
            wx.ID_ANY,
            "nvda-old.log",
        )

        self.open_item = load_menu.Append(
            wx.ID_OPEN,
            _("&Otro archivo...\tCtrl+O"),
        )

        file_menu.Append(wx.MenuItem(file_menu, wx.ID_ANY, _("&Cargar registro"), subMenu=load_menu))

        self.reload_item = file_menu.Append(wx.MenuItem(file_menu, wx.ID_ANY, _("&Recargar registro\tF5")))

        self.settings_item = file_menu.Append(wx.MenuItem(file_menu, wx.ID_ANY, _("&Ajustes\tCtrl+S")))

        file_menu.AppendSeparator()

        self.exit_item = file_menu.Append(wx.MenuItem(file_menu, wx.ID_EXIT, _("&Salir\tCtrl+Q")))

        # ----------------------------------------------------------------
        # Vista
        # ----------------------------------------------------------------

        view_menu = wx.Menu()

        self.source_view_item = view_menu.AppendRadioItem(
            wx.ID_ANY,
            _("&Por origen"),
        )

        self.level_view_item = view_menu.AppendRadioItem(
            wx.ID_ANY,
            _("&Por nivel"),
        )

        self.time_view_item = view_menu.AppendRadioItem(
            wx.ID_ANY,
            _("&Cronológico"),
        )

        self.source_view_item.Check(True)

        view_menu.AppendSeparator()

        self.clear_filters_item = view_menu.Append(
            wx.ID_ANY,
            _("&Quitar filtros\tCtrl+Z"),
        )

        # ----------------------------------------------------------------
        # Marcadores
        # ----------------------------------------------------------------

        self.bookmarks_menu = wx.Menu()

        # ----------------------------------------------------------------
        # Añadir menús
        # ----------------------------------------------------------------

        menubar.Append(
            file_menu,
            _("&Archivo"),
        )

        menubar.Append(
            view_menu,
            _("&Vista"),
        )

        menubar.Append(
            self.bookmarks_menu,
            _("&Marcadores"),
        )

        self.SetMenuBar(menubar)

    # ========================================================================
    # INTERFAZ
    # ========================================================================

    def build_ui(self):

        panel = wx.Panel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ----------------------------------------------------------------
        # FILTROS
        # ----------------------------------------------------------------

        filter_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, _("Filtros"))

        # Texto
        filter_box.Add(wx.StaticText(panel, label=_("Filtro:")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.text_filter = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.text_filter.SetHint(_("Buscar en el registro"))
        filter_box.Add(self.text_filter, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)

        # Tipos
        type_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, _("Niveles"))
        self.level_checks = {}
        display_order = ["INFO", "WARNING", "ERROR", "DEBUGWARNING", "DEBUG", "IO"]

        for level in display_order:
            checkbox = wx.CheckBox(panel, label=level)
            checkbox.SetValue(True)
            self.level_checks[level] = checkbox
            type_box.Add(checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

        filter_box.Add(type_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

        main_sizer.Add(filter_box, 0, wx.EXPAND | wx.ALL, 8)

        # ----------------------------------------------------------------
        # ÁRBOL y DETALLE
        # ----------------------------------------------------------------

        # El árbol y el detalle compartirán el espacio. Usamos proporción 2:1.
        
        # Árbol
        self.view_label = wx.StaticText(panel, label=_("Vista Por origen"))
        main_sizer.Add(self.view_label, 0, wx.LEFT | wx.RIGHT, 8)
        
        self.tree = wx.TreeCtrl(panel, style=(wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT))
        main_sizer.Add(self.tree, proportion=2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        # Detalle
        detail_box = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Detalle"))
        self.detail = wx.TextCtrl(panel, style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL))
        detail_box.Add(self.detail, 1, wx.EXPAND)
        
        main_sizer.Add(detail_box, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        # ----------------------------------------------------------------
        # ESTADO
        # ----------------------------------------------------------------

        self.status = wx.StaticText(panel, label="Sin registro cargado.")
        main_sizer.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        panel.SetSizer(main_sizer)


    # ========================================================================
    # EVENTOS
    # ========================================================================

    def bind_events(self):

        self.Bind(
            wx.EVT_MENU,
            lambda event: self.load_file(Path.home() / "AppData" / "Local" / "Temp" / "nvda.log"),
            self.load_nvda_item,
        )

        self.Bind(
            wx.EVT_MENU,
            lambda event: self.load_file(Path.home() / "AppData" / "Local" / "Temp" / "nvda-old.log"),
            self.load_nvda_old_item,
        )

        self.Bind(
            wx.EVT_MENU,
            self.on_open,
            self.open_item,
        )

        self.Bind(
            wx.EVT_MENU,
            self.on_reload,
            self.reload_item,
        )

        self.Bind(
            wx.EVT_MENU,
            self.on_settings,
            self.settings_item,
        )

        self.Bind(
            wx.EVT_MENU,
            lambda event: self.Close(),
            self.exit_item,
        )

        self.Bind(
            wx.EVT_MENU,
            lambda event: self.change_view("source"),
            self.source_view_item,
        )

        self.Bind(
            wx.EVT_MENU,
            lambda event: self.change_view("time"),
            self.time_view_item,
        )

        self.Bind(
            wx.EVT_MENU,
            lambda event: self.change_view("level"),
            self.level_view_item,
        )

        self.Bind(
            wx.EVT_MENU,
            self.on_clear_filters,
            self.clear_filters_item,
        )

        # ------------------------------------------------------------
        # Filtro de texto
        # ------------------------------------------------------------

        self.text_filter.Bind(
            wx.EVT_TEXT,
            lambda event: self.mark_dirty(),
        )

        self.text_filter.Bind(
            wx.EVT_TEXT_ENTER,
            self.on_filter_enter,
        )

        # ------------------------------------------------------------
        # Casillas de nivel
        # ------------------------------------------------------------

        for checkbox in self.level_checks.values():

            checkbox.Bind(
                wx.EVT_CHECKBOX,
                lambda event: (self.mark_dirty(), event.Skip()),
            )

        # ------------------------------------------------------------
        # Detalle
        # ------------------------------------------------------------

        self.detail.Bind(
            wx.EVT_CHAR_HOOK,
            self.on_detail_key,
        )

        # ------------------------------------------------------------
        # Árbol
        # ------------------------------------------------------------

        self.tree.Bind(
            wx.EVT_TREE_SEL_CHANGED,
            self.on_tree_selection,
        )

        self.tree.Bind(
            wx.EVT_CONTEXT_MENU,
            self.on_tree_context_menu,
        )

        self.tree.Bind(
            wx.EVT_SET_FOCUS,
            self.on_tree_focus,
        )

        # ------------------------------------------------------------
        # Teclado
        # ------------------------------------------------------------

        self.Bind(
            wx.EVT_CHAR_HOOK,
            self.on_key,
        )

    def mark_dirty(self):
        self.filters_dirty = True

    def on_clear_filters(self, event):

        self.text_filter.Clear()

        for checkbox in self.level_checks.values():

            checkbox.SetValue(True)

        self.refresh()
        self.filters_dirty = False
        self.speak(_("Filtros eliminados"))

    def on_tree_focus(self, event):

        if self.filters_dirty:

            self.refresh()
            self.filters_dirty = False

        event.Skip()

    def on_filter_enter(self, event):

        self.tree.SetFocus()

    def on_key(self, event):

        key_code = event.GetKeyCode()
        control_down = event.ControlDown()

        # F1: Abrir ayuda
        if key_code == wx.WXK_F1:
            self.on_help(event)
            return

        # Ctrl+O: Abrir registro
        if control_down and key_code == ord("O"):
            self.on_open(event)
            return

        # Ctrl+F: Foco en filtro
        elif control_down and key_code == ord("F"):
            self.text_filter.SetFocus()
            return
            
        # Ctrl+T: Foco en árbol
        elif control_down and key_code == ord("T"):
            self.tree.SetFocus()
            return

        # Ctrl+M: Alternar marcador
        elif control_down and key_code == ord("M"):
            item = self.tree.GetSelection()
            if item.IsOk():
                self.on_toggle_bookmark(item)
            return

        # Ctrl+1..6: Alternar checkboxes de filtro
        elif control_down and ord("1") <= key_code <= ord("6") and self.tree.HasFocus():
            
            index = key_code - ord("1")
            levels = ["INFO", "WARNING", "ERROR", "DEBUGWARNING", "DEBUG", "IO"]
            
            if index < len(levels):
                level = levels[index]
                checkbox = self.level_checks.get(level)
                
                if checkbox:
                    new_value = not checkbox.GetValue()
                    checkbox.SetValue(new_value)

                    state = _("activado") if new_value else _("desactivado")
                    self.speak(_("{}, {}").format(level, state))

                    self.mark_dirty()
                    self.refresh()
            return

        # F6: Cambiar vista
        elif key_code == wx.WXK_F6:

            # Orden: Origen -> Nivel -> Cronológico
            if self.current_view == "source":
                next_view = "level"
            elif self.current_view == "level":
                next_view = "time"
            else:
                next_view = "source"

            self.change_view(next_view)

            # Actualizar radio buttons del menú
            self.source_view_item.Check(self.current_view == "source")
            self.level_view_item.Check(self.current_view == "level")
            self.time_view_item.Check(self.current_view == "time")
            
            view_names = {"source": _("Vista por origen"), "level": _("Vista por niveles"), "time": _("Vista cronológica")}
            self.speak(view_names[next_view])
            return

        event.Skip()

    def on_help(self, event):
        # Determinar el archivo README adecuado
        from l10n import lancode
        readme_path = Path(f"doc/{lancode}/README.md")
        if not readme_path.exists():
            readme_path = Path("README.md")
            
        if not readme_path.exists():
            self.speak(_("No se pudo encontrar el archivo de ayuda"))
            return

        # Convertir Markdown a HTML
        with readme_path.open("r", encoding="utf-8") as f:
            md_content = f.read()
        
        html_content = markdown.markdown(md_content, extensions=['extra'])
        
        # Guardar como archivo temporal HTML
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as tmp:
            tmp.write(f"<html><body>{html_content}</body></html>")
            tmp_path = tmp.name
        
        # Abrir en el navegador
        webbrowser.open(f"file://{tmp_path}")



    # ========================================================================
    # CAMBIO DE VISTA
    # ========================================================================

    def change_view(self, view):

        self.current_view = view
        
        view_names = {"source": _("Por origen"), "level": _("Por nivel"), "time": _("Cronológica")}
        self.view_label.SetLabel(_("Vista {}").format(view_names[view]))

        self.refresh()

    # ========================================================================
    # ARCHIVOS
    # ========================================================================

    def on_open(self, event):

        dialog = wx.FileDialog(
            self,
            "Abrir registro de NVDA",
            wildcard=(
                "Registros (*.txt;*.log)|*.txt;*.log|"
                "Todos los archivos (*.*)|*.*"
            ),
            style=(
                wx.FD_OPEN
                | wx.FD_FILE_MUST_EXIST
            ),
        )

        try:

            if dialog.ShowModal() != wx.ID_OK:
                return

            path = Path(
                dialog.GetPath()
            )

        finally:

            dialog.Destroy()

        self.load_file(path)

    def on_reload(self, event):

        if self.current_file_path and self.current_file_path.exists():

            self.load_file(self.current_file_path)

    def save_settings(self, settings):
        with open("settings.json", "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        self.settings = settings

    def on_settings(self, event):
        with SettingsDialog(self, self.settings) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                new_settings = dlg.get_values()
                self.save_settings(new_settings)
                
                if 'bookmarks_folder' in new_settings:
                    self.bookmarks_folder = Path(new_settings['bookmarks_folder'])
                    self.bookmarks_folder.mkdir(exist_ok=True)

    def load_file(self, path):

        # Silenciar voz actual antes de cargar
        if nvdaControllerClient.clientLib:
            nvdaControllerClient.clientLib.nvdaController_cancelSpeech()

        try:

            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except OSError as error:

            wx.MessageBox(
                f"No se pudo abrir el archivo:\n\n{error}",
                "Error",
                wx.OK | wx.ICON_ERROR,
            )

            return

        self.model.entries = parse_log(text)

        is_reload = (self.current_file_path == path)
        
        # Solo cargar marcadores si el archivo ha cambiado
        if not is_reload:
            self.current_file_path = path
            self.current_log_hash = self.get_log_hash(path)
            self.load_bookmarks()
        else:
            self.current_file_path = path

        self.refresh()

        message = _("Registro recargado") if is_reload else _("Registro cargado")
        wx.CallLater(100, lambda: self.speak(_("{}, {} entradas").format(message, len(self.model.entries))))

        self.SetTitle(
            _("Visor de registros de NVDA — {}").format(path.name)
        )

        self.tree.SetFocus()

    # ========================================================================
    # FILTROS
    # ========================================================================

    def selected_levels(self):

        result = set()

        for level, checkbox in self.level_checks.items():

            if checkbox.GetValue():
                result.add(level)

        return result

    # ========================================================================
    # ACTUALIZAR
    # ========================================================================

    def refresh(self):

        entries = self.model.filtered(
            self.text_filter.GetValue(),
            self.selected_levels(),
        )

        self.tree_entries.clear()

        if self.current_view == "source":

            self.populate_source_tree(
                entries
            )

        elif self.current_view == "level":
            
            self.populate_level_tree(
                entries
            )

        else:

            self.populate_time_tree(
                entries
            )

        # ----------------------------------------------------------------
        # ESTADO
        # ----------------------------------------------------------------

        file_name = (
            self.current_file_path.name
            if self.current_file_path and self.current_file_path.exists()
            else "Sin archivo"
        )

        status_text = _("{} | {} entradas").format(file_name, len(entries))

        if entries:

            last_entry = entries[-1]

            status_text += _(" | Última entrada: {}").format(last_entry.time_text)

        self.status.SetLabel(status_text)

    # ========================================================================
    # VISTA POR NIVEL
    # ========================================================================

    def populate_level_tree(self, entries):
        self.tree.DeleteAllItems()
        self.detail.Clear()

        root = self.tree.AddRoot("Registro por nivel")

        # Agrupar por nivel -> modulo
        groups = {}
        for entry in entries:
            groups.setdefault(entry.level, {}).setdefault(entry.module, []).append(entry)

        # Ordenar niveles para visualización
        for level in LogModel.LEVELS:
            if level not in groups:
                continue
            
            level_node = self.tree.AppendItem(root, level)
            
            modules = groups[level]
            for module in sorted(modules.keys()):
                module_entries = modules[module]
                
                module_node = self.tree.AppendItem(level_node, f"{module} ({len(module_entries)})")
                
                for entry in module_entries:
                    node = self.tree.AppendItem(module_node, self.entry_label(entry))
                    self.tree_entries[node] = entry
        
        # Enfocar el primer elemento si existe.
        child, cookie = self.tree.GetFirstChild(root)
        if child.IsOk():
            self.tree.SelectItem(child)
            self.tree.SetFocus()


    # ========================================================================
    # VISTA POR ORIGEN
    # ========================================================================

    def populate_source_tree(self, entries):

        self.tree.DeleteAllItems()

        self.detail.Clear()

        root = self.tree.AddRoot(
            _("Registro de NVDA")
        )

        global_commands_node = None
        nvda_node = None
        global_plugins_node = None
        app_modules_node = None

        # ----------------------------------------------------------------
        # Procesar entradas especiales (en la raíz)
        # ----------------------------------------------------------------

        special_entries = [
            entry for entry in entries
            if entry.source_raw == "globalCommands.script_navigatorObject_devInfo"
        ]

        if special_entries:
            special_entries.sort(key=lambda e: e.sort_time, reverse=True)
            special_entries = [special_entries[0]]

        for entry in special_entries:

            node = self.tree.AppendItem(
                root,
                _("Developer info for navigator object"),
            )

            self.tree_entries[node] = entry

        # ----------------------------------------------------------------
        # Agrupar entradas normales
        # ----------------------------------------------------------------

        groups = {}

        for entry in entries:

            if entry.source_raw == "globalCommands.script_navigatorObject_devInfo":
                continue

            if entry.source_type == "NVDA":

                key = (
                    "NVDA",
                    entry.module,
                )

            else:

                key = (
                    entry.source_type,
                    entry.addon,
                )

            groups.setdefault(
                key,
                [],
            ).append(entry)

        # ----------------------------------------------------------------
        # Crear grupos de categorías
        # ----------------------------------------------------------------

        def sort_key(item):
            # Orden:
            # 1: NVDA
            # 2: Global Plugins
            # 3: App Modules

            type_order = {
                "NVDA": 1,
                "Global Plugin": 2,
                "App Module": 3,
            }

            return (
                type_order.get(item[0], 99),
                item[1].lower(),
            )

        for (
            source_type,
            source_name,
        ) in sorted(
            groups.keys(),
            key=sort_key,
        ):

            group_entries = groups[
                (source_type, source_name)
            ]

            # --------------------------------------------------------
            # GLOBAL COMMANDS
            # --------------------------------------------------------

            if source_type == "Global Commands":

                if global_commands_node is None:

                    global_commands_node = self.tree.AppendItem(
                        root,
                        _("Global Commands"),
                    )

                emitter_node = global_commands_node

            # --------------------------------------------------------
            # NVDA
            # --------------------------------------------------------

            elif source_type == "NVDA":

                if nvda_node is None:

                    nvda_node = self.tree.AppendItem(
                        root,
                        "NVDA",
                    )

                emitter_node = self.tree.AppendItem(
                    nvda_node,
                    source_name,
                )

            # --------------------------------------------------------
            # GLOBAL PLUGINS
            # --------------------------------------------------------

            elif source_type == "Global Plugin":

                if global_plugins_node is None:

                    global_plugins_node = self.tree.AppendItem(
                        root,
                        _("Global Plugins"),
                    )

                emitter_node = self.tree.AppendItem(
                    global_plugins_node,
                    source_name,
                )

            # --------------------------------------------------------
            # APP MODULES
            # --------------------------------------------------------

            else:

                if app_modules_node is None:

                    app_modules_node = self.tree.AppendItem(
                        root,
                        _("App Modules"),
                    )

                emitter_node = self.tree.AppendItem(
                    app_modules_node,
                    source_name,
                )

            # --------------------------------------------------------
            # NIVELES
            # --------------------------------------------------------

            for level in LogModel.LEVELS:

                level_entries = [
                    entry
                    for entry in group_entries
                    if entry.level == level
                ]

                if not level_entries:
                    continue

                if source_type == "Global Commands":

                    level_node = emitter_node

                else:

                    level_node = self.tree.AppendItem(
                        emitter_node,
                        _("{} ({})").format(level, len(level_entries)),
                    )

                for entry in level_entries:

                    node = self.tree.AppendItem(
                        level_node,
                        self.entry_label(entry),
                    )

                    self.tree_entries[node] = entry

        # Enfocar el primer elemento si existe.
        child, cookie = self.tree.GetFirstChild(root)
        if child.IsOk():
            self.tree.SelectItem(child)
            self.tree.SetFocus()

    # ========================================================================
    # VISTA CRONOLÓGICA
    # ========================================================================

    def populate_time_tree(self, entries):

        self.tree.DeleteAllItems()
        self.detail.Clear()

        root = self.tree.AddRoot(_("Registro cronológico"))

        # Agrupar: hora -> minuto -> entradas
        groups = {}
        for entry in sorted(entries, key=lambda item: item.sort_time):
            # Formato time_text: HH:MM:SS.mmm
            parts = entry.time_text.split(':')
            hour = parts[0]
            minute = parts[1]
            
            groups.setdefault(hour, {}).setdefault(minute, []).append(entry)

        # Construir el árbol
        for hour in sorted(groups.keys()):
            hour_node = self.tree.AppendItem(root, f"{hour}:00")
            
            minutes = groups[hour]
            for minute in sorted(minutes.keys()):
                minute_entries = minutes[minute]
                minute_node = self.tree.AppendItem(hour_node, _("{}:{} ({})").format(hour, minute, len(minute_entries)))
                
                for entry in minute_entries:
                    node = self.tree.AppendItem(minute_node, self.entry_label(entry))
                    self.tree_entries[node] = entry
            
            self.tree.Expand(hour_node)

        # Enfocar el primer elemento si existe.
        child, cookie = self.tree.GetFirstChild(root)
        if child.IsOk():
            self.tree.SelectItem(child)
            self.tree.SetFocus()
    # ========================================================================
    # TEXTO DE LAS ENTRADAS
    # ========================================================================

    @staticmethod
    def entry_label(entry):

        message = ""

        if entry.message:

            message = (
                entry.message
                .splitlines()[0]
                .strip()
            )

        return (
            f"{entry.time_text} — "
            f"{entry.display_emitter} — "
            f"{entry.level} — "
            f"{message}"
        )

    def on_tree_context_menu(self, event):

        item = self.tree.GetSelection()

        if not item.IsOk():
            return

        menu = wx.Menu()

        signature = self.get_node_signature(item)
        is_bookmarked = any(b['signature'] == signature for b in self.bookmarks)
        
        if is_bookmarked:
            bookmark_item = menu.Append(wx.ID_ANY, _("Quitar de marcadores"))
            self.Bind(wx.EVT_MENU, lambda e: self.on_remove_bookmark(signature), bookmark_item)
        else:
            bookmark_item = menu.Append(wx.ID_ANY, _("Añadir a marcadores"))
            self.Bind(wx.EVT_MENU, lambda e: self.on_add_bookmark(item), bookmark_item)

        if self.current_view in ("source", "level", "time"):

            export_item = menu.Append(wx.ID_ANY, _("Exportar"))
            self.Bind(wx.EVT_MENU, lambda e: self.on_export(item), export_item)

        clear_filters_item = menu.Append(wx.ID_ANY, _("Quitar filtros"))
        self.Bind(wx.EVT_MENU, self.on_clear_filters, clear_filters_item)

        self.PopupMenu(menu)
        menu.Destroy()
    
    def get_node_path(self, node):
        """Obtiene la ruta jerárquica de un nodo."""
        path = []
        current = node
        while current.IsOk() and current != self.tree.GetRootItem():
            path.insert(0, self.tree.GetItemText(current))
            current = self.tree.GetItemParent(current)
        return "/".join(path)

    def get_entry_hash(self, entry):
        """Genera un hash único basado en el contenido de la entrada."""
        content = f"{entry.level}{entry.source_raw}{entry.time_text}{entry.thread}{entry.pid}{entry.message}"
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def get_node_signature(self, node):
        """Genera una firma robusta para un nodo."""
        if node == self.tree.GetRootItem():
            return {"type": "root", "view": self.current_view}
            
        signature = {"view": self.current_view}
        if node in self.tree_entries:
            # Entrada: usar hash de contenido
            signature.update({
                "type": "entry", 
                "hash": self.get_entry_hash(self.tree_entries[node])
            })
        else:
            # Grupo: usar la ruta de nombres sin contadores dinámicos
            path = []
            current = node
            while current.IsOk() and current != self.tree.GetRootItem():
                text = self.tree.GetItemText(current)
                # Limpiar contador si existe (ej: "INFO (6)" -> "INFO")
                text = re.sub(r"\s+\(\d+\)$", "", text)
                path.insert(0, text)
                current = self.tree.GetItemParent(current)
                
            signature.update({
                "type": "group", 
                "path": path
            })
        return signature

    def on_add_bookmark(self, node):
        signature = self.get_node_signature(node)
        raw_label = self.get_node_path(node) # Usamos la ruta completa
        
        # Limpiar la etiqueta:
        # 1. Eliminar contador de entradas tipo " (6)" al final.
        # 2. Eliminar cualquier formato de entrada que termina con ")" o similar si es necesario.
        # Intentemos una limpieza más agresiva al final de la etiqueta.
        
        # Regex: busca " (número)" al final, o patrones complejos de entrada.
        # Si es una entrada, el label es el resultado de entry_label.
        # Intentemos simplemente quitar lo que esté entre paréntesis al final si parece un contador.
        
        # Caso de grupo: "Nombre (6)" -> "Nombre"
        label = re.sub(r"\s+\(\d+\)$", "", raw_label)
        
        # Caso de entrada: "17:42:04.341 — NVDA — INFO — Mensaje..."
        # Si es una entrada, GetNodePath devuelve una ruta tipo "NVDA/INFO/17:42:04.341 — NVDA — INFO — Mensaje..."
        # El usuario quiere limpiar la parte final.
        
        # Si el label sigue teniendo la estructura de una entrada, limpiamos.
        # Basado en el ejemplo: "... — ActualizadorRecursos: comprobando actualizaciones... )"
        # Parece que hay una parte final que sobra.
        
        if " — " in label:
            # Es probable que sea una entrada, tomamos la parte descriptiva.
            parts = label.split(" — ")
            # Ejemplo: ["17:42:04.341", "NVDA", "INFO", "Mensaje...)"]
            # Tomamos el mensaje y quitamos el ")" final si existe
            if len(parts) >= 4:
                label = parts[-1].rstrip(" )")
        
        # Evitar duplicados
        if any(b['signature'] == signature for b in self.bookmarks):
            self.speak(_("Ya existe ese marcador"))
            return
            
        bookmark_id = wx.NewIdRef()
        bookmark_item = self.bookmarks_menu.Append(bookmark_id, label)
        self.Bind(wx.EVT_MENU, lambda e: self.on_bookmark_selected(signature), bookmark_item)
        
        self.bookmarks.append({'signature': signature, 'menu_id': bookmark_id, 'label': label})
        self.save_bookmarks()
        self.speak(_("Marcador añadido"))

    def on_remove_bookmark(self, signature):
        bookmark = next((b for b in self.bookmarks if b['signature'] == signature), None)
        if bookmark:
            self.bookmarks_menu.Remove(bookmark['menu_id'])
            self.bookmarks.remove(bookmark)
            self.save_bookmarks()
            self.speak(_("Marcador eliminado"))

    def on_toggle_bookmark(self, node):
        signature = self.get_node_signature(node)
        if any(b['signature'] == signature for b in self.bookmarks):
            self.on_remove_bookmark(signature)
        else:
            self.on_add_bookmark(node)

    def on_bookmark_selected(self, signature):
        # 1. Guardar estado inicial (vista y selección) como "marcador temporal"
        initial_selection = self.tree.GetSelection()
        initial_signature = self.get_node_signature(initial_selection) if initial_selection.IsOk() else None
        
        # Helper para restaurar el estado inicial
        def restore_initial_state():
            if initial_signature:
                # Restaurar vista
                if self.current_view != initial_signature['view']:
                    self.change_view(initial_signature['view'])
                    self.source_view_item.Check(self.current_view == "source")
                    self.level_view_item.Check(self.current_view == "level")
                    self.time_view_item.Check(self.current_view == "time")
                
                # Restaurar selección
                root = self.tree.GetRootItem()
                def find_node_by_sig(node, target_sig):
                    if self.get_node_signature(node) == target_sig:
                        return node
                    child, cookie = self.tree.GetFirstChild(node)
                    while child.IsOk():
                        found = find_node_by_sig(child, target_sig)
                        if found: return found
                        child, cookie = self.tree.GetNextChild(node, cookie)
                    return None
                    
                target = find_node_by_sig(root, initial_signature)
                if target:
                    self.tree.SelectItem(target)
                    self.tree.EnsureVisible(target)
                    self.tree.SetFocus()

        # 2. Intentar navegar al marcador destino
        # Cambiar vista
        if self.current_view != signature['view']:
            self.change_view(signature['view'])
            self.source_view_item.Check(self.current_view == "source")
            self.level_view_item.Check(self.current_view == "level")
            self.time_view_item.Check(self.current_view == "time")

        # Buscar el nodo
        root = self.tree.GetRootItem()
        def find_node(node):
            if self.get_node_signature(node) == signature:
                return node
            child, cookie = self.tree.GetFirstChild(node)
            while child.IsOk():
                found = find_node(child)
                if found: return found
                child, cookie = self.tree.GetNextChild(node, cookie)
            return None
            
        target = find_node(root)
        
        if target:
            self.tree.SelectItem(target)
            self.tree.EnsureVisible(target)
            self.tree.SetFocus()
            # Éxito: el estado temporal se descarta implícitamente
        else:
            # Comprobar filtros
            filters_active = self.text_filter.GetValue() != "" or any(not checkbox.GetValue() for checkbox in self.level_checks.values())
            
            if filters_active:
                msg = _("No se puede acceder al marcador con este filtro aplicado. ¿Quieres quitar el filtro?")
                dlg = wx.MessageDialog(self, msg, _("Marcador no encontrado"), wx.YES_NO | wx.ICON_QUESTION)
                if dlg.ShowModal() == wx.ID_YES:
                    self.on_clear_filters(None)
                    # Intentar buscar de nuevo
                    target = find_node(root)
                    if target:
                        self.tree.SelectItem(target)
                        self.tree.EnsureVisible(target)
                        self.tree.SetFocus()
                        return # Éxito
            
            # Fallo o usuario dijo no
            self.speak(_("No se pudo encontrar el marcador en la vista actual"))
            restore_initial_state()



    def get_all_entries_under_node(self, node):

        entries = []

        if node in self.tree_entries:
            entries.append(self.tree_entries[node])

        child, cookie = self.tree.GetFirstChild(node)

        while child.IsOk():

            entries.extend(self.get_all_entries_under_node(child))

            child, cookie = self.tree.GetNextChild(node, cookie)

        return entries

    def on_export(self, node):

        entries = self.get_all_entries_under_node(node)

        if not entries:
            return

        dialog = wx.FileDialog(
            self,
            _("Guardar registro como"),
            wildcard=_("Archivo de texto (*.txt;*.log)|*.txt;*.log"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )

        try:

            if dialog.ShowModal() != wx.ID_OK:
                return

            path = Path(dialog.GetPath())

            with path.open("w", encoding="utf-8") as f:

                for entry in sorted(entries, key=lambda e: e.sort_time):
                    f.write(entry.header_text + "\n")

                    if entry.message:
                        f.write(entry.message + "\n")

                    if entry.traceback:
                        f.write("\n".join(entry.traceback) + "\n")

                    f.write("\n")

        finally:

            dialog.Destroy()

    def get_vscode_path(self):

        code = shutil.which("code")

        if code:
            vscode = Path(code).parent.parent / "Code.exe"
            return vscode

        return None

    def on_detail_key(self, event):
        key = event.GetKeyCode()

        # Navegación entre entradas: AvPág (PageDown) y RePág (PageUp)
        if key in (wx.WXK_PAGEDOWN, wx.WXK_PAGEUP):
            content = self.detail.GetValue()
            pos = self.detail.GetInsertionPoint()
            
            separator = "-" * 40
            
            # Buscar todas las posiciones de los separadores
            separators = [m.start() for m in re.finditer(re.escape(separator), content)]
            
            if not separators:
                event.Skip()
                return

            if key == wx.WXK_PAGEDOWN:
                # Siguiente entrada
                # Posición después del separador actual (si estamos sobre uno)
                # O buscar el siguiente separador.
                
                # Encontramos el primer separador que esté después de la posición actual del cursor.
                for s_pos in separators:
                    if s_pos > pos:
                        # Saltar el separador (40 chars) + salto de línea (1 char)
                        target = s_pos + len(separator) + 1
                        self.detail.SetInsertionPoint(target)
                        self.detail.ShowPosition(target)
                        return
                
                # Si estamos después del último separador, o no hay más, avisar
                self.speak(_("No hay más entradas"))
            else:
                # Anterior entrada
                
                # Buscamos el separador inmediatamente anterior a la posición actual.
                # Si estamos dentro de una entrada (después de un separador), vamos al inicio de esa entrada.
                # Si estamos al inicio de una entrada (justo después de un separador), vamos al inicio de la anterior.
                
                # Posición del separador que precede o define el inicio de la entrada actual
                found_s_pos = -1
                
                # Encontrar el separador previo más cercano a pos
                for s_pos in reversed(separators):
                    if s_pos < pos:
                        found_s_pos = s_pos
                        break
                
                # Si encontramos un separador antes, vamos al inicio de esa entrada
                # Si no, vamos al inicio del documento
                if found_s_pos != -1:
                    # Si el cursor está justo al inicio de la entrada (inmediatamente después del separador)
                    # buscamos el separador anterior para retroceder más.
                    if pos == found_s_pos + len(separator) + 1:
                        # Buscar el separador anterior a found_s_pos
                        prev_s_pos = -1
                        for s_pos in reversed(separators):
                            if s_pos < found_s_pos:
                                prev_s_pos = s_pos
                                break
                        
                        if prev_s_pos != -1:
                            target = prev_s_pos + len(separator) + 1
                        else:
                            target = 0
                    else:
                        target = found_s_pos + len(separator) + 1
                else:
                    target = 0
                
                self.detail.SetInsertionPoint(target)
                self.detail.ShowPosition(target)
                if target == 0:
                    self.speak(_("Primera entrada"))
            
            event.Skip()
            return

        if key == wx.WXK_SPACE:

            # Obtener línea actual
            pos = self.detail.GetInsertionPoint()
            success, col, line_no = self.detail.PositionToXY(pos)
            
            line_text = self.detail.GetLineText(line_no)

            # Analizar con Regex
            match = TRACEBACK_FILE_RE.search(line_text)

            if match:
                path_str = match.group("path")
                line = match.group("line")
                path = Path(path_str)

                # Si no existe, intentar buscar en fuente de NVDA si es .pyc
                target_path = None
                if not path.exists() and path.suffix == ".pyc":
                    nvda_source = self.settings.get('nvda_source')
                    if nvda_source:
                        # La estrategia es simple: unir la base de la fuente configurada
                        # con la ruta relativa completa del traceback, cambiando .pyc por .py
                        # Si el log trae 'comtypes/_vtbl.pyc', target_path será
                        # 'C:\...\source\comtypes\_vtbl.py'
                        
                        relative_part = path.with_suffix('.py')
                        target_path = Path(nvda_source) / relative_part
                    
                    print(f"Depuración - Path original: {path}, Path destino calculado: {target_path}")
                
                final_path = target_path if (target_path and target_path.exists()) else (path if path.exists() else None)

                if final_path:
                    vscode_path = self.settings.get('code_editor')
                    vscode = Path(vscode_path) if vscode_path else self.get_vscode_path()

                    if vscode and vscode.exists():
                        # Detectar si es VS Code por el nombre del ejecutable
                        # Envolver las rutas entre comillas para manejar espacios
                        if vscode.name.lower() in ("code.exe", "code"):
                            os.system(f'start "" "{vscode}" -g "{final_path}:{line}"')
                        else:
                            os.system(f'start "" "{vscode}" "{final_path}"')
                        return
                    else:
                        wx.MessageBox(
                            _("No se pudo encontrar el editor configurado."),
                            _("Error"),
                            wx.OK | wx.ICON_ERROR,
                        )

        event.Skip()

    # ========================================================================
    # DETALLE
    # ========================================================================

    def on_tree_selection(self, event):

        item = event.GetItem()

        if not item.IsOk():
            return

        entries = self.get_all_entries_under_node(item)
        if not entries:
            self.detail.Clear()
            return

        if len(entries) == 1:
            entry = entries[0]
            lines = [
                _("Nivel: {}").format(entry.level),
                _("Hora: {}").format(entry.time_text),
                _("Hilo: {}").format(entry.thread),
                _("PID: {}").format(entry.pid),
                "",
                _("Origen: {}").format(entry.source_type),
                _("Emisor: {}").format(entry.display_emitter),
                _("Módulo: {}").format(entry.module),
                _("Fuente: {}").format(entry.source_raw),
                "",
                _("Encabezado:"),
                entry.header_text,
                "",
                _("Mensaje:"),
                entry.message or _("(sin mensaje)"),
            ]

            if entry.traceback:
                lines.extend([
                    "",
                    _("Traceback:"),
                ])
                lines.extend(entry.traceback)

            self.detail.SetValue("\n".join(lines))

        else:
            # Detalles completos de múltiples entradas
            lines = []
            for entry in sorted(entries, key=lambda e: e.sort_time):
                lines.append(entry.header_text)
                if entry.message:
                    lines.append(entry.message)
                if entry.traceback:
                    lines.extend(entry.traceback)
                lines.append("-" * 40) # Separador visual
            self.detail.SetValue("\n".join(lines))


# ============================================================================
# APLICACIÓN
# ============================================================================

class App(wx.App):

    def OnInit(self):

        frame = MainFrame()

        frame.Show()

        return True


if __name__ == "__main__":

    app = App(False)
    app.MainLoop()
