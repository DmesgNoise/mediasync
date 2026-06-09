document.addEventListener("DOMContentLoaded", () => {
    initRequestAppManagement();
    initDownloaderManagement();
});

function initRequestAppManagement() {
    const addRequestAppButton = document.querySelector("[data-add-request-app]");

    if (addRequestAppButton) {
        addRequestAppButton.addEventListener("click", () => {
            addRequestAppRow();
        });
    }

    document.querySelectorAll("[data-request-app-row]").forEach((row) => {
        wireRequestAppRow(row);
    });

    updateRequestAppEmptyState();
}

function addRequestAppRow() {
    const list = document.querySelector("[data-request-app-list]");

    if (!list) {
        return;
    }

    const row = createRequestAppRow();
    list.appendChild(row);
    wireRequestAppRow(row);
    setRequestAppEditing(row, true);
    updateRequestAppEmptyState();
}

function createRequestAppRow() {
    const row = document.createElement("div");
    row.className = "settings-source-item settings-integration-compact is-editing";
    row.dataset.requestAppRow = "";
    row.dataset.requestAppId = "";
    row.dataset.requestAppVersion = "";
    row.dataset.connectionValid = "false";
    row.dataset.editing = "true";

    row.innerHTML = `
        <img
            class="settings-source-logo"
            src="/static/img/seerr-logo.png"
            alt="Seerr"
            data-request-app-logo
        >

        <div class="settings-integration-main">
            <div class="settings-integration-static hidden" data-request-app-static>
                <div>
                    <div class="settings-source-name-static" data-request-app-static-name>New Request App</div>
                    <div class="settings-source-meta" data-request-app-static-meta>Not saved</div>
                    <div class="settings-integration-url" data-request-app-static-url></div>
                </div>
            </div>

            <div class="settings-source-edit" data-request-app-edit>
                <div class="settings-source-edit-title">Edit Request App</div>

                <div class="form-grid settings-source-form-grid">
                    <label>
                        <span>Request App Name</span>
                        <input name="app_name" type="text" placeholder="Enter request app name">
                    </label>

                    <label>
                        <span>Request App Type</span>
                        <select class="settings-select" name="app_type" data-request-app-type>
                            <option value="seerr" selected>Seerr</option>
                        </select>
                    </label>

                    <label>
                        <span>Server URL</span>
                        <input name="app_url" type="text" placeholder="Enter server URL">
                    </label>

                    <label>
                        <span>API Key</span>
                        <div class="settings-secret-row">
                            <input name="api_key" type="password" placeholder="Enter API key">
                            <button class="mini-action-button" type="button" data-request-app-toggle-secret>Show</button>
                        </div>
                    </label>
                </div>
            </div>

            <div class="settings-source-actions-compact settings-integration-actions">
                <button class="mini-action-button" type="button" data-request-app-test>Test Connection</button>
                <button class="mini-action-button hidden" type="button" data-request-app-edit-button>Edit</button>
                <button class="mini-action-button good" type="button" data-request-app-save disabled>Save Request App</button>
                <button class="mini-action-button danger" type="button" data-request-app-delete>Delete</button>
            </div>

            <div class="settings-result hidden" data-settings-result></div>
        </div>
    `;

    return row;
}

