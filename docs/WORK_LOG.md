# Development Work Log - April 6, 2026

This log tracks the progress of features and fixes implemented during today's session.

## COMPLETED TASKS

### 1. Catalog Enhancements
- [x] Add `uploadModalOverlay` HTML to `view_datasets.html`
- [x] Add CSS for the upload modal in `view_datasets.html`
- [x] Support uploading to specific folders in Data Catalog
- [x] Create `/api/catalog/contents` for folder-aware exploration
- [x] Update `preprocessing.html` with Folder Breadcrumbs and Explorer
- [x] Update `view_models.html` with folder selection for model uploads
- [x] Add folder exploration to `deploy.html` and `test_model.html`

### 2. Search & UI Fixes
- [x] Standardize Search Logic (Name OR Date) across all catalogs
- [x] Fix Modal Positioning in Model Catalog (Ensured `position: fixed` and centered)
- [x] Resolved Stacking Context issues by moving modal fragments to global blocks

### 3. Folder Management (Deletions)
- [x] Implement `DELETE /api/delete_folder/{folder_id}` with ownership validation
- [x] Added backend "Empty-Check" to prevent deleting folders with active items
- [x] Integrated Delete UI (Trash icons) into Data and Model catalog tables

### 4. Training Integration
- [x] Upgraded `train_model.html` with the advanced Folder Explorer
- [x] Linked explorer selection to `/connect_dataset_train` for seamless data ingestion

### 5. Chatbot Resource Management
- [x] Created `ChatUsage` database model to track daily message counts
- [x] Implemented `/api/chat` backend proxy to control external API costs
- [x] Enforced **5 chats per day** limit per user
- [x] Updated Frontend JS to handle "Daily limit reached" status gracefully
- [x] Added detailed diagnostics for 502 Bad Gateway troubleshooting

---

**Summary**: All planned features for the day have been successfully implemented, documented, and verified.
