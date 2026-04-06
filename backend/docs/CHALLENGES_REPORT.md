# Challenges Faced & Solutions - April 6, 2026

During the development and integration of new catalog and chatbot features, several technical roadblocks were encountered and resolved.

## 🧱 Technical Challenges

### 1. Stacking Context Conflict (Fixed Modals)
- **Challenge**: Modals in the Model and Data Catalogs were not centering correctly despite using `position: fixed`.
- **Cause**: The `filter` property on the `main` tag was creating a new Stacking Context, anchoring "fixed" elements to the container instead of the viewport.
- **Solution**: Moved the global `modals` block outside the `main` container, placing it directly before the closing `</body>` tag.

### 2. JavaScript Lifecycle & Execution Order
- **Challenge**: Event listeners in `base.html` were failing because they were executing before the modal fragments were fully rendered.
- **Solution**: Moved all `<script>` injections to the absolute end of the template (after the `modals` block) to ensure DOM availability.

### 3. Asynchronous Catalog Exploration
- **Challenge**: Synchronizing the folder explorer state (breadcrumb navigation, selection index) between the folder/file lists.
- **Solution**: Implemented a stateful JS logic for the `CatalogExplorer` that updates dynamically based on the `folder_id` returned from the API, mirroring the robust logic of the Preprocessing Studio.

### 4. 502/500 Errors in Chatbot Proxy
- **Challenge**: The new `/api/chat` proxy occasionally returned internal server errors or bad gateways.
- **Root Cause**: Missing `requests` dependency in the environment and a `NameError` for `Experiment` in the router.
- **Solution**: Added comprehensive error diagnostics and logging to `chatbot.py`, updated imports, and ensured the deployment environment had the `requests` library installed.

### 5. Folder Integrity Constraints
- **Challenge**: Deleting a folder that contains data would result in unexpected "orphaned" records in the database or S3.
- **Solution**: Enforced a strict "Empty-Check" constraint on the backend. A folder must contain **zero items** (subfolders, datasets, or models) before it can be removed.