function wireRequestAppRow(row) {
    if (row.dataset.requestAppWired === "true") {
        return;
    }

    row.dataset.requestAppWired = "true";
    row.dataset.connectionValid = row.dataset.connectionValid || "false";
    row.dataset.requestAppVersion = row.dataset.requestAppVersion || "";
    row.dataset.editing = row.dataset.editing || "false";

    const testButton = row.querySelector("[data-request-app-test]");
    const editButton = row.querySelector("[data-request-app-edit-button]");
    const saveButton = row.querySelector("[data-request-app-save]");
    const deleteButton = row.querySelector("[data-request-app-delete]");
    const typeSelect = row.querySelector('select[name="app_type"]');
    const appNameInput = row.querySelector('input[name="app_name"]');
    const urlInput = row.querySelector('input[name="app_url"]');
    const apiKeyInput = row.querySelector('input[name="api_key"]');
    const secretButton = row.querySelector("[data-request-app-toggle-secret], [data-toggle-secret]");

    if (secretButton) {
        secretButton.addEventListener("click", () => {
            toggleSecretInput(secretButton);
        });
    }

    if (typeSelect) {
        typeSelect.addEventListener("change", () => {
            invalidateRequestAppConnection(row);
            syncRequestAppLogo(row);
        });
    }

    [urlInput, apiKeyInput].forEach((input) => {
        if (!input) {
            return;
        }

        input.addEventListener("input", () => {
            invalidateRequestAppConnection(row);
        });
    });

    if (appNameInput) {
        appNameInput.addEventListener("input", () => {
            markRequestAppUnsaved(row);
            updateRequestAppSaveState(row);
        });
    }

    if (testButton) {
        testButton.addEventListener("click", async () => {
            await testRequestApp(row);
        });
    }

    if (editButton) {
        editButton.addEventListener("click", () => {
            setRequestAppEditing(row, true);
        });
    }

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            await saveRequestApp(row);
        });
    }

    if (deleteButton) {
        deleteButton.addEventListener("click", () => {
            const appName = getRequestAppName(row) || "this request app";

            showRequestAppConfirmModal({
                title: `Delete ${appName}?`,
                body: `
                    <p>This will remove:</p>
                    <ul>
                        <li>Request app connection</li>
                        <li>Stored API key</li>
                    </ul>
                `,
                actionText: "Delete Request App",
                onConfirm: async () => {
                    if (row.dataset.requestAppId) {
                        const formData = new FormData();
                        formData.append("request_app_id", row.dataset.requestAppId);

                        const result = await requestAppFetchJson("/api/request-apps/delete", formData);

                        if (!result.success) {
                            showRequestAppResult(row, result);
                            return;
                        }
                    }

                    row.remove();
                    updateRequestAppEmptyState();
                },
            });
        });
    }

    syncRequestAppLogo(row);
    updateRequestAppStatic(row);
    setRequestAppEditing(row, row.dataset.editing === "true");
    updateRequestAppSaveState(row);
}

function setRequestAppEditing(row, editing) {
    row.dataset.editing = editing ? "true" : "false";
    row.classList.toggle("is-editing", editing);
    row.classList.toggle("is-saved", !editing);

    const staticBlock = row.querySelector("[data-request-app-static]");
    const editBlock = row.querySelector("[data-request-app-edit]");
    const editButton = row.querySelector("[data-request-app-edit-button]");
    const saveButton = row.querySelector("[data-request-app-save]");

    if (staticBlock) {
        staticBlock.classList.toggle("hidden", editing);
    }

    if (editBlock) {
        editBlock.classList.toggle("hidden", !editing);
    }

    if (editButton) {
        editButton.classList.toggle("hidden", editing);
    }

    if (saveButton) {
        saveButton.classList.toggle("hidden", !editing);
    }

    updateRequestAppSaveState(row);
}

function invalidateRequestAppConnection(row) {
    row.dataset.connectionValid = "false";
    row.dataset.requestAppVersion = "";

    const resultBox = row.querySelector("[data-settings-result]");

    if (resultBox) {
        resultBox.className = "settings-result hidden";
        resultBox.textContent = "";
    }

    markRequestAppUnsaved(row);
    updateRequestAppSaveState(row);
    updateRequestAppStatic(row);
}

function markRequestAppUnsaved(row) {
    const saveButton = row.querySelector("[data-request-app-save]");

    if (saveButton) {
        saveButton.textContent = "Save Request App";
    }
}

function syncRequestAppLogo(row) {
    const typeSelect = row.querySelector('select[name="app_type"]');
    const logo = row.querySelector("[data-request-app-logo]");

    if (!typeSelect || !logo) {
        return;
    }

    logo.src = `/static/img/${typeSelect.value}-logo.png`;
    logo.alt = formatRequestAppName(typeSelect.value);
}

