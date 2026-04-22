# Implementation Plan - Folder Deletion with Empty-Check

This plan adds the ability for users to delete folders in both the Data and Model catalogs. To prevent accidental data loss, folders can only be deleted if they are completely empty (no subfolders and no datasets/models).

## Proposed Changes

### Backend - Folder API

#### [MODIFY] [data_catalog.py](file:///c:/Users/kanak/OneClick.AI/backend/app/routers/data_catalog.py)
- Add a new endpoint `DELETE /api/delete_folder/{folder_id}`.
- Implement logic to:
    1. Verify folder ownership by the current user.
    2. Check for subfolders in the `folders` table.
    3. Check for items based on `folder_type`:
        - If `dataset`: Check for linked records in the `datasets` table.
        - If `model`: Check for linked records in the `experiments` table.
    4. Return a `400 Bad Request` if the folder is not empty.
    5. Delete the folder record if the check passes.

### Frontend - Data Catalog

#### [MODIFY] [view_datasets.html](file:///c:/Users/kanak/OneClick.AI/backend/app/templates/view_datasets.html)
- Add a delete button (red trash icon) in the folder rows of the main table.
- Add a JavaScript function `deleteFolder(folderId)` that:
    1. Asks for confirmation.
    2. Calls the `DELETE /api/delete_folder/{folder_id}` endpoint.
    3. Handles the "Folder is not empty" error by showing a user-friendly alert.
    4. Reloads the page on success.

### Frontend - Model Catalog

#### [MODIFY] [view_models.html](file:///c:/Users/kanak/OneClick.AI/backend/app/templates/view_models.html)
- Add a similar delete button in the folder rows.
- Add the corresponding `deleteFolder(folderId)` JavaScript function.

## Verification Plan

### Automated Tests
- Use the browser tool to:
    1. Create a new "Test Folder" in the Data Catalog.
    2. Verify it can be deleted immediately (since it's empty).
    3. Create another folder and upload a dataset into it.
    4. Attempt to delete this folder and verify that a "Folder is not empty" warning appears.
    5. Delete the dataset, then verify the folder can now be deleted.
    6. Repeat similar checks for the Model Catalog.

### Manual Verification
- Ensure the delete icons match the design aesthetic of the existing catalog buttons (glassmorphism/standard AI theme).
