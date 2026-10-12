# Enhanced log viewer user guide

Enhanced log viewer for NVDA. Browse the active NVDA log in a structured tree view and apply filters to find information more easily.

## Features and Keyboard Shortcuts

* When opening the viewer, the current NVDA log is automatically loaded.
* In the File menu, there are options to open nvda.log, nvda-old.log, or any .log file.
* File/Save As... saves all entries from the current view to a text file. Current view means the entries that meet the applied filters.

The tree context menu has the options:
- Export, which saves the content of the branch hanging from the selected node to a text file.
- Clear filter (Ctrl+Z), which clears applied filters.
- Add to bookmarks / Remove from bookmarks
- Hide

In the details view, when there is a traceback, place the cursor over a line that refers to a .py file and press the space bar to open that file in the editor selected in settings.
If the settings define the path to a local folder containing the NVDA source code, the file corresponding to the .pyc file indicated in the traceback can also be opened in the editor.
If the selected editor is VS Code, files open on the exact line. Other editors might not support this feature.
In Settings, select VS Code (when detected) or Windows Notepad from the editor list, or use Browse to choose another executable. No editor is selected by default if none has been configured.

### Keyboard Shortcuts

* F1: Open this document.
* Ctrl+O: Opens a .log file.
* F5: Reloads the opened file.
* F6: Toggles between the tree view by message source, view by level, and chronological view.
* Ctrl+F: Moves focus to the filter text box.
* Ctrl+T: Moves focus to the entries tree.
* With focus on the tree, Ctrl+1 to Ctrl+6: Toggles each message level (info, warning, error, etc.).
* Ctrl+Z: Removes applied filters.
* Right-click or Applications key in the tree: Opens the context menu.
* Alt+F4 or Ctrl+Q: Closes the viewer.
* Ctrl+M: Adds or removes the current item from the bookmarks menu.
