import addonHandler
import globalPluginHandler
import globalVars
import gui as nvdaGui
import NVDAState
from gui import logViewer as nvdaLogViewer
import wx

from pathlib import Path

addonHandler.initTranslation()

from .gui.main_frame import MainFrame


class _LogViewerBridge:
	class _OutputControl:
		def __init__(self, bridge):
			self.bridge = bridge

		def SetInsertionPointEnd(self):
			self.bridge.followTail = True

	def __init__(self, plugin):
		self.plugin = plugin
		self.outputCtrl = self._OutputControl(self)
		self.followTail = False

	def refresh(self):
		wx.CallAfter(self.plugin._refreshLogViewer, self.followTail)
		self.followTail = False


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._frame = None
		self._terminated = False
		self._originalActivate = nvdaLogViewer.activate
		self._originalLogViewer = nvdaLogViewer.logViewer
		self._patchedActivate = self.activateLogViewer
		self._bridge = _LogViewerBridge(self)

		nvdaLogViewer.activate = self._patchedActivate
		nvdaLogViewer.logViewer = self._bridge

	def activateLogViewer(self):
		if globalVars.appArgs.secure:
			return
		if globalVars.appArgs.logFileName is None:
			wx.CallAfter(
				nvdaGui.messageBox,
				_("Log is unavailable"),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
			)
			return
		wx.CallAfter(self._showLogViewer)

	def _showLogViewer(self):
		if self._terminated:
			return
		logPath = globalVars.appArgs.logFileName
		if not logPath:
			return
		if self._frame is None or self._frame.IsBeingDeleted():
			dataDir = Path(NVDAState.WritePaths.configDir) / "addons" / "logViewer"
			dataDir.mkdir(parents=True, exist_ok=True)
			settingsPath = dataDir / "settings.json"
			self._frame = MainFrame(
				parent=nvdaGui.mainFrame,
				log_path=Path(logPath),
				settings_path=settingsPath,
				data_dir=dataDir,
			)
			self._frame.Bind(wx.EVT_CLOSE, self._onFrameClose)
		self._frame.Show()
		self._frame.Raise()

	def _refreshLogViewer(self, followTail):
		if self._terminated:
			return
		logPath = globalVars.appArgs.logFileName
		if not logPath:
			return
		if self._frame is None or self._frame.IsBeingDeleted():
			self._showLogViewer()
		if self._frame is None or self._frame.IsBeingDeleted():
			return
		self._frame.refresh_log_file(Path(logPath), follow_tail=followTail)

	def _onFrameClose(self, event):
		self._frame = None
		event.Skip()

	def terminate(self):
		self._terminated = True
		if self._frame is not None and not self._frame.IsBeingDeleted():
			self._frame.Destroy()
		self._frame = None

		if nvdaLogViewer.activate is self._patchedActivate:
			nvdaLogViewer.activate = self._originalActivate
		if nvdaLogViewer.logViewer is self._bridge:
			nvdaLogViewer.logViewer = self._originalLogViewer
