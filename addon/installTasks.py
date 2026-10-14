import os


def onInstall():
	"""Schedule removal of our old logViewer installation to avoid duplicating enhancedLogViewer."""
	try:
		from addonHandler import AddonStateCategory, state
		from NVDAState import WritePaths
	except ImportError:
		return

	configDir = getattr(WritePaths, "configDir", None)
	if not configDir:
		return
	legacyAddonPath = os.path.join(configDir, "addons", "logViewer")
	manifestPath = os.path.join(legacyAddonPath, "manifest.ini")
	if not os.path.isfile(manifestPath):
		return
	try:
		with open(manifestPath, "r", encoding="utf-8") as manifestFile:
			manifestContents = manifestFile.read()
	except OSError:
		return
	if "fjavids" not in manifestContents.casefold():
		return
	state[AddonStateCategory.PENDING_REMOVE].add("logViewer")
	state[AddonStateCategory.DISABLED].discard("logViewer")
	state.save()
