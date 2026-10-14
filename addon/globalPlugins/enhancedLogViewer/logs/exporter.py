# -*- coding: UTF-8 -*-
"""
Log Viewer - NVDA addon
This file is a part of the Log Viewer addon.
This file is covered by the GNU General Public License.
See the file COPYING.txt for more details.
Copyright (C) 2026 Javi Dominguez <fjavids@gmail.com>
"""

from pathlib import Path

from ..bookmark_store import encode_embedded_bookmarks


def render_entries(entries, bookmarks=()):
	lines = []
	for entry in sorted(entries, key=lambda item: item.sort_time):
		lines.append(entry.header_text)
		if entry.message:
			lines.append(entry.message)
		if entry.traceback:
			lines.append("\n".join(entry.traceback))
		lines.append("")

	bookmark_block = encode_embedded_bookmarks(bookmarks)
	if bookmark_block:
		lines.append(bookmark_block)

	return "\n".join(lines) + ("\n" if lines else "")


def write_entries(file_path, entries, bookmarks=()):
	Path(file_path).write_text(
		render_entries(entries, bookmarks),
		encoding="utf-8",
	)
