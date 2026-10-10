from pathlib import Path
import re
import shutil
import webbrowser
import markdown
import wx
import nvdaControllerClient
from l10n import _

from bookmark_store import BookmarkStore, entry_hash
from config import load_settings as read_settings
from config import save_settings as write_settings
from logs.exporter import write_entries as export_entries
from logs.log_model import LogModel
from logs.parser import parse_log

from .bookmark_controller import BookmarkController
from .log_detail_view import LogDetailView
from .main_frame_ui import bind_events, build_menu, build_ui
from .settings_dialog import SettingsDialog
from .tree_view import LogTreeView


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

		# Configuración de marcadores
		bookmarks_folder_path = self.settings.get('bookmarks_folder', 'bookmarks')
		self.bookmarks_folder = Path(bookmarks_folder_path)
		self.bookmark_store = BookmarkStore(self.bookmarks_folder)

		self.cleanup_old_bookmarks()

		self.current_log_hash = None

		# Flag para saber si los filtros han cambiado
		self.filters_dirty = False
		self.hidden_entries = set()

		# Vista actual:
		#
		# source = Por origen
		# time   = Cronológico
		self.current_view = "source"

		build_menu(self)
		build_ui(self)
		self.tree_view = LogTreeView(
			self.tree,
			self.detail,
			self.model,
			lambda: self.current_view,
			self.entry_label,
			self.get_entry_hash,
		)
		self.tree_entries = self.tree_view.entries_by_node
		self.bookmark_controller = BookmarkController(self)
		self.detail_view = LogDetailView(
			self.detail,
			self.get_all_entries_under_node,
			lambda: self.settings,
			self.speak,
			self.get_vscode_path,
			lambda: self.tree_view.destroyed,
		)
		bind_events(self)

		self.last_text_filter = ""
		self.last_selected_levels = set(self.level_checks.keys())

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
		return self.bookmark_store.get_log_hash(path)

	def load_bookmarks(self):
		"""Carga marcadores para el log actual."""
		# Limpiar menú de marcadores
		while self.bookmarks_menu.GetMenuItemCount() > 0:
			item = self.bookmarks_menu.FindItemByPosition(0)
			self.bookmarks_menu.Remove(item)

		self.bookmarks = []

		if not self.current_log_hash:
			return

		data = self.bookmark_store.load(self.current_log_hash)

		# Reconstruir el menú
		for entry in data:
			signature = entry['signature']
			label = entry.get('label', _("Marcador sin nombre"))

			bookmark_id = wx.NewIdRef()
			bookmark_item = self.bookmarks_menu.Append(bookmark_id, label)
			self.Bind(
				wx.EVT_MENU,
				lambda e, sig=signature: self.on_bookmark_selected(sig),
				bookmark_item,
			)

			self.bookmarks.append({
				'signature': signature,
				'menu_id': bookmark_id,
				'label': label,
			})

	def save_bookmarks(self):
		"""Guarda los marcadores actuales en un archivo."""
		if not self.current_log_hash:
			return

		self.bookmark_store.save(self.current_log_hash, self.bookmarks)

	def load_settings(self):
		return read_settings(str(self.get_vscode_path() or ""))

	def cleanup_old_bookmarks(self):
		days = self.settings.get('cleanup_days', 90)
		self.bookmark_store.cleanup_old(days)





	def mark_dirty(self):
		self.filters_dirty = True

	def on_clear_filters(self, event):

		self.text_filter.Clear()
		self.hidden_entries.clear()

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

		# F6: Cambiar vista; Shift+F6 recorre las vistas en sentido inverso.
		elif key_code == wx.WXK_F6:
			view_order = ("source", "level", "time")
			current_index = view_order.index(self.current_view)
			if event.ShiftDown():
				next_view = view_order[(current_index - 1) % len(view_order)]
			else:
				next_view = view_order[(current_index + 1) % len(view_order)]

			self.change_view(next_view)

			# Actualizar radio buttons del menú
			self.source_view_item.Check(self.current_view == "source")
			self.level_view_item.Check(self.current_view == "level")
			self.time_view_item.Check(self.current_view == "time")

			view_names = {
				"source": _("Vista por origen"),
				"level": _("Vista por niveles"),
				"time": _("Vista cronológica"),
			}
			self.speak(view_names[next_view])
			return

		event.Skip()

	def on_help(self, event):
		from l10n import lancode
		readme_path = Path(f"doc/{lancode}/README.md")
		if not readme_path.exists():
			readme_path = Path("README.md")

		if not readme_path.exists():
			self.speak(_("No se pudo encontrar el archivo de ayuda"))
			return

		with readme_path.open("r", encoding="utf-8") as f:
			md_content = f.read()

		html_content = markdown.markdown(md_content, extensions=['extra'])

		import tempfile
		with tempfile.NamedTemporaryFile(
			mode="w",
			suffix=".html",
			delete=False,
			encoding="utf-8",
		) as tmp:
			tmp.write(f"<html><body>{html_content}</body></html>")
			tmp_path = tmp.name

		webbrowser.open(f"file://{tmp_path}")



	# ========================================================================
	# CAMBIO DE VISTA
	# ========================================================================

	def change_view(self, view):

		self.current_view = view

		view_names = {
			"source": _("Por origen"),
			"level": _("Por nivel"),
			"time": _("Cronológica"),
		}
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
		write_settings(settings)
		self.settings = settings

	def on_settings(self, event):
		with SettingsDialog(self, self.settings) as dlg:
			if dlg.ShowModal() == wx.ID_OK:
				new_settings = dlg.get_values()
				self.save_settings(new_settings)

				if 'bookmarks_folder' in new_settings:
					self.bookmarks_folder = Path(new_settings['bookmarks_folder'])
					self.bookmark_store.set_folder(self.bookmarks_folder)

	def load_file(self, path):

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

		if not is_reload:
			self.current_file_path = path
			self.current_log_hash = self.bookmark_store.get_log_hash(path)
			self.load_bookmarks()
		else:
			self.current_file_path = path

		self.refresh()

		message = _("Registro recargado") if is_reload else _("Registro cargado")
		wx.CallLater(
			100,
			lambda: self.speak(
				_("{}, {} entradas").format(message, len(self.model.entries))
			),
		)

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

	def on_restore_hidden(self, event):
		self.hidden_entries.clear()
		self.refresh()
		self.speak(_("Elementos ocultos restaurados"))

	def refresh(self):
		if getattr(self, "is_refreshing", False):
			return

		self.is_refreshing = True
		try:
			current_text = self.text_filter.GetValue()
			current_levels = self.selected_levels()

			entries = self.model.filtered(
				current_text,
				current_levels,
				self.hidden_entries,
			)

			if not entries:
				if not getattr(self, "showing_no_entries_dialog", False):
					self.showing_no_entries_dialog = True
					wx.MessageBox(
						_("No hay entradas que coincidan con el filtro"),
						_("Atención"),
						wx.OK | wx.ICON_WARNING,
					)
					self.showing_no_entries_dialog = False

				wx.CallAfter(self.text_filter.SetValue, self.last_text_filter)

				for level, checkbox in self.level_checks.items():
					checkbox.SetValue(level in self.last_selected_levels)

				entries = self.model.filtered(
					self.last_text_filter,
					self.last_selected_levels,
					self.hidden_entries,
				)
			else:
				self.last_text_filter = current_text
				self.last_selected_levels = current_levels

			self.tree_entries.clear()

			self.restore_hidden_item.Enable(len(self.hidden_entries) > 0)
			self.restore_hidden_item.SetItemLabel(
				_("&Restaurar {} elementos ocultos").format(len(self.hidden_entries))
			)

			if self.current_view == "source":
				self.populate_source_tree(entries)
			elif self.current_view == "level":
				self.populate_level_tree(entries)
			else:
				self.populate_time_tree(entries)

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
		finally:
			self.is_refreshing = False

	# ========================================================================
	# VISTA POR NIVEL
	# ========================================================================









	# ========================================================================
	# VISTA POR ORIGEN
	# ========================================================================



	# ========================================================================
	# VISTA CRONOLÓGICA
	# ========================================================================



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



	def populate_level_tree(self, entries):
		self.tree_view.populate_level_tree(entries)

	def populate_source_tree(self, entries):
		self.tree_view.populate_source_tree(entries)

	def populate_time_tree(self, entries):
		self.tree_view.populate_time_tree(entries)

	@staticmethod
	def _signatures_equal(signature1, signature2):
		return LogTreeView.signatures_equal(signature1, signature2)

	def _find_node_by_signature(self, target_signature):
		return self.tree_view.find_node_by_signature(target_signature)

	def get_node_path(self, node):
		return self.tree_view.get_node_path(node)

	def get_node_signature(self, node):
		return self.tree_view.get_node_signature(node)

	def get_all_entries_under_node(self, node):
		return self.tree_view.get_all_entries_under_node(node)




	def get_entry_hash(self, entry):
		return entry_hash(entry)








	def on_add_bookmark(self, node):
		return self.bookmark_controller.on_add_bookmark(node)

	def on_bookmark_selected(self, signature):
		return self.bookmark_controller.on_bookmark_selected(signature)

	def on_hide_node(self, node):
		return self.bookmark_controller.on_hide_node(node)

	def on_remove_bookmark(self, signature):
		return self.bookmark_controller.on_remove_bookmark(signature)

	def on_toggle_bookmark(self, node):
		return self.bookmark_controller.on_toggle_bookmark(node)

	def on_tree_context_menu(self, event):
		return self.bookmark_controller.on_tree_context_menu(event)

	def write_entries(self, file_path, entries):
		export_entries(file_path, entries)

	def on_save_as(self, event):
		current_text = self.text_filter.GetValue()
		current_levels = self.selected_levels()
		entries = self.model.filtered(
			current_text,
			current_levels,
			self.hidden_entries,
		)

		if not entries:
			wx.MessageBox(
				_("No hay entradas para guardar con los filtros actuales."),
				_("Atención"),
				wx.OK | wx.ICON_WARNING,
			)
			return

		dialog = wx.FileDialog(
			self,
			_("Guardar registro como"),
			wildcard=_("Archivo de registro (*.log;*.txt)|*.log;*.txt"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		)

		try:
			if dialog.ShowModal() != wx.ID_OK:
				return

			path = Path(dialog.GetPath())
			self.write_entries(path, entries)
			self.speak(_("Registro guardado"))

		finally:
			dialog.Destroy()

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
			self.write_entries(path, entries)

		finally:
			dialog.Destroy()

	def get_vscode_path(self):
		code = shutil.which("code")

		if code:
			vscode = Path(code).parent.parent / "Code.exe"
			return vscode

		return None
	def on_detail_key(self, event):
		self.detail_view.on_detail_key(event)

	def on_tree_selection(self, event):
		self.detail_view.on_tree_selection(event)



