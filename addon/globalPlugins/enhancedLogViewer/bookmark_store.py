from datetime import datetime
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import time


_EMBEDDED_BOOKMARKS_RE = re.compile(
	r"\{bookmarks:(?P<payload>[^\r\n{}]*)\}\r?\n?\Z"
)


def _valid_bookmark(bookmark):
	if not isinstance(bookmark, dict):
		return False

	signature = bookmark.get("signature")
	label = bookmark.get("label")
	if not isinstance(signature, (list, tuple)) or len(signature) != 3:
		return False
	if signature[0] not in ("entry", "group"):
		return False
	if signature[1] not in ("source", "level", "time"):
		return False
	if not isinstance(label, str):
		return False

	if signature[0] == "entry":
		return isinstance(signature[2], str)
	return isinstance(signature[2], (list, tuple)) and all(
		isinstance(part, str) for part in signature[2]
	)


def encode_embedded_bookmarks(bookmarks):
	data = [
		{"signature": bookmark["signature"], "label": bookmark["label"]}
		for bookmark in bookmarks
		if _valid_bookmark(bookmark)
	]
	if not data:
		return None

	json_data = json.dumps(data, ensure_ascii=False).encode("utf-8")
	payload = base64.b64encode(json_data).decode("ascii")
	return f"{{bookmarks:{payload}}}"


def extract_embedded_bookmarks(text):
	match = _EMBEDDED_BOOKMARKS_RE.search(text)
	if not match:
		return text, []

	start = match.start()
	if start and text[start - 1] not in "\r\n":
		return text, []

	log_text = text[:start]
	try:
		payload = base64.b64decode(match.group("payload"), validate=True)
		data = json.loads(payload.decode("utf-8"))
	except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
		return log_text, []

	if not isinstance(data, list):
		return log_text, []

	bookmarks = [bookmark for bookmark in data if _valid_bookmark(bookmark)]
	return log_text, bookmarks


def entry_hash(entry, message=None):
	if message is None:
		message = entry.message
	content = (
		f"{entry.level}{entry.source_raw}{entry.time_text}"
		f"{entry.thread}{entry.pid}{message}"
	)
	return hashlib.md5(content.encode("utf-8")).hexdigest()


class BookmarkStore:
	def __init__(self, folder):
		self.set_folder(folder)

	def set_folder(self, folder):
		self.folder = Path(folder)
		self.folder.mkdir(exist_ok=True)

	@staticmethod
	def get_log_hash(path):
		if not path.exists():
			return None

		with path.open("rb") as log_file:
			content = log_file.read(512)
		return hashlib.md5(content).hexdigest()

	def cleanup_old(self, days):
		now = datetime.now()
		for file_path in self.folder.glob("*"):
			if not file_path.is_file():
				continue

			modified_at = datetime.fromtimestamp(file_path.stat().st_mtime)
			if (now - modified_at).days > days:
				file_path.unlink()

	def load(self, log_hash):
		if not log_hash:
			return []

		bookmark_file = self.folder / log_hash
		if not bookmark_file.exists():
			return []

		with bookmark_file.open("r", encoding="utf-8") as bookmark_stream:
			bookmarks = json.load(bookmark_stream)
		os.utime(bookmark_file, (time.time(), time.time()))
		return bookmarks

	def save(self, log_hash, bookmarks):
		if not log_hash:
			return

		bookmark_file = self.folder / log_hash
		data = [
			{'signature': bookmark['signature'], 'label': bookmark['label']}
			for bookmark in bookmarks
		]
		with bookmark_file.open("w", encoding="utf-8") as bookmark_stream:
			json.dump(data, bookmark_stream, indent=4)
