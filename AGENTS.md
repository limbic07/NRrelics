# NRrelics Developer Guide

This document provides instructions for AI agents and developers working on the NRrelics codebase. It covers environment setup, running the application, code style guidelines, and architectural conventions.

## 1. Environment & Setup

### Dependencies
The project relies on Python and several third-party libraries.
- **Python Version**: Recommended Python 3.9+
- **Key Libraries**:
    - `PySide6`: GUI framework (Qt for Python)
    - `rapidocr_onnxruntime`: OCR engine
    - `opencv-python`: Image processing
    - `numpy`: Numerical operations
    - `pyautogui`, `pydirectinput`: Automation

### Installation
To set up the development environment:

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 2. Build & Run Commands

### Running the Application
The entry point for the application is `main.py`.

```bash
# Run the application
python main.py
```

### Linting
This project follows standard Python linting rules.
If `flake8` or `pylint` are not installed, install them via pip.

```bash
# Run flake8 (recommended)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

### Testing
Currently, there is no dedicated `tests/` directory.
When adding tests, use `pytest`.

```bash
# Run all tests (if applicable)
pytest

# Run a single test file
pytest tests/test_ocr.py

# Run a specific test case
pytest tests/test_ui.py::test_window_launch
```

**Note for Agents**:
- If tasked with adding a feature, ALWAYS verify by running the application (`python main.py`) to ensure no regressions in startup.
- Since automated tests are missing, consider adding a basic unit test for any new logic in `core/`.

## 3. Code Style Guidelines

Adhere strictly to **PEP 8** conventions.

### Formatting
- **Indentation**: 4 spaces (no tabs).
- **Line Length**: Limit to 100 characters where possible, though 120 is acceptable for complex UI definitions.
- **Encoding**: Always use `utf-8` when reading/writing files.

### Imports
Group imports in the following order:
1.  **Standard Library** (`sys`, `json`, `pathlib`)
2.  **Third-Party Libraries** (`PySide6`, `numpy`, `rapidocr`)
3.  **Local Application Imports** (`core`, `ui`)

Example:
```python
import sys
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Signal

from ui.mainwindow import MainWindow
from core.ocr import OCREngine
```

### Naming Conventions
- **Classes**: `PascalCase` (e.g., `OCRWorker`, `MainWindow`).
- **Functions/Methods**: `snake_case` (e.g., `initialize_ocr`, `load_config`).
- **Variables**: `snake_case` (e.g., `config_path`, `user_settings`).
- **Constants**: `UPPER_CASE` (e.g., `DEFAULT_FONT_SIZE`).
- **Private Members**: Prefix with underscore (e.g., `_load_config`, `_init_ui`).

### Type Hinting
Use Python type hints for function arguments and return values, especially in `core` logic.

```python
def process_image(self, image_path: Path) -> dict:
    """Process an image and return results."""
    # ...
```

### Docstrings
Use triple double-quotes (`"""`) for docstrings.
- **Modules**: Brief description at the top.
- **Classes**: Description of the class purpose.
- **Methods**: Brief description. If complex, explain arguments and return values.

```python
class OCRWorker(QObject):
    """
    Worker thread for handling OCR tasks asynchronously.
    Attributes:
        finished (Signal): Emitted when initialization is complete.
    """
```

### Error Handling
- Use `try...except` blocks for operations involving File I/O, Network, or External API calls (like OCR).
- Log errors or emit error signals rather than crashing the application silently.

```python
try:
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"Error loading config: {e}")
    return {}
```

## 4. UI Development (PySide6)

- **Threading**: heavy operations (like OCR initialization or image processing) MUST be offloaded to a `QThread` to keep the UI responsive. See `OCRWorker` in `main.py` for reference.
- **Signals/Slots**: Use `Signal` for communication between worker threads and the UI thread.
- **Styling**: Prefer external QSS (Qt Style Sheets) or centralized style definitions over inline styles, unless it's a specific fix.

## 5. File System Interactions

- **Paths**: Use `pathlib.Path` instead of `os.path` strings.
- **Absolute Paths**: When tools (like `read` or `write` in agent contexts) require paths, ensure you are resolving them relative to the project root.

## 6. Project Structure

- `main.py`: Entry point. Handles app initialization and global thread management.
- `ui/`: Contains all PySide6 widgets and windows.
- `core/`: Contains business logic (OCR, data processing) independent of the UI.
- `data/`: Configuration files and static data resources.
- `requirements.txt`: Python package dependencies.

## 7. Version Control & Commit Messages

- **Commits**: Atomic commits focusing on a single logical change.
- **Messages**:
    - `feat: Add new settings dialog`
    - `fix: Resolve OCR timeout issue`
    - `refactor: Optimize image loading`
    - `docs: Update README`

---
*Generated by Antigravity for NRrelics*
