"""RunPod serverless worker: reads a supplier invoice photo and returns its lines as JSON.

Input:  {"image_base64": "<base64 image>", "mime": "image/jpeg"}
Output: {"invoice": {"supplier_name", "invoice_date", "lines": [{"name", "unit", "qty", "unit_cost"}]}}
        or {"error": "<reason>"}

The model only transcribes. Pricing, ceilings and approval happen in the HargaSync app.
"""

import base64
import binascii
import io
import json
import os
import re

MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen2.5-VL-7B-Instruct")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "1536"))

PROMPT = """You are reading a supplier invoice from a Malaysian grocery wholesaler.
Text may mix Bahasa Malaysia, English and Chinese. Transcribe it; do not guess missing values.
Return ONLY one JSON object, no commentary, in exactly this shape:
{"supplier_name": "...", "invoice_date": "YYYY-MM-DD or null",
 "lines": [{"name": "product name as printed", "unit": "unit or pack as printed, e.g. pek, botol, karton, kg",
            "qty": number, "unit_cost": number in ringgit per unit (not the line total)}]}
Skip subtotal, tax, discount and total rows."""

_model = None
_processor = None


def parse_model_json(text: str) -> dict:
    """Pull the outermost JSON object out of model output (handles ```json fences and chatter)."""
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model output contains no JSON object")
    return json.loads(text[start : end + 1])


def _load_model():
    global _model, _processor
    if _model is None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        _processor = AutoProcessor.from_pretrained(MODEL_ID, max_pixels=1280 * 28 * 28)
        _model = AutoModelForImageTextToText.from_pretrained(
            MODEL_ID, torch_dtype=torch.bfloat16, device_map="auto"
        )
    return _model, _processor


def _read_invoice(image) -> str:
    model, processor = _load_model()
    messages = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": PROMPT}]}]
    prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[prompt], images=[image], return_tensors="pt").to(model.device)
    output = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
    generated = output[:, inputs["input_ids"].shape[1] :]
    return processor.batch_decode(generated, skip_special_tokens=True)[0]


def handler(job: dict) -> dict:
    try:
        from PIL import Image

        data = base64.b64decode(job["input"]["image_base64"], validate=True)
        image = Image.open(io.BytesIO(data)).convert("RGB")
        return {"invoice": parse_model_json(_read_invoice(image))}
    except (KeyError, binascii.Error, OSError, ValueError) as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"}


if __name__ == "__main__":
    import runpod

    runpod.serverless.start({"handler": handler})
