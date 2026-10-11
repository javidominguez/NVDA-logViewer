import os
from pathlib import Path

from ..logs.models import TRACEBACK_FILE_RE


def resolve_traceback_location(line_text, nvda_source=""):
	match = TRACEBACK_FILE_RE.search(line_text)
	if not match:
		return None

	path = Path(match.group("path"))
	line_number = match.group("line")
	target_path = None
	if not path.exists() and path.suffix == ".pyc" and nvda_source:
		relative_path = path.with_suffix(".py")
		target_path = Path(nvda_source) / relative_path

	if target_path and target_path.exists():
		return target_path, line_number
	if path.exists():
		return path, line_number
	return None


def find_traceback_references(text):
	references = []
	seen = set()
	for line_text in text.splitlines():
		match = TRACEBACK_FILE_RE.search(line_text)
		if not match:
			continue

		reference = match.group("path"), match.group("line")
		if reference not in seen:
			seen.add(reference)
			references.append(reference)
	return references


def open_in_editor(path, line_number, editor_path):
	if not editor_path:
		return False

	editor = Path(editor_path)
	if not editor.exists():
		return False

	if editor.name.lower() in ("code.exe", "code"):
		os.system(f'start "" "{editor}" -g "{path}:{line_number}"')
	else:
		os.system(f'start "" "{editor}" "{path}"')
	return True
