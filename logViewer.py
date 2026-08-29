from pathlib import Path
import shutil
import os
import re
import wx

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


# ============================================================================
# VENTANA PRINCIPAL
# ============================================================================

class MainFrame(wx.Frame):

    def __init__(self):

        super().__init__(
            None,
            title="Visor de registros de NVDA",
            size=(1250, 800),
        )

        self.model = LogModel()

        # Nodo del árbol -> LogEntry
        self.tree_entries = {}

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

            self.load_file(temp_log)

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
            "&Otro archivo...\tCtrl+O",
        )

        file_menu.Append(wx.MenuItem(file_menu, wx.ID_ANY, "&Cargar registro", subMenu=load_menu))

        self.reload_item = file_menu.Append(wx.MenuItem(file_menu, wx.ID_ANY, "&Recargar registro\tF5"))

        file_menu.AppendSeparator()

        self.exit_item = file_menu.Append(wx.MenuItem(file_menu, wx.ID_EXIT, "&Salir\tAlt+F4"))

        # ----------------------------------------------------------------
        # Vista
        # ----------------------------------------------------------------

        view_menu = wx.Menu()

        self.source_view_item = view_menu.AppendRadioItem(
            wx.ID_ANY,
            "&Por origen",
        )

        self.time_view_item = view_menu.AppendRadioItem(
            wx.ID_ANY,
            "&Cronológico",
        )

        self.level_view_item = view_menu.AppendRadioItem(
            wx.ID_ANY,
            "&Por nivel",
        )

        self.source_view_item.Check(True)

        view_menu.AppendSeparator()

        self.clear_filters_item = view_menu.Append(
            wx.ID_ANY,
            "&Quitar filtros\tCtrl+Z",
        )

        # ----------------------------------------------------------------
        # Añadir menús
        # ----------------------------------------------------------------

        menubar.Append(
            file_menu,
            "&Archivo",
        )

        menubar.Append(
            view_menu,
            "&Vista",
        )

        self.SetMenuBar(menubar)

    # ========================================================================
    # INTERFAZ
    # ========================================================================

    def build_ui(self):

        panel = wx.Panel(self)

        main_sizer = wx.BoxSizer(
            wx.VERTICAL
        )

        # ----------------------------------------------------------------
        # FILTROS
        # ----------------------------------------------------------------

        filter_box = wx.StaticBoxSizer(
            wx.HORIZONTAL,
            panel,
            "Filtros",
        )

        # ------------------------------------------------------------
        # Texto
        # ------------------------------------------------------------

        filter_box.Add(
            wx.StaticText(
                panel,
                label="Texto:",
            ),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            6,
        )

        self.text_filter = wx.TextCtrl(
            panel,
            style=wx.TE_PROCESS_ENTER,
        )

        self.text_filter.SetHint(
            "Buscar en los encabezados"
        )

        filter_box.Add(
            self.text_filter,
            1,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            20,
        )

        # ------------------------------------------------------------
        # Tipos
        # ------------------------------------------------------------

        type_box = wx.StaticBoxSizer(
            wx.HORIZONTAL,
            panel,
            "Tipo",
        )

        self.level_checks = {}

        # Definir el orden específico para la interfaz
        display_order = ["INFO", "WARNING", "ERROR", "DEBUGWARNING", "DEBUG", "IO"]

        for level in display_order:

            checkbox = wx.CheckBox(
                panel,
                label=level,
            )

            checkbox.SetValue(True)

            self.level_checks[level] = checkbox

            type_box.Add(
                checkbox,
                0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
                12,
            )

        filter_box.Add(
            type_box,
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            10,
        )

        main_sizer.Add(
            filter_box,
            0,
            wx.EXPAND | wx.ALL,
            8,
        )

        # ----------------------------------------------------------------
        # ÁRBOL
        # ----------------------------------------------------------------

        self.tree = wx.TreeCtrl(
            panel,
            style=(
                wx.TR_DEFAULT_STYLE
                | wx.TR_HIDE_ROOT
            ),
        )

        main_sizer.Add(
            self.tree,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT,
            8,
        )

        # ----------------------------------------------------------------
        # DETALLE
        # ----------------------------------------------------------------

        detail_box = wx.StaticBoxSizer(
            wx.VERTICAL,
            panel,
            "Detalle",
        )

        self.detail = wx.TextCtrl(
            panel,
            style=(
                wx.TE_MULTILINE
                | wx.TE_READONLY
                | wx.HSCROLL
            ),
        )

        detail_box.Add(
            self.detail,
            1,
            wx.EXPAND,
        )

        main_sizer.Add(
            detail_box,
            0,
            wx.EXPAND | wx.ALL,
            8,
        )

        # ----------------------------------------------------------------
        # ESTADO
        # ----------------------------------------------------------------

        self.status = wx.StaticText(
            panel,
            label="Sin registro cargado.",
        )

        main_sizer.Add(
            self.status,
            0,
            wx.LEFT | wx.BOTTOM,
            8,
        )

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

        # Ctrl+O: Abrir registro
        if control_down and key_code == ord("O"):

            self.on_open(event)
            return

        # Ctrl+F: Foco en filtro
        elif control_down and key_code == ord("F"):

            self.text_filter.SetFocus()
            return

        # F6: Cambiar vista
        elif key_code == wx.WXK_F6:

            views = ["source", "time", "level"]
            try:
                next_view = views[(views.index(self.current_view) + 1) % len(views)]
            except ValueError:
                next_view = "source"

            self.change_view(next_view)

            # Actualizar radio buttons del menú
            self.source_view_item.Check(self.current_view == "source")
            self.time_view_item.Check(self.current_view == "time")
            self.level_view_item.Check(self.current_view == "level")
            return

        event.Skip()

    # ========================================================================
    # CAMBIO DE VISTA
    # ========================================================================

    def change_view(self, view):

        self.current_view = view

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

    def load_file(self, path):

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

        self.current_file_path = path

        self.refresh()

        self.SetTitle(
            f"Visor de registros de NVDA — "
            f"{path.name}"
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

        status_text = f"{file_name} | {len(entries)} entradas"

        if entries:

            last_entry = entries[-1]

            status_text += f" | Última entrada: {last_entry.time_text}"

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
            "Registro de NVDA"
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
                "Developer info for navigator object",
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
                        "Global Commands",
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
                        "Global Plugins",
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
                        "App Modules",
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
                        f"{level} ({len(level_entries)})",
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

        root = self.tree.AddRoot(
            "Registro cronológico"
        )

        for entry in sorted(
            entries,
            key=lambda item: item.sort_time,
        ):

            node = self.tree.AppendItem(
                root,
                self.entry_label(entry),
            )

            self.tree_entries[node] = entry

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

        if self.current_view == "source":

            export_item = menu.Append(wx.ID_ANY, "Exportar")
            self.Bind(wx.EVT_MENU, lambda e: self.on_export(item), export_item)

        clear_filters_item = menu.Append(wx.ID_ANY, "Quitar filtros")
        self.Bind(wx.EVT_MENU, self.on_clear_filters, clear_filters_item)

        self.PopupMenu(menu)
        menu.Destroy()

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
            "Guardar registro como",
            wildcard="Archivo de texto (*.txt;*.log)|*.txt;*.log",
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

        if event.GetKeyCode() == wx.WXK_SPACE:

            # Obtener línea actual
            pos = self.detail.GetInsertionPoint()
            success, col, line_no = self.detail.PositionToXY(pos)
            
            line_text = self.detail.GetLineText(line_no)

            # Analizar con Regex
            match = TRACEBACK_FILE_RE.search(line_text)

            if match:
                path = Path(match.group("path"))
                line = match.group("line")

                if path.exists():

                    vscode = self.get_vscode_path()

                    if vscode and vscode.exists():
                        os.system(f'start "" "{vscode}" -g "{path}:{line}"')
                        return
                    else:
                        wx.MessageBox(
                            "No se pudo encontrar VS Code instalado.",
                            "Error",
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

        entry = self.tree_entries.get(item)

        if entry is None:
            return

        lines = [
            f"Nivel: {entry.level}",
            f"Hora: {entry.time_text}",
            f"Hilo: {entry.thread}",
            f"PID: {entry.pid}",
            "",
            f"Origen: {entry.source_type}",
            f"Emisor: {entry.display_emitter}",
            f"Módulo: {entry.module}",
            f"Fuente: {entry.source_raw}",
            "",
            "Encabezado:",
            entry.header_text,
            "",
            "Mensaje:",
            entry.message or "(sin mensaje)",
        ]

        if entry.traceback:

            lines.extend([
                "",
                "Traceback:",
            ])

            lines.extend(
                entry.traceback
            )

        self.detail.SetValue(
            "\n".join(lines)
        )


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