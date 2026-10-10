import wx
from gui.main_frame import MainFrame


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
