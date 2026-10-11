from pathlib import Path
import wx
import addonHandler

addonHandler.initTranslation()


def build_menu(frame):

	menubar = wx.MenuBar()

	# ----------------------------------------------------------------
	# File
	# ----------------------------------------------------------------

	file_menu = wx.Menu()

	load_menu = wx.Menu()

	frame.load_nvda_item = load_menu.Append(
		wx.ID_ANY,
		"nvda.log",
	)

	frame.load_nvda_old_item = load_menu.Append(
		wx.ID_ANY,
		"nvda-old.log",
	)

	frame.open_item = load_menu.Append(
		wx.ID_OPEN,
		_("&Other file...\tCtrl+O"),
	)

	file_menu.Append(
		wx.MenuItem(
			file_menu,
			wx.ID_ANY,
			_("&Load log"),
			subMenu=load_menu,
		)
	)

	frame.reload_item = file_menu.Append(
		wx.MenuItem(file_menu, wx.ID_ANY, _("&Reload log\tF5"))
	)

	frame.save_as_item = file_menu.Append(
		wx.ID_ANY,
		_("&Save as...\tCtrl+S"),
	)
	frame.Bind(wx.EVT_MENU, frame.on_save_as, frame.save_as_item)

	frame.settings_item = file_menu.Append(
		wx.MenuItem(file_menu, wx.ID_ANY, _("&Settings\tCtrl+A"))
	)

	file_menu.AppendSeparator()

	frame.exit_item = file_menu.Append(
		wx.MenuItem(file_menu, wx.ID_EXIT, _("&Exit\tCtrl+Q"))
	)

	# ----------------------------------------------------------------
	# View
	# ----------------------------------------------------------------

	view_menu = wx.Menu()

	frame.source_view_item = view_menu.AppendRadioItem(
		wx.ID_ANY,
		_("&By source"),
	)

	frame.level_view_item = view_menu.AppendRadioItem(
		wx.ID_ANY,
		_("&By level"),
	)

	frame.time_view_item = view_menu.AppendRadioItem(
		wx.ID_ANY,
		_("&Chronological"),
	)

	frame.source_view_item.Check(True)

	view_menu.AppendSeparator()

	frame.clear_filters_item = view_menu.Append(
		wx.ID_ANY,
		_("&Clear filters\tCtrl+Z"),
	)

	frame.restore_hidden_item = view_menu.Append(
		wx.ID_ANY,
		_("&Restore hidden elements"),
	)
	frame.restore_hidden_item.Enable(False)
	frame.Bind(wx.EVT_MENU, frame.on_restore_hidden, frame.restore_hidden_item)

	# ----------------------------------------------------------------
	# Bookmarks
	# ----------------------------------------------------------------

	frame.bookmarks_menu = wx.Menu()

	# ----------------------------------------------------------------
	# Add menus
	# ----------------------------------------------------------------

	menubar.Append(
		file_menu,
		_("&File"),
	)

	menubar.Append(
		view_menu,
		_("&View"),
	)

	menubar.Append(
		frame.bookmarks_menu,
		_("&Bookmarks"),
	)

	frame.SetMenuBar(menubar)


