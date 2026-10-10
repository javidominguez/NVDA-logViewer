# ============================================================================
# MODELO
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
        Filtra las entradas.

        IMPORTANTE:

        El texto de búsqueda se compara con el encabezado,
        el mensaje y el traceback de la entrada.

        La búsqueda no distingue mayúsculas/minúsculas.
        """

		text_filter = text_filter.strip().casefold()
		if hidden_entries is None:
			hidden_entries = set()

		result = []

		for entry in self.entries:

			# ------------------------------------------------------------
			# Filtro de ocultación
			# ------------------------------------------------------------

			if entry.id in hidden_entries:
				continue

			# ------------------------------------------------------------
			# Filtro por nivel
			# ------------------------------------------------------------

			if entry.level not in levels:
				continue

			# ------------------------------------------------------------
			# Filtro por texto
			# ------------------------------------------------------------

			if text_filter:

				# Combina encabezado, mensaje y traceback para la búsqueda
				traceback_text = "\n".join(entry.traceback).casefold()
				content = (
					f"{entry.header_text}\n{entry.message}\n{traceback_text}"
				).casefold()

				if text_filter not in content:
					continue

			result.append(entry)

		return result
