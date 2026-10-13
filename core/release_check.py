"""Explicit release smoke check: --self-test OUTPUT.json.

Run in a disposable application copy; normal page settings are created there.
The check starts no automation and performs no save writes.
"""

import json
import os
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

from app_version import APP_NAME, APP_VERSION


def run_release_check(application_class, output: Path) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QImage, QPainter, QFont, QColor, QFontDatabase
    from core.affix_catalog import AffixCatalog, validation_affix_names
    from core.relic_validation import ReadOnlySaveValidator, RelicRecord, ValidationStatus
    from core.ocr_engine import VocabularyLoader, bundled_ocr_model_params
    import numpy as np

    result = {"version": APP_VERSION, "frozen": bool(getattr(sys, "frozen", False)),
              "ok": False, "checks": {}}
    application = None
    completed = False

    def finish(error=None):
        nonlocal completed
        if completed:
            return
        completed = True
        if error:
            result["error"] = str(error)
        result["ok"] = not error
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if application:
            application.app.exit(0 if result["ok"] else 1)

    def inspect():
        try:
            window = application.window
            assert window.windowTitle() == f"{APP_NAME} v{APP_VERSION}"
            assert window.about_page.version_label.text() == f"v{APP_VERSION}"
            for name in ("shop_page", "repo_page", "save_page", "settings_page", "about_page"):
                window.switchTo(getattr(window, name))
                application.app.processEvents()
                assert not window.grab().isNull()
            result["checks"]["all_pages"] = "rendered"
            layout = window.save_page.page_content.layout()
            assert layout.indexOf(window.save_page.save_info_card) < layout.indexOf(window.save_page.backup_card)
            assert layout.indexOf(window.save_page.backup_card) < layout.indexOf(window.save_page.validation_card)
            result["checks"]["save_page_layout"] = "current / backups / validation"
            rules = ReadOnlySaveValidator()
            record = RelicRecord(0, 2003002, (6633100, 7044500, 6610802, 0, 0, 6820000),
                                 "Red", "release fixture", False, False)
            assert rules._validate_relic(record).status is ValidationStatus.CONFORMS
            strict = ReadOnlySaveValidator(check_id_consistency=True)._validate_relic(record)
            assert strict.status is ValidationStatus.CONFORMS
            assert strict.id_status is ValidationStatus.VIOLATES
            assert validation_affix_names()[6610802]
            assert len(AffixCatalog().effects) > 100
            result["checks"]["rule_resources"] = {"relics": len(rules.rule_data.relics),
                                                   "effects": len(rules.rule_data.effects)}
            for mode in ("normal", "deepnight"):
                count = len(VocabularyLoader("data", mode).vocabulary)
                assert count > 50
                result["checks"][f"vocabulary_{mode}"] = count
            image = QImage(600, 64, QImage.Format_RGB32)
            image.fill(QColor("white"))
            painter = QPainter(image)
            painter.setFont(QFont("Microsoft YaHei", 23))
            painter.setPen(QColor("black"))
            painter.drawText(12, 45, "提升物理攻击力+2")
            painter.end()
            array = np.frombuffer(image.bits(), dtype=np.uint8).reshape(64, 600, 4)[:, :, :3].copy()
            text, score = application.ocr_engine.recognize_single_line(array)
            assert "物理攻击力" in text and "2" in text, (text, score)
            assert not hasattr(application.ocr_engine.engine, "text_det")
            assert not hasattr(application.ocr_engine.engine, "text_cls")
            result["checks"]["offline_ocr"] = {"text": text, "score": float(score),
                                                  "models": [Path(p).name for p in bundled_ocr_model_params().values()]}
            finish()
        except Exception:
            finish(traceback.format_exc())

    try:
        with patch("rapidocr.utils.download_file.DownloadFile.run",
                   side_effect=RuntimeError("model download forbidden during release check")):
            application = application_class()
            # Qt's offscreen platform does not discover Windows fonts itself.
            for filename in ("msyh.ttc", "segoeui.ttf"):
                font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
                if font.is_file():
                    QFontDatabase.addApplicationFont(str(font))
            application.initialize()
            application.window.show()
            errors = []
            application.ocr_worker.error.connect(errors.append)
            timer = QTimer(application.window)
            timer.setInterval(100)

            def poll():
                if application.ocr_engine is not None:
                    timer.stop()
                    inspect()
                elif errors:
                    timer.stop()
                    finish(errors[0])

            timer.timeout.connect(poll)
            timer.start()
            QTimer.singleShot(60000, lambda: finish("OCR startup timed out"))
            application.app.exec()
    except Exception:
        finish(traceback.format_exc())
    return 0 if result["ok"] else 1
