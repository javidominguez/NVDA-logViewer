# -*- coding: UTF-8 -*-
"""
Log Viewer - NVDA addon
This file is a part of the Log Viewer addon.
This file is covered by the GNU General Public License.
See the file COPYING.txt for more details.
Copyright (C) 2026 Javi Dominguez <fjavids@gmail.com>
"""

from .models import HEADER_RE, LogEntry


# ============================================================================
# PARSER
# ============================================================================

def parse_log(text):
	"""
    Parse an NVDA log.

    Each line matching HEADER_RE starts a new entry.
    Subsequent lines belong to that entry.
    """

	entries = []

	current = None
	in_traceback = False
	next_id = 1

	for line in text.splitlines():

		match = HEADER_RE.match(line)

		# ----------------------------------------------------------------
		# New header.
		# ----------------------------------------------------------------

		if match:

			if current is not None:
				entries.append(current)

			current = LogEntry(
				id=next_id,
				level=match.group("level"),
				source_raw=match.group("source"),
				time_text=match.group("time"),
				thread=match.group("thread"),
				pid=int(match.group("pid")) if match.group("pid") else None,
			)

			next_id += 1
			in_traceback = False

			continue

		# ----------------------------------------------------------------
		# No entry has been found yet.
		# ----------------------------------------------------------------

		if current is None:
			continue

		# ----------------------------------------------------------------
		# Traceback.
		# ----------------------------------------------------------------

		if line.strip() == "Traceback (most recent call last):":

			in_traceback = True
			current.traceback.append(line)

		elif in_traceback:

			current.traceback.append(line)

		# ----------------------------------------------------------------
		# Message.
		# ----------------------------------------------------------------

		elif current.message:

			current.message += "\n" + line

		else:

			current.message = line

	# Add the last entry.
	if current is not None:
		entries.append(current)

	return entries
