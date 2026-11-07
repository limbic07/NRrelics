"""Color inference from the selected relic detail icon in a full game screenshot."""
from functools import lru_cache

import joblib
import numpy as np
from PIL import Image

from core.utils.path import get_resource_path


def extract_features(image):
    """Feature version 1; keep synchronized with the trained model."""
    rgb = np.asarray(image.convert("RGB").resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32) / 255
    hsv = np.asarray(image.convert("HSV").resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32) / 255
    chroma = rgb / np.maximum(rgb.max(axis=2, keepdims=True), .05)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    weights = sat * np.maximum(val, .15)
    features = []
    for y0, y1, x0, x1 in [(0, 32, 0, 32), (8, 24, 8, 24), (10, 22, 10, 22)]:
        mask = np.zeros((32, 32), dtype=bool)
        mask[y0:y1, x0:x1] = True
        hist, _ = np.histogram(hue[mask], bins=16, range=(0, 1), weights=weights[mask])
        features.extend((hist / max(hist.sum(), .001)).tolist())
        for data in [sat[mask], val[mask], chroma[:, :, 0][mask], chroma[:, :, 1][mask], chroma[:, :, 2][mask]]:
            features.extend(np.quantile(data, [.1, .25, .5, .75, .9]).tolist())
    for y in range(4):
        for x in range(4):
            ys, xs = slice(y * 8, (y + 1) * 8), slice(x * 8, (x + 1) * 8)
            for array in (rgb, chroma):
                features.extend(np.median(array[ys, xs], axis=(0, 1)).tolist())
            features.extend([float(np.median(sat[ys, xs])), float(np.median(val[ys, xs]))])
    features.extend(np.asarray(image.convert("L").resize((8, 8), Image.Resampling.LANCZOS), dtype=float).ravel() / 255)
    return np.asarray(features, dtype=np.float32)


@lru_cache(maxsize=1)
def _model():
    return joblib.load(get_resource_path('data/relic_color_model.joblib'))['model']


def recognize_color(screen, layout='storage'):
    """Return (color, confidence); unknown is never guessed into a color."""
    if screen is None or screen.size == 0:
        return '未知', 0.0
    h, w = screen.shape[:2]
    box = (929, 744, 1057, 892) if layout == 'storage' else (488, 532, 617, 680)
    x1, y1, x2, y2 = box
    crop = screen[round(y1*h/1080):round(y2*h/1080), round(x1*w/1920):round(x2*w/1920)]
    if crop.size == 0 or float(np.std(crop)) < 12:
        return '未知', 0.0
    try:
        image = Image.fromarray(crop[:, :, ::-1].copy())
        probabilities = _model().predict_proba(extract_features(image).reshape(1, -1))[0]
        index = int(np.argmax(probabilities))
        label = str(_model().classes_[index])
        confidence = float(probabilities[index])
        if label == '特殊遗物' or confidence < 0.75:
            return '未知', confidence
        return label, confidence
    except Exception as exc:
        from core.utils import log_debug
        log_debug(f'[颜色识别] 模型推理失败: {type(exc).__name__}: {exc}')
        return '未知', 0.0