async function testRequestApp(row) {
    const testButton = row.querySelector("[data-request-app-test]");
    const appType = row.querySelector('select[name="app_type"]')?.value || "seerr";
    const appUrl = row.querySelector('input[name="app_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";

    row.dataset.connectionValid = "false";
    row.dataset.requestAppVersion = "";
    updateRequestAppSaveState(row);
    updateRequestAppStatic(row);

    if (!appUrl || !apiKey) {
        showRequestAppResult(row, {
            success: false,
            message: "Enter a server URL and API key first.",
        });
        return;
    }

    showRequestAppResult(row, {
        success: true,
        message: "Testing connection...",
    });

    if (testButton) {
        testButton.disabled = true;
        testButton.textContent = "Testing...";
    }

    try {
        const formData = new FormData();
        formData.append("app_type", appType);
        formData.append("app_url", appUrl);
        formData.append("api_key", apiKey);

        const result = await requestAppFetchJson("/api/request-apps/test", formData);

        if (result.success) {
            row.dataset.connectionValid = "true";
            row.dataset.requestAppVersion = result.version || "Unknown";
        }

        updateRequestAppStatic(row);
        showRequestAppResult(row, result);
    } finally {
        if (testButton) {
            testButton.disabled = false;
            testButton.textContent = "Test Connection";
        }

        updateRequestAppSaveState(row);
    }
}

async function saveRequestApp(row) {
    if (row.dataset.connectionValid !== "true") {
        showRequestAppResult(row, {
            success: false,
            message: "Test the request app connection before saving.",
        });
        return;
    }

    const saveButton = row.querySelector("[data-request-app-save]");
    const appName = getRequestAppName(row);
    const appType = row.querySelector('select[name="app_type"]')?.value || "seerr";
    const appUrl = row.querySelector('input[name="app_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";

    if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = "Saving...";
    }

    const formData = new FormData();
    formData.append("request_app_id", row.dataset.requestAppId || "");
    formData.append("app_name", appName || formatRequestAppName(appType));
    formData.append("app_type", appType);
    formData.append("app_url", appUrl);
    formData.append("api_key", apiKey);

    const result = await requestAppFetchJson("/api/request-apps/save", formData);

    showRequestAppResult(row, result);

    if (result.success) {
        row.dataset.requestAppId = result.request_app_id;
        row.dataset.connectionValid = "true";
        row.dataset.requestAppVersion = result.version || row.dataset.requestAppVersion || "Unknown";

        updateRequestAppStatic(row);
        setRequestAppEditing(row, false);

        if (saveButton) {
            saveButton.textContent = "Save Request App";
        }

        updateRequestAppEmptyState();
        return;
    }

    if (saveButton) {
        saveButton.textContent = "Save Request App";
    }

    updateRequestAppSaveState(row);
}

function updateRequestAppStatic(row) {
    const appName = getRequestAppName(row) || "Request App";
    const appType = row.querySelector('select[name="app_type"]')?.value || "seerr";
    const appUrl = row.querySelector('input[name="app_url"]')?.value.trim() || "";
    const version = row.dataset.requestAppVersion || "Unknown";
    const connected = row.dataset.connectionValid === "true";

    const nameEl = row.querySelector("[data-request-app-static-name]");
    const metaEl = row.querySelector("[data-request-app-static-meta]");
    const urlEl = row.querySelector("[data-request-app-static-url]");

    if (nameEl) {
        nameEl.textContent = appName || formatRequestAppName(appType);
    }

    if (metaEl) {
        metaEl.innerHTML = `v${escapeIntegrationHtml(version)} <span>•</span> ${connected ? "Connected" : "Disconnected"}`;
    }

    if (urlEl) {
        urlEl.textContent = appUrl;
    }
}

function getRequestAppName(row) {
    return row.querySelector('input[name="app_name"]')?.value.trim() || "";
}

function updateRequestAppSaveState(row) {
    const saveButton = row.querySelector("[data-request-app-save]");

    if (!saveButton) {
        return;
    }

    saveButton.disabled = row.dataset.connectionValid !== "true";
}

function updateRequestAppEmptyState() {
    const rows = document.querySelectorAll("[data-request-app-row]");
    const emptyBox = document.querySelector("[data-request-app-empty]");

    if (!emptyBox) {
        return;
    }

    if (rows.length) {
        emptyBox.classList.add("hidden");
    } else {
        emptyBox.classList.remove("hidden");
    }
}

function initDownloaderManagement() {
    const addDownloaderButton = document.querySelector("[data-add-downloader]");

    if (addDownloaderButton) {
        addDownloaderButton.addEventListener("click", () => {
            addDownloaderRow();
        });
    }

    document.querySelectorAll("[data-downloader-row]").forEach((row) => {
        wireDownloaderRow(row);
    });

    updateDownloaderEmptyState();
}

function addDownloaderRow() {
    const list = document.querySelector("[data-downloader-list]");

    if (!list) {
        return;
    }

    const row = createDownloaderRow();
    list.appendChild(row);
    wireDownloaderRow(row);
    setDownloaderEditing(row, true);
    updateDownloaderEmptyState();
}

function createDownloaderRow() {
    const row = document.createElement("div");
    row.className = "settings-source-item settings-integration-compact is-editing";
    row.dataset.downloaderRow = "";
    row.dataset.downloaderId = "";
    row.dataset.downloaderVersion = "";
    row.dataset.connectionValid = "false";
    row.dataset.editing = "true";

    row.innerHTML = `
        <img
            class="settings-source-logo"
            src="/static/img/sab-logo.png"
            alt="SABnzbd"
            data-downloader-logo
        >

        <div class="settings-integration-main">
            <div class="settings-integration-static hidden" data-downloader-static>
                <div>
                    <div class="settings-source-name-static" data-downloader-static-name>New Downloader</div>
                    <div class="settings-source-meta" data-downloader-static-meta>Not saved</div>
                    <div class="settings-integration-url" data-downloader-static-url></div>
                </div>
            </div>

            <div class="settings-source-edit" data-downloader-edit>
                <div class="settings-source-edit-title">Edit Downloader</div>

                <div class="form-grid settings-source-form-grid">
                    <label>
                        <span>Downloader Name</span>
                        <input name="downloader_name" type="text" placeholder="Enter downloader name">
                    </label>

                    <label>
                        <span>Downloader Type</span>
                        <select class="settings-select" name="downloader_type" data-downloader-type>
                            <option value="sabnzbd" selected>SABnzbd</option>
                        </select>
                    </label>

                    <label>
                        <span>Server URL</span>
                        <input name="downloader_url" type="text" placeholder="Enter server URL">
                    </label>

                    <label>
                        <span>API Key</span>
                        <div class="settings-secret-row">
                            <input name="api_key" type="password" placeholder="Enter API key">
                            <button class="mini-action-button" type="button" data-downloader-toggle-secret>Show</button>
                        </div>
                    </label>
                </div>
            </div>

            <div class="settings-source-actions-compact settings-integration-actions">
                <button class="mini-action-button" type="button" data-downloader-test>Test Connection</button>
                <button class="mini-action-button hidden" type="button" data-downloader-edit-button>Edit</button>
                <button class="mini-action-button good" type="button" data-downloader-save disabled>Save Downloader</button>
                <button class="mini-action-button danger" type="button" data-downloader-delete>Delete</button>
            </div>

            <div class="settings-result hidden" data-settings-result></div>
        </div>
    `;

    return row;
}

function wireDownloaderRow(row) {
    if (row.dataset.downloaderWired === "true") {
        return;
    }

    row.dataset.downloaderWired = "true";
    row.dataset.connectionValid = row.dataset.connectionValid || "false";
    row.dataset.downloaderVersion = row.dataset.downloaderVersion || "";
    row.dataset.editing = row.dataset.editing || "false";

    const testButton = row.querySelector("[data-downloader-test]");
    const editButton = row.querySelector("[data-downloader-edit-button]");
    const saveButton = row.querySelector("[data-downloader-save]");
    const deleteButton = row.querySelector("[data-downloader-delete]");
    const typeSelect = row.querySelector('select[name="downloader_type"]');
    const nameInput = row.querySelector('input[name="downloader_name"]');
    const urlInput = row.querySelector('input[name="downloader_url"]');
    const apiKeyInput = row.querySelector('input[name="api_key"]');
    const secretButton = row.querySelector("[data-downloader-toggle-secret], [data-toggle-secret]");

    if (secretButton) {
        secretButton.addEventListener("click", () => {
            toggleSecretInput(secretButton);
        });
    }

    if (typeSelect) {
        typeSelect.addEventListener("change", () => {
            invalidateDownloaderConnection(row);
            syncDownloaderLogo(row);
        });
    }

    [urlInput, apiKeyInput].forEach((input) => {
        if (!input) {
            return;
        }

        input.addEventListener("input", () => {
            invalidateDownloaderConnection(row);
        });
    });

    if (nameInput) {
        nameInput.addEventListener("input", () => {
            markDownloaderUnsaved(row);
            updateDownloaderSaveState(row);
        });
    }

    if (testButton) {
        testButton.addEventListener("click", async () => {
            await testDownloader(row);
        });
    }

    if (editButton) {
        editButton.addEventListener("click", () => {
            setDownloaderEditing(row, true);
        });
    }

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            await saveDownloader(row);
        });
    }

    if (deleteButton) {
        deleteButton.addEventListener("click", () => {
            const downloaderName = getDownloaderName(row) || "this downloader";

            showRequestAppConfirmModal({
                title: `Delete ${downloaderName}?`,
                body: `
                    <p>This will remove:</p>
                    <ul>
                        <li>Downloader connection</li>
                        <li>Stored API key</li>
                    </ul>
                `,
                actionText: "Delete Downloader",
                onConfirm: async () => {
                    if (row.dataset.downloaderId) {
                        const formData = new FormData();
                        formData.append("downloader_id", row.dataset.downloaderId);

                        const result = await requestAppFetchJson("/api/downloaders/delete", formData);

                        if (!result.success) {
                            showDownloaderResult(row, result);
                            return;
                        }
                    }

                    row.remove();
                    updateDownloaderEmptyState();
                },
            });
        });
    }

    syncDownloaderLogo(row);
    updateDownloaderStatic(row);
    setDownloaderEditing(row, row.dataset.editing === "true");
    updateDownloaderSaveState(row);
}

