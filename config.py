import json
from pathlib import Path

SETTINGS_FILE = "settings.json"

def load_settings(default_code_editor=""):
	path = Path(SETTINGS_FILE)
	if path.exists():
		with path.open("r", encoding="utf-8") as f:
			return json.load(f)

	settings = {
		'code_editor': default_code_editor,
		'nvda_source': '',
		'bookmarks_folder': 'bookmarks',
		'cleanup_days': 90
	}
	return settings

def save_settings(settings):
	with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
		json.dump(settings, f, indent=4)
