# Enhanced log viewer

An NVDA add-on that displays the active NVDA log in a structured tree view and lets you filter entries, inspect tracebacks, and manage bookmarks.

The add-on replaces NVDA's standard log viewer when the standard viewer is opened. It loads the active log file and refreshes the view when NVDA writes a message that requests the log viewer.

## Features

* The current NVDA log is loaded automatically when the viewer opens.
* The File menu can open `nvda.log`, `nvda-old.log`, or any `.log` file.
* Save As exports the entries in the current view, including applied filters.
* The tree context menu can export the selected branch, clear filters, add or remove bookmarks, and hide entries.
* In the details view, place the cursor on a traceback line and press Space to open the referenced source file in the configured editor. Files that can be opened this way are listed in the details text box context menu.
* If the NVDA source folder is configured, a `.pyc` traceback reference can be resolved to its corresponding `.py` file.
* VS Code opens files at the referenced line. Other editors are opened with the file path and may not support line navigation.
* Settings offer detected VS Code and Windows Notepad choices. Use Browse to select another executable.

## Keyboard shortcuts

* F1: Open this documentation.
* Ctrl+O: Open a log file.
* F5: Reload the current file.
* F6: Switch between source, level, and chronological views.
* Ctrl+F: Focus the filter text box.
* Ctrl+T: Focus the entries tree.
* With focus on the tree, Ctrl+1 to Ctrl+6: Toggle each message level.
* Ctrl+Z: Clear applied filters.
* Right-click or the Applications key in the tree or details area: Open the context menu.
* Ctrl+M: Add or remove the current item from bookmarks.
* Alt+F4 or Ctrl+Q: Close the viewer.
