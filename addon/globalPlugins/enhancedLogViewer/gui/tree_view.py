import re

import addonHandler

addonHandler.initTranslation()

from ..logs.log_model import LogModel


class LogTreeView:
	NAVIGATOR_OBJECT_DEV_INFO_SOURCE = (
		"globalCommands.script_navigatorObject_devInfo"
	)

	def __init__(self, tree, detail, model, current_view, entry_label, entry_hash):
		self.tree = tree
		self.detail = detail
		self.model = model
		self.current_view = current_view
		self.entry_label = entry_label
		self.entry_hash = entry_hash
		self.entries_by_node = {}
		self.destroyed = False

	@classmethod
	def _keep_latest_navigator_object_dev_info(cls, entries):
		dev_info_entries = [
			entry
			for entry in entries
			if entry.source_raw == cls.NAVIGATOR_OBJECT_DEV_INFO_SOURCE
		]
		if len(dev_info_entries) < 2:
			return entries

		latest_entry = max(dev_info_entries, key=lambda entry: entry.sort_time)
		return [
			entry
			for entry in entries
			if (
				entry.source_raw != cls.NAVIGATOR_OBJECT_DEV_INFO_SOURCE
				or entry is latest_entry
			)
		]

	def on_tree_destroy(self, event):
		self.destroyed = True
		event.Skip()

	def get_expanded_signatures(self, root):
		expanded = set()
		child, cookie = self.tree.GetFirstChild(root)
		while child.IsOk():
			if self.tree.IsExpanded(child):
				expanded.add(self.get_node_signature(child))
				expanded.update(self.get_expanded_signatures(child))
			child, cookie = self.tree.GetNextChild(root, cookie)
		return expanded

	def restore_expanded_state(self, root, expanded_signatures):
		child, cookie = self.tree.GetFirstChild(root)
		while child.IsOk():
			signature = self.get_node_signature(child)
			if signature in expanded_signatures:
				self.tree.Expand(child)
				self.restore_expanded_state(child, expanded_signatures)
			child, cookie = self.tree.GetNextChild(root, cookie)

	def restore_closest_focus(self, previous_entry, entries):
		if not previous_entry or not entries:
			return False

		try:
			old_index = self.model.entries.index(previous_entry)
		except ValueError:
			return False

		best_entry = None
		minimum_distance = float("inf")
		for entry in entries:
			try:
				current_index = self.model.entries.index(entry)
				distance = abs(current_index - old_index)
				if distance < minimum_distance:
					minimum_distance = distance
					best_entry = entry
			except ValueError:
				continue

		if best_entry:
			for node, entry in self.entries_by_node.items():
				if entry == best_entry:
					self.tree.SelectItem(node)
					self.tree.EnsureVisible(node)
					self.tree.SetFocus()
					return True
		return False

	def restore_focus_by_signature(self, target_signature):
		if target_signature is None:
			return False

		root = self.tree.GetRootItem()
		if not root.IsOk():
			return False

		def find_node_tolerant(node, target_sig):
			node_sig = self.get_node_signature(node)
			if node_sig[0] == target_sig[0] and node_sig[1] == target_sig[1]:
				if node_sig[0] == "entry":
					if node_sig[2] == target_sig[2]:
						return node
				else:
					path1 = node_sig[2]
					path2 = target_sig[2]
					if len(path1) == len(path2):
						for part1, part2 in zip(path1, path2):
							clean1 = re.sub(r"\s+\(\d+\)$", "", part1).strip()
							clean2 = re.sub(r"\s+\(\d+\)$", "", part2).strip()
							if clean1 != clean2:
								break
						else:
							return node

			child, cookie = self.tree.GetFirstChild(node)
			while child.IsOk():
				found = find_node_tolerant(child, target_sig)
				if found:
					return found
				child, cookie = self.tree.GetNextChild(node, cookie)
			return None

		target = find_node_tolerant(root, target_signature)
		if not target:
			return False

		self.tree.SelectItem(target)
		self.tree.EnsureVisible(target)
		self.tree.SetFocus()
		return True

	def save_tree_state(self):
		selection = self.tree.GetSelection()
		target_signature = (
			self.get_node_signature(selection)
			if selection and selection.IsOk()
			else None
		)
		previous_entry = (
			self.entries_by_node.get(selection)
			if selection and selection.IsOk()
			else None
		)
		root = self.tree.GetRootItem()
		expanded_signatures = (
			self.get_expanded_signatures(root) if root and root.IsOk() else set()
		)

		self.entries_by_node.clear()
		self.tree.DeleteAllItems()
		self.detail.Clear()
		return target_signature, previous_entry, expanded_signatures

	def restore_tree_state(
		self,
		root,
		target_signature,
		expanded_signatures,
		previous_entry=None,
		entries=None,
	):
		self.restore_expanded_state(root, expanded_signatures)
		focus_restored = self.restore_focus_by_signature(target_signature)
		if (
			not focus_restored
			and previous_entry is not None
			and entries is not None
		):
			focus_restored = self.restore_closest_focus(previous_entry, entries)
		if not focus_restored:
			first_item, _cookie = self.tree.GetFirstChild(root)
			if first_item.IsOk():
				self.tree.SelectItem(first_item)
				self.tree.EnsureVisible(first_item)
				self.tree.SetFocus()

	def populate_level_tree(self, entries):
		entries = self._keep_latest_navigator_object_dev_info(entries)
		target_sig, previous_entry, expanded_sigs = self.save_tree_state()
		root = self.tree.AddRoot("Registro por nivel")

		groups = {}
		for entry in entries:
			groups.setdefault(entry.level, {}).setdefault(entry.module, []).append(entry)

		for level in LogModel.LEVELS:
			if level not in groups:
				continue

			level_node = self.tree.AppendItem(root, level)
			modules = groups[level]
			for module in sorted(modules):
				module_entries = modules[module]
				module_node = self.tree.AppendItem(
					level_node,
					f"{module} ({len(module_entries)})",
				)
				for entry in module_entries:
					node = self.tree.AppendItem(module_node, self.entry_label(entry))
					self.entries_by_node[node] = entry

		self.restore_tree_state(
			root, target_sig, expanded_sigs, previous_entry, entries
		)

	def populate_source_tree(self, entries):
		entries = self._keep_latest_navigator_object_dev_info(entries)
		target_sig, _previous_entry, expanded_sigs = self.save_tree_state()
		root = self.tree.AddRoot(_("NVDA Log"))

		nvda_node = None
		global_plugins_node = None
		app_modules_node = None

		special_entries = [
			entry for entry in entries
			if entry.source_raw == self.NAVIGATOR_OBJECT_DEV_INFO_SOURCE
		]

		for entry in special_entries:
			node = self.tree.AppendItem(
				root,
				_("Developer info for navigator object"),
			)
			self.entries_by_node[node] = entry

		groups = {}
		for entry in entries:
			if entry.source_raw == self.NAVIGATOR_OBJECT_DEV_INFO_SOURCE:
				continue
			if entry.source_type == "NVDA":
				key = ("NVDA", entry.module)
			else:
				key = (entry.source_type, entry.addon)
			groups.setdefault(key, []).append(entry)

		def sort_key(item):
			type_order = {"NVDA": 1, "Global Plugin": 2, "App Module": 3}
			return type_order.get(item[0], 99), item[1].lower()

		for source_type, source_name in sorted(groups, key=sort_key):
			group_entries = groups[(source_type, source_name)]
			if source_type == "NVDA":
				if nvda_node is None:
					nvda_node = self.tree.AppendItem(root, "NVDA")
				emitter_node = self.tree.AppendItem(nvda_node, source_name)
			elif source_type == "Global Plugin":
				if global_plugins_node is None:
					global_plugins_node = self.tree.AppendItem(
						root, _("Global Plugins")
					)
				emitter_node = self.tree.AppendItem(global_plugins_node, source_name)
			else:
				if app_modules_node is None:
					app_modules_node = self.tree.AppendItem(root, _("App Modules"))
				emitter_node = self.tree.AppendItem(app_modules_node, source_name)

			for level in LogModel.LEVELS:
				level_entries = [entry for entry in group_entries if entry.level == level]
				if not level_entries:
					continue
				level_node = self.tree.AppendItem(
					emitter_node,
					_("{} ({})").format(level, len(level_entries)),
				)
				for entry in level_entries:
					node = self.tree.AppendItem(level_node, self.entry_label(entry))
					self.entries_by_node[node] = entry

		self.restore_tree_state(root, target_sig, expanded_sigs)

	def populate_time_tree(self, entries):
		entries = self._keep_latest_navigator_object_dev_info(entries)
		target_sig, _previous_entry, expanded_sigs = self.save_tree_state()
		root = self.tree.AddRoot(_("Chronological log"))

		groups = {}
		for entry in sorted(entries, key=lambda item: item.sort_time):
			parts = entry.time_text.split(":")
			hour = parts[0]
			minute = parts[1]
			groups.setdefault(hour, {}).setdefault(minute, []).append(entry)

		for hour in sorted(groups):
			hour_node = self.tree.AppendItem(root, f"{hour}:00")
			for minute in sorted(groups[hour]):
				minute_entries = groups[hour][minute]
				minute_node = self.tree.AppendItem(
					hour_node,
					_("{}:{} ({})").format(hour, minute, len(minute_entries)),
				)
				for entry in minute_entries:
					node = self.tree.AppendItem(minute_node, self.entry_label(entry))
					self.entries_by_node[node] = entry
			self.tree.Expand(hour_node)

		self.restore_tree_state(root, target_sig, expanded_sigs)

	def get_node_signature(self, node):
		if node == self.tree.GetRootItem():
			return "root", self.current_view()
		if node in self.entries_by_node:
			return (
				"entry",
				self.current_view(),
				self.entry_hash(self.entries_by_node[node]),
			)

		path = []
		current = node
		while current.IsOk() and current != self.tree.GetRootItem():
			text = self.tree.GetItemText(current)
			text = re.sub(r"\s+\(\d+\)$", "", text).strip()
			path.insert(0, text)
			current = self.tree.GetItemParent(current)
		return "group", self.current_view(), tuple(path)

	@staticmethod
	def signatures_equal(signature1, signature2):
		if signature1[0] != signature2[0] or signature1[1] != signature2[1]:
			return False
		if signature1[0] == "entry":
			return signature1[2] == signature2[2]

		path1, path2 = signature1[2], signature2[2]
		if len(path1) != len(path2):
			return False
		for part1, part2 in zip(path1, path2):
			clean1 = re.sub(r"\s+\(\d+\)$", "", part1).strip()
			clean2 = re.sub(r"\s+\(\d+\)$", "", part2).strip()
			if clean1 != clean2:
				return False
		return True

	def find_node_by_signature(self, target_signature):
		root = self.tree.GetRootItem()
		if not root.IsOk():
			return None

		def find_node(node):
			if self.signatures_equal(
				self.get_node_signature(node), target_signature
			):
				return node
			child, cookie = self.tree.GetFirstChild(node)
			while child.IsOk():
				found = find_node(child)
				if found:
					return found
				child, cookie = self.tree.GetNextChild(node, cookie)
			return None

		return find_node(root)

	def get_node_path(self, node):
		path = []
		current = node
		while current.IsOk() and current != self.tree.GetRootItem():
			path.insert(0, self.tree.GetItemText(current))
			current = self.tree.GetItemParent(current)
		return "/".join(path)

	def get_all_entries_under_node(self, node):
		if self.destroyed:
			return []

		entries = []
		if node in self.entries_by_node:
			entries.append(self.entries_by_node[node])

		child, cookie = self.tree.GetFirstChild(node)
		while child.IsOk():
			entries.extend(self.get_all_entries_under_node(child))
			child, cookie = self.tree.GetNextChild(node, cookie)
		return entries
