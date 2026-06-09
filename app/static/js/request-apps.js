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
    updateRequestAppEmptyState();
}

function createRequestAppRow() {
    const row = document.createElement("div");
    row.className = "settings-source-item editable";
    row.dataset.requestAppRow = "";
    row.dataset.requestAppId = "";
    row.dataset.requestAppVersion = "";
    row.dataset.connectionValid = "false";

    row.innerHTML = `
        <div class="source-order-controls"></div>

        <img
            src="/static/img/seerr-logo.png"
            alt="Seerr"
            data-request-app-logo
        >

        <div class="settings-source-edit">
            <div class="form-grid">
                <label>
                    <span>Request App Name</span>
                    <input name="app_name" type="text" value="Seerr">
                </label>

                <label>
                    <span>Request App Type</span>
                    <select class="settings-select" name="app_type" data-request-app-type>
                        <option value="seerr" selected>Seerr</option>
                    </select>
                </label>

                <label>
                    <span>Server URL</span>
                    <input name="app_url" type="text" placeholder="https://seerr.example.com">
                </label>

                <label>
                    <span>API Key</span>
                    <div class="settings-secret-row">
                        <input name="api_key" type="password" placeholder="Enter API key">
                        <button class="mini-action-button" type="button" data-request-app-toggle-secret>Show</button>
                    </div>
                </label>
            </div>

            <div class="settings-description">
                New request app → test connection before saving.
            </div>

            <div class="settings-source-actions">
                <button class="mini-action-button" type="button" data-request-app-test>Test Connection</button>
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

    const testButton = row.querySelector("[data-request-app-test]");
    const saveButton = row.querySelector("[data-request-app-save]");
    const deleteButton = row.querySelector("[data-request-app-delete]");
    const typeSelect = row.querySelector('select[name="app_type"]');
    const appNameInput = row.querySelector('input[name="app_name"]');
    const urlInput = row.querySelector('input[name="app_url"]');
    const apiKeyInput = row.querySelector('input[name="api_key"]');
    const secretButton = row.querySelector("[data-request-app-toggle-secret], [data-toggle-secret]");

    if (secretButton) {
        secretButton.addEventListener("click", () => {
            const secretRow = secretButton.closest(".settings-secret-row");
            const input = secretRow ? secretRow.querySelector("input") : null;

            if (!input) {
                return;
            }

            if (input.type === "password") {
                input.type = "text";
                secretButton.textContent = "Hide";
            } else {
                input.type = "password";
                secretButton.textContent = "Show";
            }
        });
    }

    if (typeSelect) {
        typeSelect.addEventListener("change", () => {
            invalidateRequestAppConnection(row);
            syncRequestAppLogo(row);

            if (appNameInput && !appNameInput.value.trim()) {
                appNameInput.value = formatRequestAppName(typeSelect.value);
            }
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

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            await saveRequestApp(row);
        });
    }

    if (deleteButton) {
        deleteButton.addEventListener("click", () => {
            const appName = row.querySelector('input[name="app_name"]')?.value || "this request app";

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

            const description = row.querySelector(".settings-description");
            if (description) {
                description.textContent = `${formatRequestAppName(appType)} → v${row.dataset.requestAppVersion} → Connected`;
            }
        }

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
    const appName = row.querySelector('input[name="app_name"]')?.value.trim() || "";
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

        const description = row.querySelector(".settings-description");
        if (description) {
            description.textContent = `${formatRequestAppName(appType)} → v${row.dataset.requestAppVersion} → Connected`;
        }

        if (saveButton) {
            saveButton.textContent = "Saved ✓";
            saveButton.disabled = true;
        }

        updateRequestAppEmptyState();
        return;
    }

    if (saveButton) {
        saveButton.textContent = "Save Request App";
    }

    updateRequestAppSaveState(row);
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

function formatRequestAppName(appType) {
    const labels = {
        seerr: "Seerr",
        overseerr: "Overseerr",
        ombi: "Ombi",
    };

    return labels[appType] || appType;
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
    updateDownloaderEmptyState();
}

function createDownloaderRow() {
    const row = document.createElement("div");
    row.className = "settings-source-item editable";
    row.dataset.downloaderRow = "";
    row.dataset.downloaderId = "";
    row.dataset.downloaderVersion = "";
    row.dataset.connectionValid = "false";

    row.innerHTML = `
        <div class="source-order-controls"></div>

        <img
            src="/static/img/sab-logo.png"
            alt="SABnzbd"
            data-downloader-logo
        >

        <div class="settings-source-edit">
            <div class="form-grid">
                <label>
                    <span>Downloader Name</span>
                    <input name="downloader_name" type="text" value="SABnzbd">
                </label>

                <label>
                    <span>Downloader Type</span>
                    <select class="settings-select" name="downloader_type" data-downloader-type>
                        <option value="sabnzbd" selected>SABnzbd</option>
                    </select>
                </label>

                <label>
                    <span>Server URL</span>
                    <input name="downloader_url" type="text" placeholder="http://sabnzbd:8080">
                </label>

                <label>
                    <span>API Key</span>
                    <div class="settings-secret-row">
                        <input name="api_key" type="password" placeholder="Enter API key">
                        <button class="mini-action-button" type="button" data-downloader-toggle-secret>Show</button>
                    </div>
                </label>
            </div>

            <div class="settings-description">
                New downloader → test connection before saving.
            </div>

            <div class="settings-source-actions">
                <button class="mini-action-button" type="button" data-downloader-test>Test Connection</button>
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

    const testButton = row.querySelector("[data-downloader-test]");
    const saveButton = row.querySelector("[data-downloader-save]");
    const deleteButton = row.querySelector("[data-downloader-delete]");
    const typeSelect = row.querySelector('select[name="downloader_type"]');
    const nameInput = row.querySelector('input[name="downloader_name"]');
    const urlInput = row.querySelector('input[name="downloader_url"]');
    const apiKeyInput = row.querySelector('input[name="api_key"]');
    const secretButton = row.querySelector("[data-downloader-toggle-secret], [data-toggle-secret]");

    if (secretButton) {
        secretButton.addEventListener("click", () => {
            const secretRow = secretButton.closest(".settings-secret-row");
            const input = secretRow ? secretRow.querySelector("input") : null;

            if (!input) {
                return;
            }

            if (input.type === "password") {
                input.type = "text";
                secretButton.textContent = "Hide";
            } else {
                input.type = "password";
                secretButton.textContent = "Show";
            }
        });
    }

    if (typeSelect) {
        typeSelect.addEventListener("change", () => {
            invalidateDownloaderConnection(row);
            syncDownloaderLogo(row);

            if (nameInput && !nameInput.value.trim()) {
                nameInput.value = formatDownloaderName(typeSelect.value);
            }
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

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            await saveDownloader(row);
        });
    }

    if (deleteButton) {
        deleteButton.addEventListener("click", () => {
            const downloaderName = row.querySelector('input[name="downloader_name"]')?.value || "this downloader";

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

            const description = row.querySelector(".settings-description");
            if (description) {
                description.textContent = `${formatDownloaderName(downloaderType)} → v${row.dataset.downloaderVersion} → Connected`;
            }
        }

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
    const downloaderName = row.querySelector('input[name="downloader_name"]')?.value.trim() || "";
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

        const description = row.querySelector(".settings-description");
        if (description) {
            description.textContent = `${formatDownloaderName(downloaderType)} → v${row.dataset.downloaderVersion} → Connected`;
        }

        if (saveButton) {
            saveButton.textContent = "Saved ✓";
            saveButton.disabled = true;
        }

        updateDownloaderEmptyState();
        return;
    }

    if (saveButton) {
        saveButton.textContent = "Save Downloader";
    }

    updateDownloaderSaveState(row);
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
