# -*- coding: UTF-8 -*-
"""
Log Viewer - NVDA addon
This file is a part of the Log Viewer addon.
This file is covered by the GNU General Public License.
See the file COPYING.txt for more details.
Copyright (C) 2026 Javi Dominguez <fjavids@gmail.com>
"""

import json
from pathlib import Path

SETTINGS_FILE = "settings.json"

def load_settings(default_code_editor="", settings_path=None):
	path = Path(settings_path) if settings_path else Path(SETTINGS_FILE)
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

def save_settings(settings, settings_path=None):
	path = Path(settings_path) if settings_path else Path(SETTINGS_FILE)
	with path.open("w", encoding="utf-8") as f:
		json.dump(settings, f, indent=4)
