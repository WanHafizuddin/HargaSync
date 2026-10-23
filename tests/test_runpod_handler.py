import importlib.util
import unittest
from pathlib import Path

HANDLER_PATH = Path(__file__).resolve().parent.parent / "runpod" / "handler.py"


def load_handler():
    spec = importlib.util.spec_from_file_location("runpod_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParseModelJson(unittest.TestCase):
    def setUp(self):
        self.handler = load_handler()

    def test_plain_json(self):
        self.assertEqual(self.handler.parse_model_json('{"lines": []}'), {"lines": []})

    def test_fenced_json_with_chatter(self):
        text = 'Here is the invoice:\n```json\n{"supplier_name": "A", "lines": [{"name": "x"}]}\n```\nDone.'
        self.assertEqual(self.handler.parse_model_json(text)["supplier_name"], "A")

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            self.handler.parse_model_json("I cannot read this image.")

    def test_bad_input_returns_error(self):
        result = self.handler.handler({"input": {"image_base64": "not base64!!", "mime": "image/png"}})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
