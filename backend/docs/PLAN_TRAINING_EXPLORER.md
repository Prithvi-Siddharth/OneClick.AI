# Implementation Plan - Folder-Based Catalog Explorer for Model Training

This plan aims to replace the basic dataset selection dropdown in the Model Training page with the advanced, folder-aware catalog explorer used in the Preprocessing Studio. This will provide a consistent user experience and allow users to navigate deep folder structures to find their training data.

## Proposed Changes

### Frontend - Model Training

#### [MODIFY] [train_model.html](file:///c:/Users/kanak/OneClick.AI/backend/app/templates/train_model.html)
- **UI Update**:
    - Replace the `<select>` dropdown inside `catalogModal` with:
        - A `catalogBreadcrumbs` div for navigation path.
        - A `catalogExplorer` div for displaying folders and files.
        - A selection status indicator.
    - Standardize the CSS for the explorer items (hover effects, selected state).
- **JS Logic Integration**:
    - Add `loadCatalogContents(folderId)` to fetch folder/file lists via AJAX.
    - Add `renderBreadcrumbs(crumbs)` to update the navigation path dynamically.
    - Add `renderExplorer(data)` to generate the folder/file UI.
    - Add `selectDataset(el)` to handle item selection within the explorer.
    - Update `catalogForm` submission to use the `dataset_id` selected via the explorer.

### Backend - Synchronization

- No changes required to `data_catalog.py` as `/api/catalog/contents` is already generalized.
- Ensure `train_model_page` in `training.py` continues to provide fallback `active_dataset` context if needed.

## Verification Plan

### Automated Tests
- Use the browser tool to:
    1. Navigate to the Model Training page.
    2. Open the "Connect from Catalog" modal.
    3. Verify that folders are displayed and can be navigated.
    4. Verify that breadcrumbs update correctly when entering subfolders.
    5. Select a dataset, click "Confirm", and verify the page reloads with the correct dataset loaded.

### Manual Verification
- Verify that the UI aesthetics (icons, colors, glassmorphism) are consistent between the Training and Preprocessing explorers.
- Test "Back to Root" navigation within the explorer.
