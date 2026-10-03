import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.ocr_engine import OCR_MODEL_FILES, LineOnlyRapidOCR, bundled_ocr_model_params


class OcrModelBundleTests(unittest.TestCase):
    def test_all_runtime_models_resolve_to_bundled_resource_directory(self):
        params = bundled_ocr_model_params()
        self.assertEqual(set(params), {'Rec.model_path'})
        self.assertEqual({Path(path).name for path in params.values()},
                         set(OCR_MODEL_FILES.values()))
        self.assertTrue(all(Path(path).is_file() for path in params.values()))
        self.assertTrue(all('resources\\models' in path or 'resources/models' in path
                            for path in params.values()))

    def test_missing_model_fails_before_rapidocr_can_download_one(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('core.ocr_engine.get_resource_path', return_value=directory):
                with self.assertRaisesRegex(FileNotFoundError, '缺少本地 OCR 模型文件'):
                    bundled_ocr_model_params()

    def test_runtime_initializes_only_the_local_recognizer(self):
        with patch('rapidocr.utils.download_file.DownloadFile.run',
                   side_effect=AssertionError('unexpected model download')):
            engine = LineOnlyRapidOCR(params={
                **bundled_ocr_model_params(),
                'Global.use_det': False,
                'Global.use_cls': False,
            })
        self.assertTrue(hasattr(engine, 'text_rec'))
        self.assertFalse(hasattr(engine, 'text_det'))
        self.assertFalse(hasattr(engine, 'text_cls'))

    def test_pyinstaller_spec_includes_every_runtime_model(self):
        spec = Path(__file__).resolve().parents[1] / 'NRrelic_Bot.spec'
        tree = ast.parse(spec.read_text(encoding='utf-8'))
        static_data = next(ast.literal_eval(node.value)
                           for node in tree.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == '_static_data'
                                   for target in node.targets))
        packaged = {source for source, destination in static_data
                    if destination == 'resources/models'}
        self.assertEqual(packaged, {
            f'resources/models/{name}' for name in OCR_MODEL_FILES.values()})


if __name__ == '__main__':
    unittest.main()
