# -*- coding: UTF-8 -*-
"""
Log Viewer - NVDA addon
This file is a part of the Log Viewer addon.
This file is covered by the GNU General Public License.
See the file COPYING.txt for more details.
Copyright (C) 2026 Javi Dominguez <fjavids@gmail.com>
"""

from pathlib import Path
import shutil
import webbrowser
import wx
import addonHandler
import languageHandler
import speech
import ui

addonHandler.initTranslation()

from ..bookmark_store import (
	BookmarkStore,
	entry_hash,
	extract_embedded_bookmarks,
)
from ..config import (
	DEFAULT_BOOKMARKS_FOLDER,
	load_settings as read_settings,
	resolve_bookmarks_folder,
	save_settings as write_settings,
)
from ..logs.exporter import render_entries, write_entries as export_entries
from ..logs.log_model import LogModel
from ..logs.models import NAVIGATOR_OBJECT_DEV_INFO_SOURCE
from ..logs.parser import parse_log

from .bookmark_controller import BookmarkController
from .log_detail_view import LogDetailView
from .main_frame_ui import bind_events, build_menu, build_ui
from .settings_dialog import SettingsDialog
from .tree_view import LogTreeView


# ============================================================================
# MAIN WINDOW
# ============================================================================

class MainFrame(wx.Frame):

	def speak(self, text):
		ui.message(text)

	def __init__(self, parent=None, log_path=None, settings_path=None, data_dir=None):

		super().__init__(
			parent,
			title=_("NVDA Log Viewer"),
			size=(1250, 800),
		)

		self.model = LogModel()
		self.settings_path = Path(settings_path) if settings_path else None
		self.data_dir = Path(data_dir) if data_dir else Path.cwd()
		self.settings = read_settings(settings_path=self.settings_path)

		# Bookmark configuration.
		self.bookmarks_folder = resolve_bookmarks_folder(
			self.settings.get("bookmarks_folder", DEFAULT_BOOKMARKS_FOLDER),
			self.data_dir,
		)
		self.bookmark_store = BookmarkStore(self.bookmarks_folder)

		self.cleanup_old_bookmarks()

		self.current_log_hash = None

		# Flag indicating whether the filters have changed.
		self.filters_dirty = False
		self.hidden_entries = set()

		# Current view:
		#
		# source = By source
		# time   = Chronological
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
		# Path of the currently loaded file.
		# ----------------------------------------------------------------

		self.current_file_path = None

		if log_path and Path(log_path).is_file():
			self.load_file(
				Path(log_path),
				cancel_speech=False,
				allow_empty=True,
			)

	def load_bookmarks(self, embedded_bookmarks=()):
		"""Load bookmarks for the current log."""
		# Clear the bookmarks menu.
		while self.bookmarks_menu.GetMenuItemCount() > 0:
			item = self.bookmarks_menu.FindItemByPosition(0)
			self.bookmarks_menu.Remove(item)

		self.bookmarks = []

		if not self.current_log_hash:
			return

		data = self.bookmark_store.load(self.current_log_hash)
		for embedded_bookmark in embedded_bookmarks:
			if any(
				self._signatures_equal(
					embedded_bookmark["signature"],
					bookmark["signature"],
				)
				for bookmark in data
			):
				continue
			data.append(embedded_bookmark)

		# Rebuild the menu.
		for entry in data:
			signature = entry["signature"]
			label = entry.get("label", _("Unnamed bookmark"))

			bookmark_id = wx.NewIdRef()
			bookmark_item = self.bookmarks_menu.Append(bookmark_id, label)
			self.Bind(
				wx.EVT_MENU,
				lambda e, sig=signature: self.on_bookmark_selected(sig),
				bookmark_item,
			)

			self.bookmarks.append({
				"signature": signature,
				"menu_id": bookmark_id,
				"label": label,
			})

		if embedded_bookmarks:
			self.save_bookmarks()

	def save_bookmarks(self):
		"""Save the current bookmarks to a file."""
		if not self.current_log_hash:
			return

		self.bookmark_store.save(self.current_log_hash, self.bookmarks)

	def cleanup_old_bookmarks(self):
		days = self.settings.get("cleanup_days", 90)
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
		self.speak(_("Filters cleared"))

	def on_tree_focus(self, event):

		if self.filters_dirty:

			self.refresh()
			self.filters_dirty = False

		event.Skip()

	def on_filter_enter(self, event):
		self.tree.SetFocus()

	def refresh_log_file(self, path, *, follow_tail=False):
		if path.is_file():
			self.load_file(
				path,
				announce=False,
				cancel_speech=False,
				follow_tail=follow_tail,
				allow_empty=True,
			)

	def focus_navigator_object_dev_info(self):
		if self.current_view != "source":
			self.change_view("source")
			self.source_view_item.Check(True)
			self.level_view_item.Check(False)
			self.time_view_item.Check(False)

		dev_info_entries = [
			entry
			for entry in self.model.entries
			if entry.source_raw == NAVIGATOR_OBJECT_DEV_INFO_SOURCE
		]
		if dev_info_entries:
			dev_info_entry = max(dev_info_entries, key=lambda entry: entry.sort_time)
			for node, entry in self.tree_entries.items():
				if entry == dev_info_entry:
					self.tree.SelectItem(node)
					self.tree.EnsureVisible(node)
					break
		self.detail.SetFocus()

	def on_key(self, event):

		key_code = event.GetKeyCode()
		control_down = event.ControlDown()

		# Enter: Move from the selected tree item to its details.
		if (
			self.tree.HasFocus()
			and key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
		):
			self.detail.SetFocus()
			return

		# F1: Open help.
		if key_code == wx.WXK_F1:
			self.on_help(event)
			return

		# Ctrl+C: Copy the selected tree item only while the tree has focus.
		if control_down and key_code == ord("C") and self.tree.HasFocus():
			item = self.tree.GetSelection()
			if item.IsOk():
				self.on_copy(item)
			return

		# Ctrl+O: Open a log.
		if control_down and key_code == ord("O"):
			self.on_open(event)
			return

		# Ctrl+F: Focus the filter.
		elif control_down and key_code == ord("F"):
			self.text_filter.SetFocus()
			return

		# Ctrl+T: Focus the tree.
		elif control_down and key_code == ord("T"):
			self.tree.SetFocus()
			return

		# Ctrl+M: Toggle the bookmark.
		elif control_down and key_code == ord("M"):
			item = self.tree.GetSelection()
			if item.IsOk():
				self.on_toggle_bookmark(item)
			return

		# Ctrl+1..6: Toggle the filter checkboxes.
		elif control_down and ord("1") <= key_code <= ord("6") and self.tree.HasFocus():

			index = key_code - ord("1")
			levels = ["INFO", "WARNING", "ERROR", "DEBUGWARNING", "DEBUG", "IO"]

			if index < len(levels):
				level = levels[index]
				checkbox = self.level_checks.get(level)

				if checkbox:
					new_value = not checkbox.GetValue()
					checkbox.SetValue(new_value)

					state = _("enabled") if new_value else _("disabled")
					self.speak(_("{}, {}").format(level, state))

					self.mark_dirty()
					self.refresh()
			return

		# F6: Change view; Shift+F6 cycles through views in reverse.
		elif key_code == wx.WXK_F6:
			view_order = ("source", "level", "time")
			current_index = view_order.index(self.current_view)
			if event.ShiftDown():
				next_view = view_order[(current_index - 1) % len(view_order)]
			else:
				next_view = view_order[(current_index + 1) % len(view_order)]

			self.change_view(next_view)

			# Update the menu radio buttons.
			self.source_view_item.Check(self.current_view == "source")
			self.level_view_item.Check(self.current_view == "level")
			self.time_view_item.Check(self.current_view == "time")

			view_names = {
				"source": _("View by source"),
				"level": _("View by levels"),
				"time": _("Chronological view"),
			}
			self.speak(view_names[next_view])
			return

		event.Skip()

	def on_help(self, event):
		language = languageHandler.getLanguage().split("_")[0]
		doc_path = Path(__file__).parents[3] / "doc" / language / "readme.html"
		if not doc_path.exists():
			doc_path = Path(__file__).parents[3] / "doc" / "en" / "readme.html"
			if not doc_path.exists():
				self.speak(_("Could not find the help file"))
				return
		webbrowser.open(doc_path.as_uri())

	# ========================================================================
	# CHANGE VIEW
	# ========================================================================

	def change_view(self, view):

		self.current_view = view

		view_names = {
			"source": _("By source"),
			"level": _("By level"),
			"time": _("Chronological"),
		}
		self.view_label.SetLabel(_("View {}").format(view_names[view]))

		self.refresh()

	# ========================================================================
	# FILES
	# ========================================================================

	def on_open(self, event):

		dialog = wx.FileDialog(
			self,
			_("Open NVDA log"),
			wildcard=(
				_("Log files (*.txt;*.log)|*.txt;*.log")
				+ "|"
				+ _("All files (*.*)|*.*")
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
		write_settings(settings, settings_path=self.settings_path)
		self.settings = settings

	def on_settings(self, event):
		with SettingsDialog(
			self,
			self.settings,
			self.get_vscode_path,
			data_dir=self.data_dir,
		) as dlg:
			if dlg.ShowModal() == wx.ID_OK:
				new_settings = dlg.get_values()
				self.save_settings(new_settings)

				if "bookmarks_folder" in new_settings:
					self.bookmarks_folder = resolve_bookmarks_folder(
						new_settings["bookmarks_folder"],
						self.data_dir,
					)
					self.bookmark_store.set_folder(self.bookmarks_folder)

	def load_file(
		self,
		path,
		*,
		announce=True,
		cancel_speech=True,
		follow_tail=False,
		allow_empty=False,
	):
		path = Path(path)
		if cancel_speech:
			speech.cancelSpeech()

		try:

			text = path.read_text(
				encoding="utf-8",
				errors="replace",
			)

		except OSError as error:

			wx.MessageBox(
				_("Could not open file:\n\n{}").format(error),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)

			return

		text, embedded_bookmarks = extract_embedded_bookmarks(text)
		self.model.entries = parse_log(text)

		is_reload = (self.current_file_path == path)

		if not is_reload:
			self.current_file_path = path
			self.current_log_hash = self.bookmark_store.get_log_hash(path)
			self.load_bookmarks(embedded_bookmarks)
		else:
			self.current_file_path = path

		self.refresh(allow_empty=allow_empty)

		if follow_tail:
			self.focus_navigator_object_dev_info()

		if announce:
			message = _("Log reloaded") if is_reload else _("Log loaded")
			wx.CallLater(
				100,
				lambda: self.speak(
					_("{}, {} entries").format(message, len(self.model.entries))
				),
			)

		self.SetTitle(
			_("NVDA Log Viewer — {}").format(path.name)
		)
		if announce:
			self.tree.SetFocus()

	# ========================================================================
	# FILTERS
	# ========================================================================

	def selected_levels(self):

		result = set()

		for level, checkbox in self.level_checks.items():

			if checkbox.GetValue():
				result.add(level)

		return result
	# ========================================================================
	# REFRESH
	# ========================================================================

	def on_restore_hidden(self, event):
		self.hidden_entries.clear()
		self.refresh()
		self.speak(_("Hidden elements restored"))

	def refresh(self, *, allow_empty=False):
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

			if not entries and not allow_empty:
				if not getattr(self, "showing_no_entries_dialog", False):
					self.showing_no_entries_dialog = True
					wx.MessageBox(
						_("No entries match the filter"),
						_("Warning"),
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

			self.restore_hidden_item.Enable(len(self.hidden_entries) > 0)
			self.restore_hidden_item.SetItemLabel(
				_("&Restore {} hidden elements").format(len(self.hidden_entries))
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
				else _("No file")
			)

			status_text = _("{} | {} entries").format(file_name, len(entries))

			if entries:
				last_entry = entries[-1]
				status_text += _(" | Last entry: {}").format(last_entry.time_text)

			self.status.SetLabel(status_text)
		finally:
			self.is_refreshing = False

	# ========================================================================
	# ENTRY TEXT
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
		bookmarks = (
			self.bookmark_controller.bookmarks_for_entries(entries)
			if self.settings.get("include_bookmarks_in_export", True)
			else ()
		)
		export_entries(file_path, entries, bookmarks)

	def on_copy(self, node):
		entries = self.get_all_entries_under_node(node)
		if not entries:
			return

		if not wx.TheClipboard.Open():
			wx.MessageBox(
				_("Unable to copy the selected log entries to the clipboard."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		try:
			copied = wx.TheClipboard.SetData(wx.TextDataObject(render_entries(entries)))
		finally:
			wx.TheClipboard.Close()

		if not copied:
			wx.MessageBox(
				_("Unable to copy the selected log entries to the clipboard."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		self.speak(
			ngettext(
				"%d entry copied to the clipboard",
				"%d entries copied to the clipboard",
				len(entries),
			) % len(entries)
		)

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
				_("No entries to save with current filters."),
				_("Warning"),
				wx.OK | wx.ICON_WARNING,
			)
			return

		dialog = wx.FileDialog(
			self,
			_("Save log as"),
			wildcard=_("Log file (*.log;*.txt)|*.log;*.txt"),
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		)

		try:
			if dialog.ShowModal() != wx.ID_OK:
				return

			path = Path(dialog.GetPath())
			self.write_entries(path, entries)
			self.speak(_("Log saved"))

		finally:
			dialog.Destroy()

	def on_export(self, node):
		entries = self.get_all_entries_under_node(node)

		if not entries:
			return

		dialog = wx.FileDialog(
			self,
			_("Save log as"),
			wildcard=_("Text file (*.txt;*.log)|*.txt;*.log"),
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
