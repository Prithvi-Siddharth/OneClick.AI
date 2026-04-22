# .xlsx Support — Error Report & Fixes

## Date: 2026-03-25

---

## Error 1: Internal Server Error on `/preprocess-dataset`

**Symptom:** Navigating to `/preprocess-dataset` after connecting an `.xlsx` file from the catalog returns "Internal Server Error".

**Root Cause:** The route handler at `backend/app/routers/preprocessing.py` (originally line 209) used `pd.read_csv()` hardcoded, which cannot parse `.xlsx` files.

**Status:** ✅ FIXED — Replaced with `read_df_from_s3()` helper that auto-detects file format from the S3 key extension.

---

## Error 2: WebSocket preview fails for `.xlsx` files

**Symptom:** The "get_preview" WebSocket action in the preprocessing studio would fail for `.xlsx` datasets.

**Root Cause:** The WebSocket handler (originally line 351) also used hardcoded `pd.read_csv()`.

**Status:** ✅ FIXED — Now uses `read_df_from_s3()`.

---

## Error 3: WebSocket preprocessing fails for `.xlsx` files

**Symptom:** The "apply_preprocessing" WebSocket action fails when loading `.xlsx` datasets from S3.

**Root Cause:** The preprocessing WebSocket handler (originally line 366) used hardcoded `pd.read_csv()`.

**Status:** ✅ FIXED — Now uses `read_df_from_s3()`.

---

## Error 4: Preview route always treats temporary datasets as CSV

**Symptom:** `/preview_temporary_dataset/{id}` would incorrectly parse `.xlsx` files as CSV.

**Root Cause:** The route passed `filename=f"temp_{temp_id}.csv"` to `read_dataset_from_s3()`, forcing CSV parsing regardless of actual file type.

**Status:** ✅ FIXED — Now uses the actual filename from the S3 key to preserve the correct extension.

---

## Remaining Risks (To Verify)

### Risk 1: Preprocessed file always saved as CSV
The `apply_preprocessing` WebSocket handler saves the result back to S3 as CSV via `processed_df.to_csv()` (line ~378). This means after preprocessing, the file format becomes CSV regardless of the original format. This is functionally correct but may be unexpected.

### Risk 2: `save_preprocessed_dataset` always names the file `.csv`
The `/save_preprocessed_dataset` route (line ~240) hardcodes `permanent_key = f"{user_id}/datasets/{timestamp}_processed.csv"`. After preprocessing, the saved file will always be CSV, which is fine since the preprocessing step converts it.

### Risk 3: `download_preprocessed_dataset` always names download as `.csv`
The `/download_preprocessed_dataset` route (line ~443) uses `filename=f"preprocessed_{dataset_id}.csv"`. Same reasoning — after preprocessing the file IS csv, so this is correct.

---

## Files Modified

- `backend/app/routers/preprocessing.py` — Added `read_df_from_s3()` helper, fixed 4 locations
