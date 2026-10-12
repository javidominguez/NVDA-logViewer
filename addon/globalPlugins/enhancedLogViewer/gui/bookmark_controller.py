# -*- coding: UTF-8 -*-
"""
Log Viewer - NVDA addon
This file is a part of the Log Viewer addon.
This file is covered by the GNU General Public License.
See the file COPYING.txt for more details.
Copyright (C) 2026 Javi Dominguez <fjavids@gmail.com>
"""

import re

import wx
import addonHandler

addonHandler.initTranslation()

from ..bookmark_store import entry_hash


class BookmarkController:
	def __init__(self, frame):
		self.frame = frame

	def bookmarks_for_entries(self, entries):
		frame = self.frame
		entries = list(entries)
		exported_entry_hashes = {}
		for entry in entries:
			message = entry.message
			if message and not entry.traceback:
				message += "\n"
			exported_entry_hashes.setdefault(
				entry_hash(entry),
				entry_hash(entry, message),
			)
		matching_bookmarks = []

		for bookmark in frame.bookmarks:
			signature = bookmark.get("signature")
			if not isinstance(signature, (list, tuple)) or len(signature) != 3:
				continue

			kind, view, value = signature
			if kind == "entry":
				matches = value in exported_entry_hashes
			elif kind == "group":
				group_path = tuple(value) if isinstance(value, (list, tuple)) else ()
				matches = bool(group_path) and any(
					self._entry_path(entry, view)[:len(group_path)] == group_path
					for entry in entries
				)
			else:
				matches = False

			if matches:
				if kind == "entry":
					value = exported_entry_hashes[value]
					signature = (kind, view, value)
				matching_bookmarks.append({
					"signature": signature,
					"label": bookmark.get("label", ""),
				})

		return matching_bookmarks

	@staticmethod
	def _entry_path(entry, view):
		if view == "source":
			if entry.source_type == "NVDA":
				return "NVDA", entry.module, entry.level
			if entry.source_type == "Global Plugin":
				return "Global Plugins", entry.addon, entry.level
			if entry.source_type == "App Module":
				return "App Modules", entry.addon, entry.level
		elif view == "level":
			return entry.level, entry.module
		elif view == "time":
			parts = entry.time_text.split(":")
			hour, minute = parts[0], parts[1]
			return f"{hour}:00", f"{hour}:{minute}"
		return ()

	def on_add_bookmark(self, node):
		frame = self.frame
		signature = frame.get_node_signature(node)
		raw_label = frame.get_node_path(node)

		label = re.sub(r"\s+\(\d+\)$", "", raw_label)

		if " — " in label:
			parts = label.split(" — ")
			if len(parts) >= 4:
				label = parts[-1].rstrip(" )")

		if any(
			frame._signatures_equal(bookmark['signature'], signature)
			for bookmark in frame.bookmarks
		):
			frame.speak(_("That bookmark already exists"))
			return

		bookmark_id = wx.NewIdRef()
		bookmark_item = frame.bookmarks_menu.Append(bookmark_id, label)
		frame.Bind(wx.EVT_MENU, lambda e: self.on_bookmark_selected(signature), bookmark_item)

		frame.bookmarks.append({
			'signature': signature,
			'menu_id': bookmark_id,
			'label': label,
		})
		frame.save_bookmarks()
		frame.speak(_("Bookmark added"))

	def on_bookmark_selected(self, signature):
		frame = self.frame
		initial_selection = frame.tree.GetSelection()
		initial_signature = (
			frame.get_node_signature(initial_selection)
			if initial_selection.IsOk()
			else None
		)

		def restore_initial_state():
			if initial_signature:
				if frame.current_view != initial_signature[1]:
					frame.change_view(initial_signature[1])
					frame.source_view_item.Check(frame.current_view == "source")
					frame.level_view_item.Check(frame.current_view == "level")
					frame.time_view_item.Check(frame.current_view == "time")

				target = frame._find_node_by_signature(initial_signature)
				if target:
					frame.tree.SelectItem(target)
					frame.tree.EnsureVisible(target)
					wx.CallAfter(frame.detail.SetFocus)

		if frame.current_view != signature[1]:
			frame.change_view(signature[1])
			frame.source_view_item.Check(frame.current_view == "source")
			frame.level_view_item.Check(frame.current_view == "level")
			frame.time_view_item.Check(frame.current_view == "time")

		target = frame._find_node_by_signature(signature)

		if target:
			frame.tree.SelectItem(target)
			frame.tree.EnsureVisible(target)
			wx.CallAfter(frame.detail.SetFocus)
		else:
			filters_active = (
				frame.text_filter.GetValue() != ""
				or any(not checkbox.GetValue() for checkbox in frame.level_checks.values())
				or len(frame.hidden_entries) > 0
			)

			if filters_active:
				msg = _(
					"Cannot access the bookmark with filters or hidden elements. "
					"Do you want to remove all filters?"
				)
				dlg = wx.MessageDialog(
					frame,
					msg,
					_("Bookmark not found"),
					wx.YES_NO | wx.ICON_QUESTION,
				)
				if dlg.ShowModal() == wx.ID_YES:
					frame.on_clear_filters(None)
					target = frame._find_node_by_signature(signature)
					if target:
						frame.tree.SelectItem(target)
						frame.tree.EnsureVisible(target)
						wx.CallAfter(frame.detail.SetFocus)
						return

			frame.speak(_("Could not find the bookmark in the current view"))
			restore_initial_state()

	def on_hide_node(self, node):
		frame = self.frame
		old_hidden_entries = frame.hidden_entries.copy()

		entries = frame.get_all_entries_under_node(node)
		for entry in entries:
			frame.hidden_entries.add(entry.id)

		frame.refresh()

		if (
			not frame.tree.GetRootItem().IsOk()
			or not frame.tree.GetFirstChild(frame.tree.GetRootItem())[0].IsOk()
		):
			frame.hidden_entries = old_hidden_entries
			frame.refresh()
		else:
			frame.speak(_("Entries hidden"))

	def on_remove_bookmark(self, signature):
		frame = self.frame
		bookmark = next(
			(
				item for item in frame.bookmarks
				if frame._signatures_equal(item['signature'], signature)
			),
			None,
		)
		if bookmark:
			frame.bookmarks_menu.Remove(bookmark['menu_id'])
			frame.bookmarks.remove(bookmark)
			frame.save_bookmarks()

			frame.speak(_("Bookmark deleted"))

	def on_toggle_bookmark(self, node):
		frame = self.frame
		signature = frame.get_node_signature(node)
		if any(
			frame._signatures_equal(bookmark['signature'], signature)
			for bookmark in frame.bookmarks
		):
			self.on_remove_bookmark(signature)
		else:
			self.on_add_bookmark(node)

	def on_tree_context_menu(self, event):
		frame = self.frame
		item = frame.tree.GetSelection()

		if not item.IsOk():
			return

		menu = wx.Menu()

		signature = frame.get_node_signature(item)

		is_bookmarked = any(
			frame._signatures_equal(signature, bookmark['signature'])
			for bookmark in frame.bookmarks
		)

		if is_bookmarked:
			actual_bookmark = next(
				bookmark
				for bookmark in frame.bookmarks
				if frame._signatures_equal(signature, bookmark['signature'])
			)
			actual_signature = actual_bookmark['signature']
			bookmark_item = menu.Append(wx.ID_ANY, _("Remove from bookmarks"))
			frame.Bind(
				wx.EVT_MENU,
				lambda e: self.on_remove_bookmark(actual_signature),
				bookmark_item,
			)
		else:
			bookmark_item = menu.Append(wx.ID_ANY, _("Add to bookmarks"))
			frame.Bind(wx.EVT_MENU, lambda e: self.on_add_bookmark(item), bookmark_item)

		if frame.current_view in ("source", "level", "time"):
			export_item = menu.Append(wx.ID_ANY, _("Export"))
			frame.Bind(wx.EVT_MENU, lambda e: frame.on_export(item), export_item)

		clear_filters_item = menu.Append(wx.ID_ANY, _("Clear filters"))
		frame.Bind(wx.EVT_MENU, frame.on_clear_filters, clear_filters_item)

		hide_item = menu.Append(wx.ID_ANY, _("Hide"))
		frame.Bind(wx.EVT_MENU, lambda e: self.on_hide_node(item), hide_item)

		frame.PopupMenu(menu)
		menu.Destroy()
