"""Optional OCR evidence capture for the two automatic relic workflows.

DEBUG CODE: remove this module and the marked call sites to remove capture.
No game input is sent here. Capture failures are logged once and do not alter
the existing purchase, favorite, or sell decisions.
"""

import csv
import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from core.ocr_engine import is_blank_line
from core.utils import get_resource_path, get_user_data_path


LINE_FIELDS = (
    "sample_id", "source", "mode", "line_number", "image", "visually_blank",
    "raw_ocr", "ocr_score", "game_text", "review_note",
)
ENTRY_FIELDS = (
    "sample_id", "source", "mode", "entry_number", "source_entry_numbers",
    "merged", "raw_entry", "corrected_text",
    "reported_corrected", "similarity", "exact_vocabulary_match",
    "closest_vocabulary", "closest_score", "top_3_candidates",
    "game_text", "review_note",
)
RAW_ENTRY_FIELDS = (
    "sample_id", "source", "mode", "entry_number", "raw_entry",
    "exact_vocabulary_match", "closest_vocabulary", "closest_score",
    "top_3_candidates", "game_text", "review_note",
)
CALL_FIELDS = (
    "sample_id", "source", "mode", "call_number", "retry", "input_text",
    "candidate_text", "similarity", "required_threshold",
    "accepted_by_corrector", "candidate_in_vocabulary",
    "closest_vocabulary", "closest_score",
    "game_text", "review_note",
)


def capture_enabled(settings):
    """Existing OCR debug setting, plus an environment override for developers."""
    value = os.environ.get("NRRELIC_OCR_DIAGNOSTICS", "").strip().lower()
    return bool(settings.get("ocr_debug", False)) or value in ("1", "true", "yes", "on")


def create_capture_session(settings, source, mode, log):
    if not capture_enabled(settings):
        return None
    try:
        session = OcrCaptureSession(source, mode, log)
        log(f"OCR 自动采集已开启，结果目录: {session.path}", "INFO")
        return session
    except Exception as exc:
        log(f"OCR 自动采集初始化失败: {exc}", "WARNING")
        return None


