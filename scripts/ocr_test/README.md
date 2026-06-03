# OCR accuracy gate

idea-validator (verdict: BUILD) flagged one kill-shot risk: OCR accuracy on
Indonesian thermal and handwritten field receipts, photographed on cheap Android
phones. There is no published Bahasa OCR benchmark, so we measure it ourselves
before building the bot flows. Do not skip this.

## Protocol

1. Collect 10 real field receipts from the client (or representative samples):
   thermal prints, handwritten warung receipts, faded ones, bad-angle phone
   photos. The point is to test the worst realistic input, not clean scans.

2. Put the images in `scripts/ocr_test/receipts/` and write the ground truth in
   `scripts/ocr_test/ground_truth.json`:
   ```json
   [
     {"file": "receipt_01.jpg", "amount": 450000, "vendor": "SPBU Shell"},
     {"file": "receipt_02.jpg", "amount": 127500, "vendor": "Toko Bangunan Jaya"}
   ]
   ```
   Amounts are integer rupiah.

3. Run the harness:
   ```bash
   python scripts/ocr_test/run_ocr_test.py
   ```
   It runs each image through the Azure OpenAI vision model (gpt-5-mini by
   default, the model the bot actually uses for inline OCR) with a structured
   extraction prompt and compares the parsed amount against ground truth.

## Decision thresholds (amount-parse accuracy)

| Accuracy | Decision |
|----------|----------|
| `> 80%` | Ship as designed. Confirm-before-commit handles the rest. |
| `60-70%` | Ship, but design the confirm UX around correction being the expected case, not the edge. |
| `< 60%` | Defer. Go hybrid: extract what the model is confident on, ask the worker to type the amount when confidence is low. |

Vendor accuracy is secondary; the amount and the budget line are what the ledger
needs to be right. The confirm-before-commit step is in scope regardless of the
score; the score only decides how heavily the UX leans on correction.

`receipts/` and `ground_truth.json` hold client data and are gitignored.