function setDownloaderEditing(row, editing) {
    row.dataset.editing = editing ? "true" : "false";
    row.classList.toggle("is-editing", editing);
    row.classList.toggle("is-saved", !editing);

    const staticBlock = row.querySelector("[data-downloader-static]");
    const editBlock = row.querySelector("[data-downloader-edit]");
    const editButton = row.querySelector("[data-downloader-edit-button]");
    const saveButton = row.querySelector("[data-downloader-save]");

    if (staticBlock) {
        staticBlock.classList.toggle("hidden", editing);
    }

    if (editBlock) {
        editBlock.classList.toggle("hidden", !editing);
    }

    if (editButton) {
        editButton.classList.toggle("hidden", editing);
    }

    if (saveButton) {
        saveButton.classList.toggle("hidden", !editing);
    }

    updateDownloaderSaveState(row);
}

function invalidateDownloaderConnection(row) {
    row.dataset.connectionValid = "false";
    row.dataset.downloaderVersion = "";

    const resultBox = row.querySelector("[data-settings-result]");

    if (resultBox) {
        resultBox.className = "settings-result hidden";
        resultBox.textContent = "";
    }

    markDownloaderUnsaved(row);
    updateDownloaderSaveState(row);
    updateDownloaderStatic(row);
}

function markDownloaderUnsaved(row) {
    const saveButton = row.querySelector("[data-downloader-save]");

    if (saveButton) {
        saveButton.textContent = "Save Downloader";
    }
}