class OcrCaptureSession:
    """Write one evidence bundle per OCR attempt without retaining images in RAM."""

    def __init__(self, source, mode, log):
        self.source = source
        self.mode = mode
        self.log = log
        self.disabled = False
        parent = Path(os.environ.get("NRRELIC_OCR_DEBUG_DIR") or
                      get_user_data_path("debug_ocr/collections"))
        parent.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now():%Y%m%d_%H%M%S_%f}_{source}_{mode}_{os.getpid()}"
        self.path = parent / name
        self.path.mkdir()
        self.count = 0
        names = (["normal.txt", "normal_special.txt"] if mode == "normal"
                 else ["deepnight_pos.txt", "deepnight_neg.txt"])
        vocabularies = []
        for name in names:
            file = Path(get_resource_path(f"data/{name}"))
            vocabularies.append({"name": name, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()
                                 if file.exists() else None})
        self._write_json(self.path / "manifest.json", {
            "source": source, "mode": mode,
            "created": datetime.now().astimezone().isoformat(),
            "vocabulary": vocabularies,
            "note": "game_text 列须人工对照 screen.png 填写；visually_blank 只是图像估计",
        })

    @staticmethod
    def _write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _save_png(path, image):
        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            return False
        success, encoded = cv2.imencode(".png", image)
        if not success:
            return False
        encoded.tofile(path)
        return True

    @staticmethod
    def _append_csv(path, fields, rows):
        new_file = not path.exists()
        with path.open("a", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            if new_file:
                writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _candidates(text, corrector):
        if not corrector or not text:
            return []
        scores = [(word, corrector._calculate_similarity(text, word))
                  for word in dict.fromkeys(corrector.vocabulary)]
        scores.sort(key=lambda row: row[1], reverse=True)
        return [{"text": word, "score": round(score, 4)} for word, score in scores[:3]]

    def record(self, screen, line_images, observation, trace, match, engine,
               index, context=None):
        """Capture failures never change the caller's game action."""
        if self.disabled:
            return
        try:
            self._record(screen, line_images, observation, trace, match, engine,
                         index, context or {})
        except Exception as exc:
            self.disabled = True
            self.log(f"OCR 自动采集写入失败，已关闭本轮采集: {exc}", "WARNING")

    def record_navigation_check(self, screen, index, action, check):
        """DEBUG: keep a frame only when navigation remains ambiguous."""
        if self.disabled:
            return
        try:
            if action == "sale" and self.count:
                directory = self.path / "samples" / f"{self.count:05d}"
                stem = "after_f"
            else:
                directory = self.path / "navigation"
                directory.mkdir(exist_ok=True)
                stem = f"ambiguous_{index:05d}"
            saved = self._save_png(directory / f"{stem}.png", screen)
            self._write_json(directory / f"{stem}.json", {
                "next_index": index,
                "screen_image": f"{stem}.png" if saved else None,
                "last_action": action,
                "expected_box": check.box,
                "cursor_checked": check.cursor_checked,
                "detected_cursor": check.detected_box,
                "detail_change": check.detail_change,
                "detail_icon_change": check.detail_icon_change,
                "sale_amount_change": check.sale_change,
                "card_change": check.card_change,
                "navigation_confirmed": check.confirmed,
            })
        except Exception as exc:
            self.log(f"OCR 自动采集无法保存导航校验画面: {exc}", "WARNING")

    def _record(self, screen, line_images, observation, trace, match, engine,
                index, context):
        self.count += 1
        sample_id = f"{self.count:05d}"
        sample_dir = self.path / "samples" / sample_id
        sample_dir.mkdir(parents=True)
        screen_saved = self._save_png(sample_dir / "screen.png", screen)
        attempts = trace.get("attempts", [])
        final_lines = attempts[-1].get("lines", []) if attempts else []
        line_rows = []
        for number, image in enumerate(line_images, 1):
            filename = f"line_{number}.png"
            saved = self._save_png(sample_dir / filename, image)
            line = final_lines[number - 1] if number <= len(final_lines) else {}
            line_rows.append({
                "sample_id": sample_id, "source": self.source, "mode": self.mode,
                "line_number": number,
                "image": f"samples/{sample_id}/{filename}" if saved else "",
                "visually_blank": is_blank_line(image),
                "raw_ocr": line.get("text", ""), "ocr_score": line.get("score", 0),
                "game_text": "", "review_note": "",
            })
        self._append_csv(self.path / "lines_review.csv", LINE_FIELDS, line_rows)

        corrector = engine.corrector
        vocabulary = set(corrector.vocabulary) if corrector else set()
        raw_entries = trace.get("entries_after_separator_repair", [])
        raw_entry_rows = []
        for number, raw_entry in enumerate(raw_entries, 1):
            suggestions = self._candidates(raw_entry, corrector)
            raw_entry_rows.append({
                "sample_id": sample_id, "source": self.source, "mode": self.mode,
                "entry_number": number, "raw_entry": raw_entry,
                "exact_vocabulary_match": raw_entry in vocabulary,
                "closest_vocabulary": suggestions[0]["text"] if suggestions else "",
                "closest_score": suggestions[0]["score"] if suggestions else "",
                "top_3_candidates": json.dumps(suggestions, ensure_ascii=False),
                "game_text": "", "review_note": "",
            })
        self._append_csv(self.path / "raw_entries_review.csv", RAW_ENTRY_FIELDS, raw_entry_rows)

        corrections = trace.get("correction_trace", [])
        correction_sources = trace.get("correction_sources", [])
        entry_rows = []
        for number, item in enumerate(corrections, 1):
            corrected = item.get("text", "")
            suggestions = self._candidates(corrected, corrector)
            source = correction_sources[number - 1] if number <= len(correction_sources) else {}
            entry_rows.append({
                "sample_id": sample_id, "source": self.source, "mode": self.mode,
                "entry_number": number,
                "source_entry_numbers": ",".join(map(str, source.get("entry_numbers", []))),
                "merged": source.get("merged", False),
                "raw_entry": source.get("raw_text", ""),
                "corrected_text": corrected,
                "reported_corrected": item.get("is_corrected", False),
                "similarity": item.get("similarity", 0),
                "exact_vocabulary_match": corrected in vocabulary,
                "closest_vocabulary": suggestions[0]["text"] if suggestions else "",
                "closest_score": suggestions[0]["score"] if suggestions else "",
                "top_3_candidates": json.dumps(suggestions, ensure_ascii=False),
                "game_text": "", "review_note": "",
            })
        self._append_csv(self.path / "entries_review.csv", ENTRY_FIELDS, entry_rows)

        call_rows = []
        for number, item in enumerate(trace.get("correction_calls", []), 1):
            suggestions = self._candidates(item.get("input_text", ""), corrector)
            call_rows.append({
                "sample_id": sample_id, "source": self.source, "mode": self.mode,
                "call_number": number, **item,
                "candidate_in_vocabulary": item.get("candidate_text") in vocabulary,
                "closest_vocabulary": suggestions[0]["text"] if suggestions else "",
                "closest_score": suggestions[0]["score"] if suggestions else "",
                "game_text": "", "review_note": "",
            })
        self._append_csv(self.path / "correction_calls.csv", CALL_FIELDS, call_rows)

        record = {
            "sample_id": sample_id,
            "timestamp": datetime.now().astimezone().isoformat(),
            "source": self.source, "mode": self.mode, "index": index,
            "context": context,
            "screen_image": f"samples/{sample_id}/screen.png" if screen_saved else None,
            "screen_size": [screen.shape[1], screen.shape[0]] if screen_saved else None,
            "line_images": [row["image"] for row in line_rows],
            "line_observations": line_rows,
            "ocr_trace": trace,
            "ocr_result": observation,
            "match_result": asdict(match) if match is not None else None,
        }
        self._write_json(sample_dir / "sample.json", record)
        with (self.path / "samples.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
