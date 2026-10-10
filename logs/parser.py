from .models import HEADER_RE, LogEntry


# ============================================================================
# PARSER
# ============================================================================

def parse_log(text):
	"""
    Analiza un registro de NVDA.

    Cada línea que coincide con HEADER_RE comienza una nueva entrada.
    Las líneas siguientes pertenecen a esa entrada.
    """

	entries = []

	current = None
	in_traceback = False
	next_id = 1

	for line in text.splitlines():

		match = HEADER_RE.match(line)

		# ----------------------------------------------------------------
		# Nuevo encabezado
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
				pid=int(match.group("pid")),
			)

			next_id += 1
			in_traceback = False

			continue

		# ----------------------------------------------------------------
		# Todavía no hemos encontrado una entrada
		# ----------------------------------------------------------------

		if current is None:
			continue

		# ----------------------------------------------------------------
		# Traceback
		# ----------------------------------------------------------------

		if line.strip() == "Traceback (most recent call last):":

			in_traceback = True
			current.traceback.append(line)

		elif in_traceback:

			current.traceback.append(line)

		# ----------------------------------------------------------------
		# Mensaje
		# ----------------------------------------------------------------

		elif current.message:

			current.message += "\n" + line

		else:

			current.message = line

	# Añadir última entrada
	if current is not None:
		entries.append(current)

	return entries
