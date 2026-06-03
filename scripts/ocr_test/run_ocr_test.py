"""OCR accuracy harness for Indonesian field receipts.

Runs each receipt image through an Azure OpenAI vision model (gpt-5-mini by
default) via its OpenAI-compatible v1 endpoint, compares the parsed amount against
ground truth, and reports accuracy against the decision thresholds in this
directory's README. gpt-5-mini is the runtime OCR model (vision inline), so the
gate measures the model the bot will actually use.

Usage:
    python scripts/ocr_test/run_ocr_test.py

Expects:
    scripts/ocr_test/receipts/*.jpg|png   (the test images, gitignored)
    scripts/ocr_test/ground_truth.json     (expected amounts, gitignored)
    AZURE_OPENAI_API_KEY, AZURE_OPENAI_BASE_URL in .env

NOTE: gpt-5-mini is reasoning-family. This call sends only model/messages/
response_format (no max_tokens, no temperature), which is the format it accepts;
max_tokens or temperature would 400. If the gate underperforms on gpt-5-mini
vision, the provisioned fallback is the dedicated OCR model mistral-document-ai-2512
(Foundry route ${AZURE_AI_FOUNDRY_ENDPOINT}providers/mistral/azure/ocr), not gpt-4o.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).parent
RECEIPTS_DIR = HERE / "receipts"
GROUND_TRUTH = HERE / "ground_truth.json"

EXTRACTION_PROMPT = (
    "Extract the financial details from this Indonesian receipt. "
    "Return ONLY a JSON object with keys: "
    "amount (integer rupiah, the grand total, no separators or currency symbol), "
    "vendor (string, the merchant name), "
    "date (string, ISO YYYY-MM-DD if visible else null), "
    "confidence (number 0-1, your confidence in the amount). "
    "If you cannot read the total, set amount to null."
)


def load_ground_truth() -> list[dict[str, object]]:
    if not GROUND_TRUTH.exists():
        sys.exit(f"missing ground truth file: {GROUND_TRUTH}")
    return json.loads(GROUND_TRUTH.read_text())


def extract_receipt(client: OpenAI, model: str, image_bytes: bytes) -> dict[str, object]:
    """Send the image to Azure OpenAI and parse the JSON response.

    Uses the OpenAI-compatible chat-completions vision format (image as a base64
    data URL). `model` is the Azure deployment name. Raises on an unparseable
    response rather than guessing.
    """
    b64 = base64.b64encode(image_bytes).decode("ascii")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    if content is None:
        raise ValueError("Azure OpenAI returned an empty response (no content)")
    return json.loads(content)


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    base_url = os.environ.get("AZURE_OPENAI_BASE_URL")
    if not api_key:
        sys.exit("set AZURE_OPENAI_API_KEY in .env for the OCR test")
    if not base_url:
        sys.exit("set AZURE_OPENAI_BASE_URL in .env (the .../openai/v1/ endpoint)")

    model = os.environ.get("LLM_MODEL", "gpt-5-mini")
    truth = load_ground_truth()

    client = OpenAI(api_key=api_key, base_url=base_url)

    correct = 0
    total = len(truth)
    print(f"Running OCR gate on {total} receipts with {model}\n")

    for entry in truth:
        path = RECEIPTS_DIR / str(entry["file"])
        if not path.exists():
            print(f"  SKIP {entry['file']}: file not found")
            continue
        parsed = extract_receipt(client, model, path.read_bytes())
        expected_amount = entry["amount"]
        got_amount = parsed.get("amount")
        ok = got_amount == expected_amount
        correct += int(ok)
        mark = "OK " if ok else "MISS"
        print(f"  {mark} {entry['file']}: expected {expected_amount}, got {got_amount}")

    accuracy = correct / total * 100 if total else 0.0
    print(f"\nAmount-parse accuracy: {accuracy:.0f}% ({correct}/{total})")
    if accuracy > 80:
        print("Decision: SHIP as designed.")
    elif accuracy >= 60:
        print("Decision: SHIP, design confirm-UX around correction as the norm.")
    else:
        print("Decision: DEFER, go hybrid (type amount when confidence is low).")


if __name__ == "__main__":
    main()
