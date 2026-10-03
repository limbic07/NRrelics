# OCR models for offline builds

The application loads these files through `core/ocr_engine.py`. The PyInstaller
spec places them at `resources/models` in the bundled application. RapidOCR is
pinned to 3.9.2 so its preprocessing and recognition configuration stays in sync
with the bundled files.

| File | Role | SHA-256 |
| --- | --- | --- |
| `PP-OCRv6_rec_small.onnx` | PP-OCRv6 recognition | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |

The v6 recognition file matches the model shipped with RapidOCR 3.9.2.

Application OCR uses fixed single-line crops. `LineOnlyRapidOCR` initializes
RapidOCR's recognition path only, so detection and orientation models are not
loaded or bundled. The model is required at startup and is never downloaded.
