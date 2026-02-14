# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NRrelic Bot v2 is a PySide6-based GUI application for automating relic management in Elden Ring：NIGHTREIGN. It uses OCR (CnOcr) to recognize relic affixes, fuzzy matching (rapidfuzz) to correct OCR errors, and template matching to detect relic states. The core workflow: capture game window → detect relic state → OCR affixes → match against presets → execute actions (sell/favorite).

## Development Commands

```bash
# Install dependencies
pip install cnocr opencv-python pyautogui pydirectinput keyboard rapidfuzz PySide6

# Run application
python main.py

# Test OCR recognition (standalone)
python cnocr_test.py

# Test repository filter
python test_filter.py

# Test cleaning workflow
python test_repo_cleaning.py
```

## Architecture

### Core Modules (`core/`)

**OCREngine** (`ocr_engine.py`)
- Singleton pattern for CnOcr instance
- Lazy initialization in background thread (QThread) to avoid blocking UI startup
- **Dynamic vocabulary loading**: Automatically switches vocabulary based on mode
  - `self.current_mode` tracks currently loaded vocabulary ("normal" or "deepnight")
  - `recognize_with_classification()` checks mode and reloads vocabulary if changed
  - Normal mode: loads normal.txt + normal_special.txt
  - Deepnight mode: loads deepnight_pos.txt + deepnight_neg.txt
- **Critical**: Vocabulary is NOT cleaned - special symbols like 【】 must be preserved
- Text postprocessing: symbol normalization (十→+, []→【】), noise removal (※, 仅限能使用的)
- Fuzzy correction using rapidfuzz with 90% threshold
- Retry mechanism: up to 3 retries if no affixes match vocabulary (similarity < 0.9)
- Returns classified affixes with `is_positive` flag based on vocabulary source

**RepoCleaner** (`repo_cleaner.py`)
- Main cleaning workflow controller
- Integrates OCREngine, RelicDetector, PresetManager, RepositoryFilter
- **Skip logic**: Determines whether to process a relic based on state + cleaning_mode + allow_operate_favorited
- **Matching logic**:
  - Single positive affix → unqualified
  - Deepnight mode: blacklist check → whitelist check
  - Normal mode: whitelist check only
  - Whitelist matching: general + each dedicated preset (NOT multiple dedicated presets simultaneously)
- **Action execution**:
  - Sell mode: press 'f' to mark for sale, accumulate pending_sell_count
  - Favorite mode: press '2' to toggle favorite
  - Auto-sell on auto-stop: press '3' then 'f' to confirm (only if is_running=True)
  - Manual stop: warn user to manually complete sell operation

**RelicDetector** (`relic_detector.py`)
- Template matching to detect 5 relic states:
  - Light: free to sell (not favorited, not equipped)
  - Dark-F: favorited only
  - Dark-E: equipped only
  - Dark-FE: favorited + equipped
  - Dark-O: official relic (cannot sell)
- Uses template images: `data/tpl_lock.png`, `data/tpl_equip.png`

**PresetManager** (`preset_manager.py`)
- CRUD operations for presets stored in `data/presets.json`
- Preset types:
  - Normal whitelist: 1 general + up to 20 dedicated
  - Deepnight whitelist: 1 general + up to 20 dedicated
  - Deepnight blacklist: 1 fixed preset
- Each preset contains: id, name, type, affixes (list), is_general, is_active
- **Vocabulary loading**: `load_vocabulary(preset_type, for_editing=True)`
  - `for_editing=True`: Loads only normal.txt (for preset editing UI)
  - `for_editing=False`: Loads normal.txt + normal_special.txt (for OCR recognition)
  - Deepnight modes always load single file (deepnight_pos.txt or deepnight_neg.txt)
  - **Critical**: Vocabulary is NOT cleaned - preserves all special symbols like 【】

**RepositoryFilter** (`automation.py`)
- Game window automation using pyautogui/pydirectinput
- **ROI scaling**: Base resolution 1920x1080, scales to manual game resolution setting
- Accepts settings dict in __init__ to get game_resolution
- Window position is detected dynamically, but resolution is from manual setting
- Key regions (base coordinates):
  - RITUAL_REGION: (130, 30, 280, 90) - verify in relic interface
  - SELL_REGION: (580, 130, 640, 160) - verify sell mode
  - FILTER_REGION: (50, 850, 250, 960) - filter checkbox area
  - FILTER_TITLE_REGION: (180, 55, 240, 99) - filter title verification (prevents entering sort interface)
  - AFFIX_REGION: (1105, 800, 1805, 1000) - affix OCR region
  - COUNT_REGION: (1620, 730, 1675, 760) - relic count display for auto-detect
  - FIRST_RELIC_POS: (975, 255) - cursor position for first relic