function syncDownloaderLogo(row) {
    const typeSelect = row.querySelector('select[name="downloader_type"]');
    const logo = row.querySelector("[data-downloader-logo]");

    if (!typeSelect || !logo) {
        return;
    }

    logo.src = `/static/img/${normalizeDownloaderLogoName(typeSelect.value)}-logo.png`;
    logo.alt = formatDownloaderName(typeSelect.value);
}

async function testDownloader(row) {
    const testButton = row.querySelector("[data-downloader-test]");
    const downloaderType = row.querySelector('select[name="downloader_type"]')?.value || "sabnzbd";
    const downloaderUrl = row.querySelector('input[name="downloader_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";

    row.dataset.connectionValid = "false";
    row.dataset.downloaderVersion = "";
    updateDownloaderSaveState(row);
    updateDownloaderStatic(row);

    if (!downloaderUrl || !apiKey) {
        showDownloaderResult(row, {
            success: false,
            message: "Enter a server URL and API key first.",
        });
        return;
    }

    showDownloaderResult(row, {
        success: true,
        message: "Testing connection...",
    });

    if (testButton) {
        testButton.disabled = true;
        testButton.textContent = "Testing...";
    }

    try {
        const formData = new FormData();
        formData.append("downloader_type", downloaderType);
        formData.append("downloader_url", downloaderUrl);
        formData.append("api_key", apiKey);

        const result = await requestAppFetchJson("/api/downloaders/test", formData);

        if (result.success) {
            row.dataset.connectionValid = "true";
            row.dataset.downloaderVersion = result.version || "Unknown";
        }

        updateDownloaderStatic(row);
        showDownloaderResult(row, result);
    } finally {
        if (testButton) {
            testButton.disabled = false;
            testButton.textContent = "Test Connection";
        }

        updateDownloaderSaveState(row);
    }
}

async function saveDownloader(row) {
    if (row.dataset.connectionValid !== "true") {
        showDownloaderResult(row, {
            success: false,
            message: "Test the downloader connection before saving.",
        });
        return;
    }

    const saveButton = row.querySelector("[data-downloader-save]");
    const downloaderName = getDownloaderName(row);
    const downloaderType = row.querySelector('select[name="downloader_type"]')?.value || "sabnzbd";
    const downloaderUrl = row.querySelector('input[name="downloader_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";

    if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = "Saving...";
    }

    const formData = new FormData();
    formData.append("downloader_id", row.dataset.downloaderId || "");
    formData.append("downloader_name", downloaderName || formatDownloaderName(downloaderType));
    formData.append("downloader_type", downloaderType);
    formData.append("downloader_url", downloaderUrl);
    formData.append("api_key", apiKey);

    const result = await requestAppFetchJson("/api/downloaders/save", formData);

    showDownloaderResult(row, result);

    if (result.success) {
        row.dataset.downloaderId = result.downloader_id;
        row.dataset.connectionValid = "true";
        row.dataset.downloaderVersion = result.version || row.dataset.downloaderVersion || "Unknown";

        updateDownloaderStatic(row);
        setDownloaderEditing(row, false);

        if (saveButton) {
            saveButton.textContent = "Save Downloader";
        }

        updateDownloaderEmptyState();
        return;
    }

    if (saveButton) {
        saveButton.textContent = "Save Downloader";
    }

    updateDownloaderSaveState(row);
}

function updateDownloaderStatic(row) {
    const downloaderName = getDownloaderName(row) || "Downloader";
    const downloaderType = row.querySelector('select[name="downloader_type"]')?.value || "sabnzbd";
    const downloaderUrl = row.querySelector('input[name="downloader_url"]')?.value.trim() || "";
    const version = row.dataset.downloaderVersion || "Unknown";
    const connected = row.dataset.connectionValid === "true";

    const nameEl = row.querySelector("[data-downloader-static-name]");
    const metaEl = row.querySelector("[data-downloader-static-meta]");
    const urlEl = row.querySelector("[data-downloader-static-url]");

    if (nameEl) {
        nameEl.textContent = downloaderName || formatDownloaderName(downloaderType);
    }

    if (metaEl) {
        metaEl.innerHTML = `v${escapeIntegrationHtml(version)} <span>•</span> ${connected ? "Connected" : "Disconnected"}`;
    }

    if (urlEl) {
        urlEl.textContent = downloaderUrl;
    }
}

function getDownloaderName(row) {
    return row.querySelector('input[name="downloader_name"]')?.value.trim() || "";
}

function updateDownloaderSaveState(row) {
    const saveButton = row.querySelector("[data-downloader-save]");

    if (!saveButton) {
        return;
    }

    saveButton.disabled = row.dataset.connectionValid !== "true";
}

function updateDownloaderEmptyState() {
    const rows = document.querySelectorAll("[data-downloader-row]");
    const emptyBox = document.querySelector("[data-downloader-empty]");

    if (!emptyBox) {
        return;
    }

    if (rows.length) {
        emptyBox.classList.add("hidden");
    } else {
        emptyBox.classList.remove("hidden");
    }
}

function showDownloaderResult(container, result) {
    showRequestAppResult(container, result);
}

function formatRequestAppName(appType) {
    const labels = {
        seerr: "Seerr",
        overseerr: "Overseerr",
        ombi: "Ombi",
    };

    return labels[appType] || appType;
}

function formatDownloaderName(downloaderType) {
    const labels = {
        sab: "SABnzbd",
        sabnzbd: "SABnzbd",
    };

    return labels[downloaderType] || downloaderType;
}

function normalizeDownloaderLogoName(downloaderType) {
    if (downloaderType === "sabnzbd") {
        return "sab";
    }

    return downloaderType;
}

async function requestAppFetchJson(url, formData) {
    try {
        const response = await fetch(url, {
            method: "POST",
            body: formData,
        });

        return await response.json();
    } catch (error) {
        return {
            success: false,
            message: "Request failed.",
        };
    }
}

function showRequestAppResult(container, result) {
    const resultBox = container.querySelector("[data-settings-result]");

    if (!resultBox) {
        return;
    }

    resultBox.className = `settings-result ${result.success ? "good" : "warning"}`;
    resultBox.textContent = result.message || (result.success ? "Success." : "Failed.");
}

function showRequestAppConfirmModal({ title, body, actionText, onConfirm }) {
    const modal = document.getElementById("confirm-modal");
    const titleEl = document.getElementById("confirm-modal-title");
    const bodyEl = document.getElementById("confirm-modal-body");
    const actionEl = document.getElementById("confirm-modal-action");

    if (!modal || !titleEl || !bodyEl || !actionEl) {
        return;
    }

    const close = () => {
        modal.classList.add("hidden");
        modal.setAttribute("aria-hidden", "true");
        actionEl.onclick = null;
    };

    titleEl.textContent = title;
    bodyEl.innerHTML = body;
    actionEl.textContent = actionText;

    actionEl.onclick = async () => {
        await onConfirm();
        close();
    };

    modal.querySelectorAll("[data-confirm-cancel]").forEach((button) => {
        button.onclick = close;
    });

    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
}

function toggleSecretInput(button) {
    const secretRow = button.closest(".settings-secret-row");
    const input = secretRow ? secretRow.querySelector("input") : null;

    if (!input) {
        return;
    }

    if (input.type === "password") {
        input.type = "text";
        button.textContent = "Hide";
    } else {
        input.type = "password";
        button.textContent = "Show";
    }
}

function escapeIntegrationHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
