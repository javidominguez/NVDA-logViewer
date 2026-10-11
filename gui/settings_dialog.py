import wx
from l10n import _


class SettingsDialog(wx.Dialog):
	def __init__(self, parent, settings):
		super().__init__(parent, title=_("Settings"))
		self.settings = settings
		self.init_ui()

	def init_ui(self):
		sizer = wx.BoxSizer(wx.VERTICAL)

		# Sizer for the editor.
		editor_sizer = wx.BoxSizer(wx.HORIZONTAL)
		editor_sizer.Add(
			wx.StaticText(self, label=_("Code editor:")),
			0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL,
			5,
		)
		self.editor_path = wx.TextCtrl(self, value=self.settings.get('code_editor', ''))
		self.editor_path.Bind(wx.EVT_CHAR, self.on_text_char)
		editor_sizer.Add(self.editor_path, 1, wx.EXPAND | wx.ALL, 5)
		browse_editor = wx.Button(self, label=_("Browse"))
		browse_editor.Bind(wx.EVT_BUTTON, self.on_browse_editor)
		editor_sizer.Add(browse_editor, 0, wx.ALL, 5)
		sizer.Add(editor_sizer, 0, wx.EXPAND)

		# Sizer for the NVDA source code.
		nvda_sizer = wx.BoxSizer(wx.HORIZONTAL)
		nvda_sizer.Add(
			wx.StaticText(self, label=_("NVDA source code:")),
			0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL,
			5,
		)
		self.nvda_path = wx.TextCtrl(self, value=self.settings.get('nvda_source', ''))
		self.nvda_path.Bind(wx.EVT_CHAR, self.on_text_char)
		nvda_sizer.Add(self.nvda_path, 1, wx.EXPAND | wx.ALL, 5)
		browse_nvda = wx.Button(self, label=_("Browse"))
		browse_nvda.Bind(wx.EVT_BUTTON, self.on_browse_nvda)
		nvda_sizer.Add(browse_nvda, 0, wx.ALL, 5)
		sizer.Add(nvda_sizer, 0, wx.EXPAND)

		# Sizer for the bookmarks folder.
		bookmarks_sizer = wx.BoxSizer(wx.HORIZONTAL)
		bookmarks_sizer.Add(
			wx.StaticText(self, label=_("Bookmarks folder:")),
			0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL,
			5,
		)
		self.bookmarks_path = wx.TextCtrl(
			self,
			value=self.settings.get('bookmarks_folder', 'bookmarks'),
		)
		self.bookmarks_path.Bind(wx.EVT_CHAR, self.on_text_char)
		bookmarks_sizer.Add(self.bookmarks_path, 1, wx.EXPAND | wx.ALL, 5)
		browse_bookmarks = wx.Button(self, label=_("Browse"))
		browse_bookmarks.Bind(wx.EVT_BUTTON, self.on_browse_bookmarks)
		bookmarks_sizer.Add(browse_bookmarks, 0, wx.ALL, 5)
		sizer.Add(bookmarks_sizer, 0, wx.EXPAND)

		# Sizer for cleanup settings.
		cleanup_sizer = wx.BoxSizer(wx.HORIZONTAL)
		cleanup_sizer.Add(
			wx.StaticText(self, label=_("Clean unused bookmarks in:")),
			0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL,
			5,
		)
		self.cleanup_days = wx.SpinCtrl(
			self,
			value=str(self.settings.get('cleanup_days', 90)),
			min=1,
			max=365,
		)
		cleanup_sizer.Add(self.cleanup_days, 0, wx.ALL, 5)
		cleanup_sizer.Add(
			wx.StaticText(self, label=_("Days")),
			0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL,
			5,
		)
		sizer.Add(cleanup_sizer, 0, wx.EXPAND)

		# OK and Cancel buttons.
		btn_sizer = wx.StdDialogButtonSizer()
		btn_ok = wx.Button(self, wx.ID_OK, label=_("OK"))
		btn_cancel = wx.Button(self, wx.ID_CANCEL, label=_("Cancel"))
		btn_sizer.AddButton(btn_ok)
		btn_sizer.AddButton(btn_cancel)
		btn_sizer.Realize()

		sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

		self.SetSizer(sizer)
		self.Fit()
		self.Centre()

	def on_browse_editor(self, event):
		with wx.FileDialog(
			self,
			_("Select editor"),
			wildcard=_("Executables (*.exe)|*.exe"),
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		) as dlg:
			if dlg.ShowModal() == wx.ID_OK:
				self.editor_path.SetValue(dlg.GetPath())

	def on_browse_nvda(self, event):
		with wx.DirDialog(self, _("Select NVDA folder")) as dlg:
			if dlg.ShowModal() == wx.ID_OK:
				self.nvda_path.SetValue(dlg.GetPath())

	def on_browse_bookmarks(self, event):
		with wx.DirDialog(self, _("Select bookmarks folder")) as dlg:
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
		# Allow arrow keys (left and right) and Ctrl+C (to copy).
		if (
			key in (wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_HOME, wx.WXK_END)
			or (event.ControlDown() and key == ord('C'))
		):
			event.Skip()
		else:
			# Ignore all other keys.
			return
