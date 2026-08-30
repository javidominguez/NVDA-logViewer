# NVDA Log Viewer

Prototype of an interface to visualize the NVDA log in a structured way in a tree view, with the ability to apply filters to find information more easily.

## Features and Keyboard Shortcuts

* When opening the viewer, nvda.log is automatically loaded from %temp%.
* In the File menu, there are options to open nvda.log, nvda-old.log, or any .log file.

The tree context menu has the options:
- Export, which saves the content of the branch hanging from the selected node to a text file.
- Clear filter (Ctrl+Z), which clears applied filters.

In the detail view, when there is a Traceback, if the cursor is placed on a line referencing a .py file and the spacebar is pressed, that file will be opened at the exact line referenced by the Traceback (only in VS Code; other editors are currently not supported).

### Keyboard Shortcuts

* Ctrl+O: Opens a .log file.
* F5: Reloads the opened file.
* F6: Toggles between the tree view by message source, view by level, and chronological view.
* Ctrl+F: Moves focus to the filter text box.
* Ctrl+T: Moves focus to the entries tree.
* With focus on the tree, Ctrl+1 to Ctrl+6: Toggles each message level (info, warning, error, etc.).
* Ctrl+Z: Removes applied filters.
* Right-click or Applications key in the tree: Opens the context menu.
* Alt+F4: Closes the application.
