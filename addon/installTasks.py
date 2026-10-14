def onInstall():
	"""Schedule removal of our old logViewer installation to avoid duplicating enhancedLogViewer."""
	try:
		import addonHandler
		addonHandler.initTranslation()
		from addonHandler import AddonStateCategory, getAvailableAddons, state
	except ImportError:
		return

	logViewerAddon = next(
		(addon for addon in getAvailableAddons() if addon.name.casefold() == "logviewer"),
		None,
	)
	if logViewerAddon is None:
		return

	author = logViewerAddon.manifest.get("author") or _("unknown author")
	if "fjavids" in author .casefold():
		state[AddonStateCategory.PENDING_REMOVE].add(logViewerAddon.name)
	else:
		state[AddonStateCategory.DISABLED].add(logViewerAddon.name)

		import gui
		import wx

		gui.messageBox(
			_(
				# Translators: Warning shown when another add-on named logViewer is disabled
				# because it conflicts with Enhanced Log Viewer. {author} is the add-on author's name.
				"The logViewer add-on by {author} is installed, so it will be disabled to avoid conflicts "
				"with Enhanced Log Viewer. To keep using that add-on instead, uninstall Enhanced Log Viewer "
				"and re-enable logViewer."
			).format(author=author),
			_("Warning"),
			wx.OK | wx.ICON_WARNING,
		)
	state.save()
