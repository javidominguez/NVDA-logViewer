from pathlib import Path

from bookmark_store import encode_embedded_bookmarks


def write_entries(file_path, entries, bookmarks=()):
	with Path(file_path).open("w", encoding="utf-8") as output_file:
		for entry in sorted(entries, key=lambda item: item.sort_time):
			output_file.write(entry.header_text + "\n")
			if entry.message:
				output_file.write(entry.message + "\n")
			if entry.traceback:
				output_file.write("\n".join(entry.traceback) + "\n")
			output_file.write("\n")

		bookmark_block = encode_embedded_bookmarks(bookmarks)
		if bookmark_block:
			output_file.write(bookmark_block + "\n")