- Checkbox coordinates for filter mode:
  - NORMAL_CHECKBOX: (70, 865, 95, 890)
  - DEEPNIGHT_CHECKBOX: (70, 915, 95, 940)
- `apply_filter(mode)`: Complete filter workflow
  1. Enters filter interface (press '4')
  2. Verifies filter interface (OCR checks for "筛选", presses F1 if needed)
  3. Resets filter (press '1')
  4. Adjusts checkboxes based on mode
  5. Exits filter interface (press 'q')
  6. Moves cursor to first relic position
- `verify_filter_interface()`: Prevents entering sort interface by mistake
- `move_to_first_relic()`: Positions cursor on first relic for state detection
- `detect_relic_count()`: OCR-based auto-detection of filtered relic count
- `refresh_window_info()`: Refreshes window position (not resolution) before filtering

### UI Structure (`ui/`)

**MainWindow** (`main_window.py`)
- QStackedWidget with 4 pages: Repo, Save, Shop, Settings
- Navigation via sidebar
- Receives OCREngine from Application after async initialization

**PageRepo** (`pages/page_repo.py`)
- Main cleaning interface
- Left panel: preset cards (general + dedicated presets with expand/collapse)
- Right panel: TabWidget with log + dashboard
- Dashboard shows: total_detected, qualified, unqualified, skipped, sold, favorited
- Qualified relics list: displays affixes with color coding (green=positive, red=negative)
- **Auto-detect relic count**: Checkbox to enable automatic detection of filtered relic count
  - Default: enabled (auto-detect checked, manual input hidden)
  - When enabled: calls `RepositoryFilter.detect_relic_count()` after filtering
  - When disabled: uses manual input value (1-2000)
- CleaningThread: runs RepoCleaner.start_cleaning() in background, emits log_signal and qualified_relic_signal

**PageSettings** (`pages/page_settings.py`)
- Auto-save on change (no save button)
- Settings:
  - game_window_title: default "NIGHTREIGN"
  - game_resolution: [width, height] - manual game resolution setting
    - Default: detected screen resolution on first launch
    - Common options: 1920x1080, 2560x1440, 3840x2160, etc.
    - Used for ROI coordinate scaling calculations
  - allow_operate_favorited: whether to process favorited relics
  - require_double_valid: True=2 affixes match, False=3 affixes match
- Stored in `data/settings.json`
- **Preset management** (in General Settings card):
  - Export presets: Exports presets.json with timestamp to user-selected location
  - Import presets: Imports presets.json from file with validation
    - Validates required fields before import
    - Creates backup of current presets.json before overwriting
    - Requires application restart to take effect
  - Both buttons are horizontally aligned for compact layout

**PresetEditDialog** (`dialogs/preset_edit_dialog.py`)
- Edit preset affixes by selecting from vocabulary
- Batch operations: select all, deselect all, invert, select visible
- Search filter for vocabulary
- **Important**: Disconnect itemChanged signal during batch operations to avoid performance issues

### Data Flow

```
User clicks "Start" in PageRepo
  ↓
CleaningThread.run()
  ↓
RepoCleaner.start_cleaning()
  ↓
Loop for each relic:
  1. RepositoryFilter.capture_game_window() → full window image
  2. RelicDetector.detect_state(image) → Light/F/E/FE/O
  3. RepoCleaner._should_skip_relic() → skip decision
  4. If not skip:
     a. RepositoryFilter._capture_region(AFFIX_REGION) → affix image
     b. OCREngine.recognize_with_classification(affix_image, mode) → affixes
     c. RepoCleaner._match_affixes() → qualified/unqualified
     d. RepoCleaner._execute_action() → press keys
  5. Press 'right' to next relic (unless action auto-advances)
  ↓
Auto-stop: press '3' then 'f' to sell (if pending_sell_count > 0)
Manual-stop: warn user to manually sell
```

### Critical Implementation Details

**ROI Scaling**
- All ROI coordinates are defined at base resolution 1920x1080
- `_scale_region()` automatically scales coordinates based on manual game resolution setting
- **Scaling logic**: Uses separate scale_x and scale_y factors for accurate coordinate mapping
  - scale_x = game_resolution_width / BASE_WIDTH
  - scale_y = game_resolution_height / BASE_HEIGHT
  - Game resolution is manually set in settings (not auto-detected)
  - Default resolution is set to screen resolution on first launch
  - This ensures correct scaling even when aspect ratio differs from 16:9
- **Window offset**: For windowed mode, all screen coordinates must add window.left and window.top
  - `_capture_region()`, `_capture_single_region()`, and `click_checkbox()` automatically add offset
  - This ensures correct positioning when game window is not at screen origin (0, 0)
  - Window position is detected dynamically, but resolution is from manual setting
