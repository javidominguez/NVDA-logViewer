# NVDA Log Viewer

Prototype of an interface to visualize the NVDA log in a structured way in a tree view, with the ability to apply filters to find information more easily.

## Features and Keyboard Shortcuts

* When opening the viewer, nvda.log is automatically loaded from %temp%.
* In the File menu, there are options to open nvda.log, nvda-old.log, or any .log file.

The tree context menu has the options:
- Export, which saves the content of the branch hanging from the selected node to a text file.
- Clear filter (Ctrl+Z), which clears applied filters.
- Add to bookmarks / Remove from bookmarks

In the details view, when there is a Traceback, if you place the cursor over a line that refers to a .py file and press the space bar, that file will open in the editor selected in settings.
If the settings have defined the path to a local folder containing the NVDA source code, the file corresponding to the .pyc file indicated in the traceback will also open in the editor.
If the editor set in settings is VS Code, the files will open on the exact line. Other editors do not support this feature.

### Keyboard Shortcuts

* Ctrl+O: Opens a .log file.
* F5: Reloads the opened file.
* F6: Toggles between the tree view by message source, view by level, and chronological view.
* Ctrl+F: Moves focus to the filter text box.
* Ctrl+T: Moves focus to the entries tree.
* With focus on the tree, Ctrl+1 to Ctrl+6: Toggles each message level (info, warning, error, etc.).
* Ctrl+Z: Removes applied filters.
* Right-click or Applications key in the tree: Opens the context menu.
* Alt+F4 or control+Q: Closes the application.
* control+M adds or removes the current item from the bookmarks menu.
