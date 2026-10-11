from dataclasses import dataclass, field
from datetime import datetime
import re


# ============================================================================
# REGULAR EXPRESSIONS
# ============================================================================

HEADER_RE = re.compile(
	r"^(?P<level>DEBUG|INFO|WARNING|ERROR|DEBUGWARNING|IO)\s+-\s+"
	r"(?P<source>.*?)\s+\((?P<time>\d\d:\d\d:\d\d\.\d+)\)\s+-\s+"
	r"(?P<thread>.*?)\s*(?:\((?P<pid>\d+)\))?:\s*$"
)


# Pattern for tracebacks: File "path", line number,
TRACEBACK_FILE_RE = re.compile(
	r'\s*File "(?P<path>.+)", line (?P<line>\d+),'
)

GLOBAL_PLUGIN_RE = re.compile(
	r"^external:globalPlugins\.([^.]+)(?:\.(.*))?$"
)

APP_MODULE_RE = re.compile(
	r"^external:appModules\.([^.]+)(?:\.(.*))?$"
)


# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class LogEntry:
	id: int

	level: str
	source_raw: str
	time_text: str
	thread: str
	pid: int

	message: str = ""
	traceback: list[str] = field(default_factory=list)

	@property
	def source_type(self):
		"""
        Source type:

        NVDA
        Global Plugin
        App Module
        """

		if self.source_raw.startswith("external:globalPlugins."):
			return "Global Plugin"

		if self.source_raw.startswith("external:appModules."):
			return "App Module"

		return "NVDA"

	@property
	def addon(self):
		"""
        Add-on or application name.
        """

		match = GLOBAL_PLUGIN_RE.match(self.source_raw)

		if match:
			return match.group(1)

		match = APP_MODULE_RE.match(self.source_raw)

		if match:
			return match.group(1)

		return "NVDA"

	@property
	def module(self):
		"""
        Main module.

        For example:

            braille.BrailleHandler.setDisplayByName
                -> braille

            core.main
                -> core

            config.ConfigManager._loadConfig
                -> config
        """

		if self.source_type == "NVDA":
			return self.source_raw.split(".", 1)[0]

		if self.source_type == "Global Plugin":
			match = GLOBAL_PLUGIN_RE.match(self.source_raw)

		elif self.source_type == "App Module":
			match = APP_MODULE_RE.match(self.source_raw)

		else:
			return self.source_raw

		if not match:
			return self.source_raw

		remainder = match.group(2)

		if not remainder:
			return self.addon

		return remainder.split(".", 1)[0]

	@property
	def display_emitter(self):
		"""
        Emitter name displayed in the tree.
        """

		if self.source_type == "NVDA":
			return "NVDA"

		return self.addon

	@property
	def header_text(self):
		"""
        Reconstruct the entry's original header line.

        Example:

        INFO - core.main (17:42:04.341) - MainThread (21420):
        """

		return (
			f"{self.level} - "
			f"{self.source_raw} "
			f"({self.time_text}) - "
			f"{self.thread} "
			f"({self.pid}):"
		)

	@property
	def sort_time(self):
		"""
        Time used to sort the chronological view.
        """

		try:

			return datetime.strptime(
				self.time_text,
				"%H:%M:%S.%f",
			)

		except ValueError:

			return datetime.min
