# Data Preprocessing Pipeline Implementation Guide

This document outlines the workflow, architecture, and step-by-step instructions for implementing the data preprocessing feature. This feature allows users to upload raw data, apply cleaning transformations, and save the result as a permanent dataset.

## 1. Workflow Overview

The goal is to bridge the gap between "temporary raw uploads" and "clean permanent datasets".

### User Journey
1.  **Upload**: User uploads a file via the "Preprocessing" page.
    *   *System*: Saves to `temporary_datasets` (S3 + DB) and returns a `temporary_dataset_id`.
2.  **Configuration**: User selects cleaning options (e.g., "Drop Missing Values", "Remove Duplicates").
3.  **Processing**: User clicks "Process".
    *   *System*: Reads the temporary file, applies transformations, uploads the result to the permanent `datasets` location, and returns the new `dataset_id`.
4.  **Result**: User is shown a success message and can view the new dataset in the Dashboard.

---

## 2. Technical Implementation Architecture

### Backend Components

#### A. New Service: `PreprocessingService`
**Location**: `backend/app/services/preprocessing.py` (New File)
**Responsibility**: Handle all Pandas data transformations.

*   **Function**: `clean_dataset(df: DataFrame, options: PreprocessingOptions) -> DataFrame`
    *   **Logic**:
        *   If `options.drop_duplicates` is True -> Apply `df.drop_duplicates()`.
        *   If `options.handle_missing_values` is 'drop' -> Apply `df.dropna()`.
        *   If `options.handle_missing_values` is 'mean' -> Fill numeric NaNs with column means.
        *   (Future) Add normalization or categorical encoding support.

#### B. Review Schemas
**Location**: `backend/app/schemas.py`
**Responsibility**: Define the contract for the API.

*   **Model**: `PreprocessingOptions`
    *   fields: `drop_duplicates` (bool), `handle_missing_values` (enum/str).
*   **Model**: `ProcessDatasetRequest`
    *   fields: `temporary_dataset_id` (int), `options` (PreprocessingOptions).

#### C. New API Endpoint
**Location**: `backend/app/main.py`
**Route**: `POST /process_dataset`

**Workflow Logic**:
1.  **Validation**: Verify `temporary_dataset_id` belongs to the logged-in user.
2.  **Fetch**: Retrieve the S3 Key for the temporary dataset.
3.  **Read**: Use `s3_operations.read_dataset_from_s3` (or similar low-level S3 read) to pull the file into a Pandas DataFrame.
4.  **Transform**: Call `PreprocessingService.clean_dataset(df, options)`.
5.  **Save**:
    *   Convert the cleaned DataFrame to CSV/JSON (matching original format).
    *   Generate a new permanent S3 key (e.g., `user_id/datasets/processed_timestamp.csv`).
    *   Upload using `s3_operations.upload_file_to_s3`.
6.  **Record**: Create a new entry in the `Dataset` table (permanent) with the new metadata (row count, file size, S3 key).
7.  **Response**: Return the new `dataset_id`.

---

## 3. Frontend Implementation Steps

**Location**: `backend/app/templates/preprocessing.html`

### Steps:
1.  **State Management**:
    *   Add a variable in the `<script>` section to store the `temporary_dataset_id` received after the initial upload.
    
2.  **UI Additions**:
    *   Create a "Configuration Section" `<div>` that is initially hidden.
    *   Show this section only after a successful temporary upload.
    *   **Controls**:
        *   Checkbox: "Remove Duplicate Rows"
        *   Dropdown: "Handle Missing Values" (Options: Keep, Drop Rows, Fill with Mean)
    
3.  **Process Action**:
    *   Update the "Process" button `onclick` event:
        *   Validation: Ensure a file has been uploaded (check `temporary_dataset_id`).
        *   Payload Construction: Create a JSON object matching `ProcessDatasetRequest`.
        *   API Call: `fetch('/process_dataset', { method: 'POST', ... })`.
        *   Feedback: Show a "Processing..." spinner.
    *   **On Success**: Redirect to the Dashboard or show a "Processing Complete" modal with a link to the new dataset.

---

## 4. Verification Plan

### Manual Testing Checklist
1.  **Duplicate Removal**: Upload a CSV with known duplicate rows. Select "Remove Duplicates". Verify the resulting dataset row count is lower.
2.  **Missing Values**: Upload a CSV with empty cells. Select "Fill with Mean". Verify the resulting dataset has no NaNs.
3.  **Permissions**: Try to process a dataset ID that does not belong to the current user (should fail).
4.  **End-to-End**: Upload -> Process -> View in Dashboard -> Download. Ensure file integrity.