- Never use full window for OCR - always use AFFIX_REGION for affix recognition

**Vocabulary Loading**
- Vocabulary files use format: `行号→词条内容`
- VocabularyLoader splits on '→' and takes the second part
- **Do NOT clean vocabulary in OCREngine** - preserve all special symbols (【】, +, etc.)
- OCR results ARE cleaned via postprocess_text() before matching
- **Dual vocabulary system**:
  - PresetManager: `load_vocabulary(preset_type, for_editing=True)` for UI editing (normal.txt only)
  - OCREngine: Uses VocabularyLoader directly for recognition (normal.txt + normal_special.txt)
  - This separation allows users to edit only common affixes while OCR recognizes all affixes

**Preset Matching Logic**
- General preset + each dedicated preset = one combination
- Cannot use multiple dedicated presets simultaneously
- Example: general{A,B,C} + dedicated1{D,E} + dedicated2{F,G}
  - Valid: general+dedicated1 = {A,B,C,D,E}
  - Valid: general+dedicated2 = {A,B,C,F,G}
  - Invalid: general+dedicated1+dedicated2 = {A,B,C,D,E,F,G}

**Skip Logic (Favorite Mode)**
- Light → process (can favorite)
- Dark-F → skip if allow_operate_favorited=False, else process (can unfavorite)
- Dark-FE → skip if allow_operate_favorited=False, else process
- Dark-E → process (can favorite)
- Dark-O → process (can favorite)

**Skip Logic (Sell Mode)**
- Light → process (can sell)
- Dark-F → skip if allow_operate_favorited=False, else process (unfavorite then sell)
- Dark-FE → skip if allow_operate_favorited=False, else process
- Dark-E → skip (cannot sell equipped)
- Dark-O → skip (cannot sell official)

**Font Initialization**
- **CRITICAL**: Always use explicit font initialization to avoid "QFont::setPointSize: Point size <= 0 (-1)" error
- **Best Practice**: Use `setFont(QFont("Segoe UI", 9))` instead of stylesheet `font-size: 9pt`
  - Stylesheets can cause Qt to create fonts with invalid point sizes during parsing
  - Explicit font initialization ensures valid point size from creation
- **Never** use `QFont()` without parameters (causes point size -1 error)
- **Pattern for labels with custom font sizes**:
  ```python
  label = QLabel("Text")
  label.setFont(QFont("Segoe UI", 8))  # Explicit font with size
  label.setStyleSheet("color: gray;")   # Stylesheet only for color/style
  ```
- **Application-level font setup** (in main.py):
  - Set default font before creating any widgets: `QFont("Segoe UI", 9)`
  - Add font substitutions for system fonts (MS Sans Serif, MS Shell Dlg, etc.)
  - Set global stylesheet with font-family and font-size to ensure all elements have valid fonts
- **Known Issue**: qfluentwidgets may still produce QFont warnings during FluentWindow initialization
  - This is a library-internal issue and cannot be fully prevented
  - The warning does not affect functionality

**Auto-save Pattern**
- Connect widget signals to auto-save method: `widget.textChanged.connect(self._auto_save_settings)`
- Emit settings_changed signal after saving
- No manual save button needed

## Common Pitfalls

1. **OCR Region**: Always use `_capture_region(AFFIX_REGION)` for affix OCR, not full window
2. **Vocabulary Cleaning**: Never clean vocabulary during loading - only clean OCR results
3. **Vocabulary Loading**: Use `for_editing=True` when loading vocabulary for preset editing UI
4. **Vocabulary Mode Switching**: OCREngine automatically reloads vocabulary when mode changes (normal ↔ deepnight)
5. **Auto-sell Logic**: Check `is_running` flag to distinguish auto-stop vs manual-stop
6. **Preset Matching**: Only combine general + one dedicated preset at a time
7. **Signal Disconnection**: Disconnect itemChanged signals during batch QListWidget operations
8. **Font Initialization**:
   - ALWAYS use `setFont(QFont("Segoe UI", 9))` for explicit font sizes
   - NEVER rely solely on stylesheet `font-size` property - it can cause QFont errors
   - Use stylesheets only for colors and styles, not font sizes
9. **Skip Logic**: Respect `allow_operate_favorited` setting in both sell and favorite modes
10. **Filter Interface**: Always verify filter interface after pressing '4' to avoid entering sort interface
11. **Cursor Position**: Move cursor to first relic after filtering to ensure proper state detection

## File Locations

- Vocabulary: `data/normal.txt`, `data/deepnight_pos.txt`, `data/deepnight_neg.txt`
- Presets: `data/presets.json`
- Settings: `data/settings.json`
- Templates: `data/tpl_lock.png`, `data/tpl_equip.png`, `data/tpl_cursor.png`
- Config: `config/settings.json` (application-level config)
