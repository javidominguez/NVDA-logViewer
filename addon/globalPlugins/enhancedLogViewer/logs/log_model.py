# ============================================================================
# MODEL
# ============================================================================

class LogModel:

	LEVELS = (
		"DEBUG",
		"INFO",
		"WARNING",
		"ERROR",
		"DEBUGWARNING",
		"IO",
	)

	def __init__(self):

		self.entries = []

	def filtered(self, text_filter, levels, hidden_entries=None):
		"""
        Filter the entries.

        IMPORTANT:

        The search text is matched against the entry header,
        message, and traceback.

        The search is case-insensitive.
        """

		text_filter = text_filter.strip().casefold()
		if hidden_entries is None:
			hidden_entries = set()

		result = []

		for entry in self.entries:

			# ------------------------------------------------------------
			# Hidden-entry filter.
			# ------------------------------------------------------------

			if entry.id in hidden_entries:
				continue

			# ------------------------------------------------------------
			# Level filter.
			# ------------------------------------------------------------

			if entry.level not in levels:
				continue

			# ------------------------------------------------------------
			# Text filter.
			# ------------------------------------------------------------

			if text_filter:

				# Combine the header, message, and traceback for searching.
				traceback_text = "\n".join(entry.traceback).casefold()
				content = (
					f"{entry.header_text}\n{entry.message}\n{traceback_text}"
				).casefold()

				if text_filter not in content:
					continue

			result.append(entry)

		return result
