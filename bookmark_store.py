from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import time


def entry_hash(entry):
	content = (
		f"{entry.level}{entry.source_raw}{entry.time_text}"
		f"{entry.thread}{entry.pid}{entry.message}"
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