def build_ui(frame):

	panel = wx.Panel(frame)

	main_sizer = wx.BoxSizer(wx.VERTICAL)

	# ----------------------------------------------------------------
	# FILTERS
	# ----------------------------------------------------------------

	filter_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, _("Filters"))

	# Text
	filter_box.Add(
		wx.StaticText(panel, label=_("Filter:")),
		0,
		wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
		6,
	)

	frame.text_filter = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
	frame.text_filter.SetHint(_("Search in log"))
	filter_box.Add(frame.text_filter, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)

	# Levels
	type_box = wx.StaticBoxSizer(wx.HORIZONTAL, panel, _("Levels"))
	frame.level_checks = {}
	display_order = ["INFO", "WARNING", "ERROR", "DEBUGWARNING", "DEBUG", "IO"]

	for level in display_order:
		checkbox = wx.CheckBox(panel, label=level)
		checkbox.SetValue(True)
		frame.level_checks[level] = checkbox
		type_box.Add(checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

	filter_box.Add(type_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)

	# Set the tab order to match the visual order.
	prev_win = frame.text_filter
	for checkbox in frame.level_checks.values():
		checkbox.MoveAfterInTabOrder(prev_win)
		prev_win = checkbox

	main_sizer.Add(filter_box, 0, wx.EXPAND | wx.ALL, 8)

	# ----------------------------------------------------------------
	# TREE and DETAILS
	# ----------------------------------------------------------------

	# Tree
	frame.view_label = wx.StaticText(panel, label=_("View by source"))
	main_sizer.Add(frame.view_label, 0, wx.LEFT | wx.RIGHT, 8)

	frame.tree = wx.TreeCtrl(panel, style=(wx.TR_DEFAULT_STYLE | wx.TR_HIDE_ROOT))
	main_sizer.Add(frame.tree, proportion=2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

	# Details
	detail_box = wx.StaticBoxSizer(wx.VERTICAL, panel, _("Detail"))
	frame.detail = wx.TextCtrl(
		panel,
		style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL),
	)
	detail_box.Add(frame.detail, 1, wx.EXPAND)

	main_sizer.Add(detail_box, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

	# ----------------------------------------------------------------
	# STATUS
	# ----------------------------------------------------------------

	frame.status = wx.StaticText(panel, label=_("No log loaded."))
	main_sizer.Add(frame.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

	panel.SetSizer(main_sizer)


def bind_events(frame):

	frame.Bind(
		wx.EVT_MENU,
		lambda event: frame.load_file(
			Path.home() / "AppData" / "Local" / "Temp" / "nvda.log"
		),
		frame.load_nvda_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		lambda event: frame.load_file(
			Path.home() / "AppData" / "Local" / "Temp" / "nvda-old.log"
		),
		frame.load_nvda_old_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		frame.on_open,
		frame.open_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		frame.on_reload,
		frame.reload_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		frame.on_settings,
		frame.settings_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		lambda event: frame.Close(),
		frame.exit_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		lambda event: frame.change_view("source"),
		frame.source_view_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		lambda event: frame.change_view("time"),
		frame.time_view_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		lambda event: frame.change_view("level"),
		frame.level_view_item,
	)

	frame.Bind(
		wx.EVT_MENU,
		frame.on_clear_filters,
		frame.clear_filters_item,
	)

	# ------------------------------------------------------------
	# Text filter
	# ------------------------------------------------------------

	frame.text_filter.Bind(
		wx.EVT_TEXT,
		lambda event: frame.mark_dirty(),
	)

	frame.text_filter.Bind(
		wx.EVT_TEXT_ENTER,
		frame.on_filter_enter,
	)

	# ------------------------------------------------------------
	# Level checkboxes
	# ------------------------------------------------------------

	for checkbox in frame.level_checks.values():

		checkbox.Bind(
			wx.EVT_CHECKBOX,
			lambda event: (frame.mark_dirty(), event.Skip()),
		)

	# ------------------------------------------------------------
	# Details
	# ------------------------------------------------------------

	frame.detail.Bind(
		wx.EVT_CHAR_HOOK,
		frame.on_detail_key,
	)
	frame.detail.Bind(
		wx.EVT_CONTEXT_MENU,
		frame.detail_view.on_context_menu,
	)

	# ------------------------------------------------------------
	# Tree
	# ------------------------------------------------------------

	frame.tree.Bind(
		wx.EVT_TREE_SEL_CHANGED,
		frame.on_tree_selection,
	)
	frame.tree.Bind(
		wx.EVT_WINDOW_DESTROY,
		frame.tree_view.on_tree_destroy,
	)

	frame.tree.Bind(
		wx.EVT_CONTEXT_MENU,
		frame.on_tree_context_menu,
	)

	frame.tree.Bind(
		wx.EVT_SET_FOCUS,
		frame.on_tree_focus,
	)

	# ------------------------------------------------------------
	# Keyboard
	# ------------------------------------------------------------

	frame.Bind(
		wx.EVT_CHAR_HOOK,
		frame.on_key,
	)
