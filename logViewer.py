import re
import wx

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


# ============================================================================
# REGEX
# ============================================================================

HEADER_RE = re.compile(
    r"^(?P<level>DEBUG|INFO|WARNING|ERROR)\s+-\s+"
    r"(?P<source>.*?)\s+\((?P<time>\d\d:\d\d:\d\d\.\d+)\)\s+-\s+"
    r"(?P<thread>.*?)\s+\((?P<pid>\d+)\):\s*$"
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
    )

    def __init__(self):

        self.entries = []

    def filtered(self, text_filter, levels):
        """
        Filtra las entradas.

        IMPORTANTE:

        El texto de búsqueda se compara ÚNICAMENTE con el encabezado
        de la entrada.

        Por ejemplo:

            INFO - core.main (17:42:04.341) - MainThread (21420):

        No se busca dentro del mensaje ni del traceback.

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
            #
            # SOLO se utiliza el encabezado.
            # ------------------------------------------------------------

            if text_filter:

                header = entry.header_text.casefold()

                if text_filter not in header:
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
        # Cargar automáticamente prueba.txt si existe
        # ----------------------------------------------------------------

        test_file = Path(__file__).with_name(
            "prueba.txt"
        )

        if test_file.exists():

            self.load_file(test_file)

    # ========================================================================
    # MENÚ
    # ========================================================================

    def build_menu(self):

        menubar = wx.MenuBar()

        # ----------------------------------------------------------------
        # Archivo
        # ----------------------------------------------------------------

        file_menu = wx.Menu()

        self.open_item = file_menu.Append(
            wx.ID_OPEN,
            "&Abrir registro...\tCtrl+O",
        )

        file_menu.AppendSeparator()

        self.exit_item = file_menu.Append(
            wx.ID_EXIT,
            "&Salir\tAlt+F4",
        )

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

        self.source_view_item.Check(True)

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

        for level in LogModel.LEVELS:

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

        # ------------------------------------------------------------
        # Botón abrir
        # ------------------------------------------------------------

        self.open_button = wx.Button(
            panel,
            label="Abrir registro...",
        )

        filter_box.Add(
            self.open_button,
            0,
            wx.ALIGN_CENTER_VERTICAL,
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
            self.on_open,
            self.open_item,
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

        self.open_button.Bind(
            wx.EVT_BUTTON,
            self.on_open,
        )

        # ------------------------------------------------------------
        # Filtro de texto
        # ------------------------------------------------------------

        self.text_filter.Bind(
            wx.EVT_TEXT,
            lambda event: self.refresh(),
        )

        self.text_filter.Bind(
            wx.EVT_TEXT_ENTER,
            lambda event: self.refresh(),
        )

        # ------------------------------------------------------------
        # Casillas de nivel
        # ------------------------------------------------------------

        for checkbox in self.level_checks.values():

            checkbox.Bind(
                wx.EVT_CHECKBOX,
                lambda event: self.refresh(),
            )

        # ------------------------------------------------------------
        # Árbol
        # ------------------------------------------------------------

        self.tree.Bind(
            wx.EVT_TREE_SEL_CHANGED,
            self.on_tree_selection,
        )

        # ------------------------------------------------------------
        # Teclado
        # ------------------------------------------------------------

        self.Bind(
            wx.EVT_CHAR_HOOK,
            self.on_key,
        )

    def on_key(self, event):

        if (
            event.ControlDown()
            and event.GetKeyCode() == ord("O")
        ):

            self.on_open(event)
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

        self.refresh()

        self.SetTitle(
            f"Visor de registros de NVDA — "
            f"{path.name}"
        )

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

        else:

            self.populate_time_tree(
                entries
            )

        self.status.SetLabel(
            f"{len(entries)} entradas mostradas "
            f"de {len(self.model.entries)}."
        )

    # ========================================================================
    # VISTA POR ORIGEN
    # ========================================================================

    def populate_source_tree(self, entries):

        self.tree.DeleteAllItems()

        self.detail.Clear()

        root = self.tree.AddRoot(
            "Registro de NVDA"
        )

        nvda_node = None
        global_plugins_node = None
        app_modules_node = None

        # ----------------------------------------------------------------
        # Agrupar entradas
        # ----------------------------------------------------------------

        groups = {}

        for entry in entries:

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
        # Crear árbol
        # ----------------------------------------------------------------

        for (
            source_type,
            source_name,
        ) in sorted(
            groups.keys(),
            key=lambda item: (
                0 if item[0] == "NVDA" else 1,
                item[0],
                item[1].lower(),
            ),
        ):

            group_entries = groups[
                (source_type, source_name)
            ]

            # --------------------------------------------------------
            # NVDA
            # --------------------------------------------------------

            if source_type == "NVDA":

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

        # Expandir únicamente NVDA y las categorías principales.
        self.tree.Expand(root)

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

        self.tree.Expand(root)

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