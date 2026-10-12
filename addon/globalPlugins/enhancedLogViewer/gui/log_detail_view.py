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

from .editor_navigation import (
	find_traceback_references,
	open_in_editor,
	resolve_traceback_location,
)


class LogDetailView:
	def __init__(
		self,
		detail,
		get_entries_under_node,
		get_settings,
		speak,
		get_vscode_path,
		tree_destroyed,
	):
		self.detail = detail
		self.get_entries_under_node = get_entries_under_node
		self.get_settings = get_settings
		self.speak = speak
		self.get_vscode_path = get_vscode_path
		self.tree_destroyed = tree_destroyed
		self.context_actions = {}
		self.detail.Bind(wx.EVT_MENU, self.on_context_menu_action)

	def on_context_menu(self, event):
		menu = wx.Menu()
		self.context_actions.clear()

		select_all_item = menu.Append(wx.ID_ANY, _("Select all"))
		self.context_actions[select_all_item.GetId()] = "select_all"

		copy_item = menu.Append(wx.ID_ANY, _("Copy"))
		selection_start, selection_end = self.detail.GetSelection()
		copy_item.Enable(selection_start != selection_end)
		self.context_actions[copy_item.GetId()] = "copy"

		settings = self.get_settings()
		nvda_source = settings.get("nvda_source", "")
		references = [
			(path, line_number)
			for path, line_number in find_traceback_references(
				self.detail.GetValue()
			)
			if resolve_traceback_location(
				f'File "{path}", line {line_number},',
				nvda_source,
			)
		]
		if references:
			menu.AppendSeparator()
			for path, line_number in references:
				item = menu.Append(
					wx.ID_ANY,
					_("Open {} — line {}").format(path, line_number),
				)
				self.context_actions[item.GetId()] = ("open_reference", path, line_number)

		try:
			position = event.GetPosition()
			if position == wx.DefaultPosition:
				self.detail.PopupMenu(menu)
			else:
				self.detail.PopupMenu(menu, self.detail.ScreenToClient(position))
		finally:
			self.context_actions.clear()
			menu.Destroy()

	def on_context_menu_action(self, event):
		action = self.context_actions.get(event.GetId())
		if action == "select_all":
			self.detail.SelectAll()
		elif action == "copy":
			self.detail.Copy()
		elif action and action[0] == "open_reference":
			self.open_traceback_reference(action[1], action[2])
		else:
			event.Skip()

	def open_traceback_reference(self, path, line_number):
		settings = self.get_settings()
		location = resolve_traceback_location(
			f'File "{path}", line {line_number},',
			settings.get("nvda_source", ""),
		)
		if not location:
			wx.MessageBox(
				_("Could not find referenced file: {}").format(path),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return

		resolved_path, source_line = location
		editor_path = settings.get("code_editor") or self.get_vscode_path()
		if not open_in_editor(resolved_path, source_line, editor_path):
			self.show_editor_error()

	def show_editor_error(self):
		wx.MessageBox(
			_("Could not find the configured editor."),
			_("Error"),
			wx.OK | wx.ICON_ERROR,
		)

	def on_detail_key(self, event):
		key = event.GetKeyCode()

		if key in (wx.WXK_PAGEDOWN, wx.WXK_PAGEUP):
			content = self.detail.GetValue()
			position = self.detail.GetInsertionPoint()
			separator = "-" * 40
			separators = [
				match.start()
				for match in re.finditer(re.escape(separator), content)
			]

			if not separators:
				event.Skip()
				return

			if key == wx.WXK_PAGEDOWN:
				for separator_position in separators:
					if separator_position > position:
						target = separator_position + len(separator) + 1
						self.detail.SetInsertionPoint(target)
						self.detail.ShowPosition(target)
						return
				self.speak(_("No more entries"))
			else:
				found_position = -1
				for separator_position in reversed(separators):
					if separator_position < position:
						found_position = separator_position
						break

				if found_position != -1:
					if position == found_position + len(separator) + 1:
						previous_position = -1
						for separator_position in reversed(separators):
							if separator_position < found_position:
								previous_position = separator_position
								break
						if previous_position != -1:
							target = previous_position + len(separator) + 1
						else:
							target = 0
					else:
						target = found_position + len(separator) + 1
				else:
					target = 0

				self.detail.SetInsertionPoint(target)
				self.detail.ShowPosition(target)
				if target == 0:
					self.speak(_("First entry"))

			event.Skip()
			return

		if key == wx.WXK_SPACE:
			position = self.detail.GetInsertionPoint()
			_, _, line_number = self.detail.PositionToXY(position)
			line_text = self.detail.GetLineText(line_number)
			settings = self.get_settings()
			location = resolve_traceback_location(
				line_text,
				settings.get("nvda_source", ""),
			)
			if location:
				path, source_line = location
				if self.open_location(path, source_line):
					return
				self.show_editor_error()

		event.Skip()

	def open_location(self, path, line_number):
		settings = self.get_settings()
		editor_path = settings.get("code_editor") or self.get_vscode_path()
		return open_in_editor(path, line_number, editor_path)

	def on_tree_selection(self, event):
		if self.tree_destroyed():
			return

		item = event.GetItem()
		if not item.IsOk():
			return

		entries = self.get_entries_under_node(item)
		if not entries:
			self.detail.Clear()
			return

		if (
			len(entries) == 1
			and entries[0].source_raw == "globalCommands.script_navigatorObject_devInfo"
		):
			self.detail.SetValue(entries[0].message)
			return

		if len(entries) == 1:
			entry = entries[0]
			lines = [
				_("Level: {}").format(entry.level),
				_("Time: {}").format(entry.time_text),
				_("Thread: {}").format(entry.thread),
				_("PID: {}").format(entry.pid),
				"",
				_("Origin: {}").format(entry.source_type),
				_("Emitter: {}").format(entry.display_emitter),
				_("Module: {}").format(entry.module),
				_("Source: {}").format(entry.source_raw),
				"",
				_("Header:"),
				entry.header_text,
				"",
				_("Message:"),
				entry.message or _("(no message)"),
			]

			if entry.traceback:
				lines.extend(["", _("Traceback:")])
				lines.extend(entry.traceback)
		else:
			lines = []
			for entry in sorted(entries, key=lambda item: item.sort_time):
				lines.append(entry.header_text)
				if entry.message:
					lines.append(entry.message)
				if entry.traceback:
					lines.extend(entry.traceback)
				lines.append("-" * 40)

		self.detail.SetValue("\n".join(lines))
