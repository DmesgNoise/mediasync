document.addEventListener("DOMContentLoaded", () => {
    initTimezoneSelectors();
    initSecretToggles();
    initSettingsForms();
    initSourceManagement();
    initDashboardManualScans();
    initLiveActivityStream();
});

const ACTIVE_MANUAL_SCANS = new Set();

const TIMEZONE_GROUPS = {
    "north-america": [
        ["America/New_York", "Eastern Time (America/New_York)"],
        ["America/Chicago", "Central Time (America/Chicago)"],
        ["America/Denver", "Mountain Time (America/Denver)"],
        ["America/Los_Angeles", "Pacific Time (America/Los_Angeles)"],
        ["America/Anchorage", "Alaska Time (America/Anchorage)"],
        ["America/Halifax", "Atlantic Time — AST (America/Halifax)"],
        ["America/St_Johns", "Newfoundland Time (America/St_Johns)"],
        ["Pacific/Honolulu", "Hawaii Time (Pacific/Honolulu)"],
        ["America/Phoenix", "Arizona / No DST (America/Phoenix)"],
    ],
    europe: [
        ["Europe/London", "London (Europe/London)"],
        ["Europe/Dublin", "Dublin (Europe/Dublin)"],
        ["Europe/Paris", "Paris (Europe/Paris)"],
        ["Europe/Berlin", "Berlin (Europe/Berlin)"],
        ["Europe/Rome", "Rome (Europe/Rome)"],
        ["Europe/Madrid", "Madrid (Europe/Madrid)"],
        ["Europe/Helsinki", "Helsinki (Europe/Helsinki)"],
    ],
    asia: [
        ["Asia/Tokyo", "Tokyo (Asia/Tokyo)"],
        ["Asia/Seoul", "Seoul (Asia/Seoul)"],
        ["Asia/Singapore", "Singapore (Asia/Singapore)"],
        ["Asia/Hong_Kong", "Hong Kong (Asia/Hong_Kong)"],
        ["Asia/Kolkata", "India (Asia/Kolkata)"],
        ["Asia/Dubai", "Dubai (Asia/Dubai)"],
    ],
    "australia-pacific": [
        ["Australia/Sydney", "Sydney (Australia/Sydney)"],
        ["Australia/Melbourne", "Melbourne (Australia/Melbourne)"],
        ["Australia/Perth", "Perth (Australia/Perth)"],
        ["Pacific/Auckland", "Auckland (Pacific/Auckland)"],
        ["Pacific/Apia", "Samoa (Pacific/Apia)"],
    ],
    "south-america": [
        ["America/Sao_Paulo", "São Paulo (America/Sao_Paulo)"],
        ["America/Argentina/Buenos_Aires", "Buenos Aires (America/Argentina/Buenos_Aires)"],
        ["America/Santiago", "Santiago (America/Santiago)"],
        ["America/Bogota", "Bogotá (America/Bogota)"],
    ],
    africa: [
        ["Africa/Cairo", "Cairo (Africa/Cairo)"],
        ["Africa/Johannesburg", "Johannesburg (Africa/Johannesburg)"],
        ["Africa/Lagos", "Lagos (Africa/Lagos)"],
        ["Africa/Nairobi", "Nairobi (Africa/Nairobi)"],
    ],
};

function initTimezoneSelectors() {
    const regionSelect = document.querySelector("[data-timezone-region]");
    const timezoneSelect = document.querySelector("[data-timezone-select]");
    const timezoneValue = document.querySelector("[data-timezone-value]");

    if (!regionSelect || !timezoneSelect || !timezoneValue) {
        return;
    }

    const currentTimezone = timezoneValue.value || "America/New_York";

    let matchedRegion = "north-america";

    Object.entries(TIMEZONE_GROUPS).forEach(([region, zones]) => {
        if (zones.some(([value]) => value === currentTimezone)) {
            matchedRegion = region;
        }
    });

    regionSelect.value = matchedRegion;

    const renderZones = () => {
        const selectedRegion = regionSelect.value;
        const zones = TIMEZONE_GROUPS[selectedRegion] || TIMEZONE_GROUPS["north-america"];

        timezoneSelect.innerHTML = "";

        zones.forEach(([value, label]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = label;

            if (value === timezoneValue.value) {
                option.selected = true;
            }

            timezoneSelect.appendChild(option);
        });

        if (!zones.some(([value]) => value === timezoneValue.value)) {
            timezoneValue.value = timezoneSelect.value;
        }
    };

    renderZones();

    regionSelect.addEventListener("change", () => {
        timezoneValue.value = "";
        renderZones();
        timezoneValue.value = timezoneSelect.value;
    });

    timezoneSelect.addEventListener("change", () => {
        timezoneValue.value = timezoneSelect.value;
    });
}

function initSecretToggles() {
    document.querySelectorAll("[data-toggle-secret]").forEach((button) => {
        button.addEventListener("click", () => {
            const row = button.closest(".settings-secret-row");
            const input = row ? row.querySelector("input") : null;

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
        });
    });
}

function initSettingsForms() {
    const mediaForm = document.querySelector("[data-settings-media-form]");

    if (mediaForm) {
        mediaForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            await postForm(mediaForm, "/api/settings/media-server/save");
        });

        const testButton = mediaForm.querySelector("[data-test-media-server]");

        if (testButton) {
            testButton.addEventListener("click", async () => {
                await postForm(mediaForm, "/api/settings/media-server/test");
            });
        }
    }

    const appSettingsForm = document.querySelector("[data-app-settings-form]");

    if (appSettingsForm) {
        appSettingsForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            await postForm(appSettingsForm, "/api/settings/app/save");
        });
    }

    const tvForm = document.querySelector("[data-tv-sync-form]");

    if (tvForm) {
        tvForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            await postForm(tvForm, "/api/settings/tv-sync/save");
        });
    }

    const activityForm = document.querySelector("[data-activity-settings-form]");

    if (activityForm) {
        activityForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            await postForm(activityForm, "/api/settings/activity/settings");
        });

        const clearButton = activityForm.querySelector("[data-clear-activity]");

        if (clearButton) {
            clearButton.addEventListener("click", () => {
                showConfirmModal({
                    title: "Clear Activity Log?",
                    body: "This will remove all activity history.",
                    actionText: "Clear Activity Log",
                    onConfirm: async () => {
                        await postEndpoint("/api/settings/activity/clear", activityForm);
                    },
                });
            });
        }
    }

    const testAllButton = document.querySelector("[data-test-all-sources]");

    if (testAllButton) {
        testAllButton.addEventListener("click", async () => {
            const card = testAllButton.closest(".settings-card");
            await postEndpoint("/api/settings/sources/test-all", card);
        });
    }

    const resetButton = document.querySelector("[data-reset-config]");

    if (resetButton) {
        resetButton.addEventListener("click", () => {
            showConfirmModal({
                title: "Reset MediaSync Configuration?",
                body: `
                    <p>This will remove:</p>
                    <ul>
                        <li>Media server configuration</li>
                        <li>Source mappings</li>
                        <li>Activity history</li>
                        <li>Dashboard state</li>
                        <li>Settings</li>
                    </ul>
                `,
                actionText: "Reset Configuration",
                onConfirm: async () => {
                    const card = resetButton.closest(".settings-card");
                    const result = await postEndpoint("/api/settings/reset", card);

                    if (result && result.success) {
                        window.location.href = "/setup";
                    }
                },
            });
        });
    }
}

function initSourceManagement() {
    const addSourceButton = document.querySelector("[data-add-settings-source]");

    if (addSourceButton) {
        addSourceButton.addEventListener("click", () => {
            addSettingsSourceRow();
        });
    }

    document.querySelectorAll("[data-source-row]").forEach((row) => {
        wireSettingsSourceRow(row);
    });

    initSourceDragDrop();
    updateSettingsSourceEmptyState();
}

function addSettingsSourceRow() {
    const list = document.querySelector("[data-settings-source-list]");

    if (!list) {
        return;
    }

    const row = createSettingsSourceRow();
    list.appendChild(row);
    wireSettingsSourceRow(row);
    initSourceDragDrop();
    updateSettingsSourceEmptyState();
}

function createSettingsSourceRow() {
    const row = document.createElement("div");
    row.className = "settings-source-item editable";
    row.draggable = true;
    row.dataset.sourceRow = "";
    row.dataset.sourceId = "";
    row.dataset.sourceVersion = "";
    row.dataset.connectionValid = "false";

    row.innerHTML = `
        <div class="source-order-controls">
            <div class="drag-handle">↕</div>
            <button class="mini-action-button source-order-button" type="button" data-source-move-up>Up</button>
            <button class="mini-action-button source-order-button" type="button" data-source-move-down>Down</button>
        </div>

        <img src="/static/img/radarr-logo.png" alt="Radarr" data-source-logo>

        <div class="settings-source-edit">
            <div class="form-grid">
                <label>
                    <span>Source Name</span>
                    <input name="source_name" type="text" value="Radarr">
                </label>

                <label>
                    <span>Source Type</span>
                    <select class="settings-select" name="source_type" data-source-type>
                        <option value="radarr" selected>Radarr</option>
                        <option value="sonarr">Sonarr</option>
                    </select>
                </label>

                <label>
                    <span>Server URL</span>
                    <input name="source_url" type="text" placeholder="http://radarr:7878">
                </label>

                <label>
                    <span>API Key</span>
                    <div class="settings-secret-row">
                        <input name="api_key" type="password" placeholder="Enter API key">
                        <button class="mini-action-button" type="button" data-toggle-secret>Show</button>
                    </div>
                </label>
            </div>

            <div class="settings-description">
                New source → test connection to discover compatible libraries.
            </div>

            <div class="source-library-results" data-settings-compatible-libraries>
                <div class="source-placeholder">
                    Compatible libraries will appear after a successful connection test.
                </div>
            </div>

            <div class="settings-source-actions">
                <button class="mini-action-button" type="button" data-source-test>Test Connection</button>
                <button class="mini-action-button good" type="button" data-source-save disabled>Save Source</button>
                <button class="mini-action-button danger" type="button" data-source-delete>Delete</button>
            </div>

            <div class="settings-result hidden" data-settings-result></div>
        </div>
    `;

    return row;
}

function wireSettingsSourceRow(row) {
    if (row.dataset.wired === "true") {
        return;
    }

    row.dataset.wired = "true";
    row.dataset.connectionValid = row.dataset.connectionValid || "false";
    row.dataset.sourceVersion = row.dataset.sourceVersion || "";

    const testButton = row.querySelector("[data-source-test]");
    const saveButton = row.querySelector("[data-source-save]");
    const deleteButton = row.querySelector("[data-source-delete]");
    const moveUpButton = row.querySelector("[data-source-move-up]");
    const moveDownButton = row.querySelector("[data-source-move-down]");
    const typeSelect = row.querySelector('select[name="source_type"]');
    const sourceNameInput = row.querySelector('input[name="source_name"]');
    const urlInput = row.querySelector('input[name="source_url"]');
    const apiKeyInput = row.querySelector('input[name="api_key"]');

    const secretButton = row.querySelector("[data-toggle-secret]");
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
            invalidateSettingsSourceConnection(row);
            syncSettingsSourceLogo(row);
            if (sourceNameInput && !sourceNameInput.value.trim()) {
                sourceNameInput.value = formatSourceName(typeSelect.value);
            }
        });
    }

    [urlInput, apiKeyInput].forEach((input) => {
        if (!input) {
            return;
        }

        input.addEventListener("input", () => {
            invalidateSettingsSourceConnection(row);
        });
    });

    if (sourceNameInput) {
        sourceNameInput.addEventListener("input", () => {
            markSettingsSourceUnsaved(row);
            updateSettingsSourceSaveState(row);
        });
    }

    row.addEventListener("change", (event) => {
        if (event.target.classList.contains("source-library-checkbox")) {
            markSettingsSourceUnsaved(row);
            updateSettingsSourceSaveState(row);
        }
    });

    if (testButton) {
        testButton.addEventListener("click", async () => {
            await testSettingsSource(row);
        });
    }

    if (saveButton) {
        saveButton.addEventListener("click", async () => {
            await saveSettingsSource(row);
        });
    }

    if (moveUpButton) {
        moveUpButton.addEventListener("click", async () => {
            const previous = row.previousElementSibling;

            if (previous && previous.matches("[data-source-row]")) {
                row.parentNode.insertBefore(row, previous);
                await saveSourceOrder();
            }
        });
    }

    if (moveDownButton) {
        moveDownButton.addEventListener("click", async () => {
            const next = row.nextElementSibling;

            if (next && next.matches("[data-source-row]")) {
                row.parentNode.insertBefore(next, row);
                await saveSourceOrder();
            }
        });
    }

    if (deleteButton) {
        deleteButton.addEventListener("click", () => {
            const sourceName = row.querySelector('input[name="source_name"]')?.value || "this source";

            showConfirmModal({
                title: `Delete ${sourceName}?`,
                body: `
                    <p>This will remove:</p>
                    <ul>
                        <li>Source connection</li>
                        <li>Library mapping</li>
                    </ul>
                `,
                actionText: "Delete Source",
                onConfirm: async () => {
                    if (row.dataset.sourceId) {
                        const formData = new FormData();
                        formData.append("source_id", row.dataset.sourceId);

                        const result = await fetchJson("/api/settings/source/delete", formData);

                        if (!result.success) {
                            showResult(row, result);
                            return;
                        }
                    }

                    row.remove();
                    await saveSourceOrder();
                    updateSettingsSourceEmptyState();
                },
            });
        });
    }

    syncSettingsSourceLogo(row);
    updateSettingsSourceSaveState(row);
}

function invalidateSettingsSourceConnection(row) {
    row.dataset.connectionValid = "false";
    row.dataset.sourceVersion = "";

    const libraryContainer = row.querySelector("[data-settings-compatible-libraries]");
    const resultBox = row.querySelector("[data-settings-result]");

    if (libraryContainer) {
        libraryContainer.className = "source-library-results";
        libraryContainer.innerHTML = `
            <div class="source-placeholder">
                Compatible libraries will appear after a successful connection test.
            </div>
        `;
    }

    if (resultBox) {
        resultBox.className = "settings-result hidden";
        resultBox.textContent = "";
    }

    markSettingsSourceUnsaved(row);
    updateSettingsSourceSaveState(row);
}

function markSettingsSourceUnsaved(row) {
    const saveButton = row.querySelector("[data-source-save]");

    if (saveButton) {
        saveButton.textContent = "Save Source";
    }
}

function syncSettingsSourceLogo(row) {
    const typeSelect = row.querySelector('select[name="source_type"]');
    const logo = row.querySelector("[data-source-logo]");

    if (!typeSelect || !logo) {
        return;
    }

    logo.src = `/static/img/${typeSelect.value}-logo.png`;
    logo.alt = formatSourceName(typeSelect.value);
}

async function testSettingsSource(row) {
    const testButton = row.querySelector("[data-source-test]");
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "radarr";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";
    const libraryContainer = row.querySelector("[data-settings-compatible-libraries]");

    row.dataset.connectionValid = "false";
    row.dataset.sourceVersion = "";

    updateSettingsSourceSaveState(row);

    if (!sourceUrl || !apiKey) {
        showResult(row, {
            success: false,
            message: "Enter a server URL and API key first.",
        });
        return;
    }

    const selectedLibraryIds = getSelectedLibraryIds(row);

    showResult(row, {
        success: true,
        message: "Testing connection...",
    });

    if (testButton) {
        testButton.disabled = true;
        testButton.textContent = "Testing...";
    }

    try {
        const formData = new FormData();
        formData.append("source_type", sourceType);
        formData.append("source_url", sourceUrl);
        formData.append("api_key", apiKey);

        const result = await fetchJson("/api/source/test", formData);

        if (result.success) {
            row.dataset.connectionValid = "true";
            row.dataset.sourceVersion = result.version || "Unknown";

            if (libraryContainer) {
                renderCompatibleLibraries(
                    libraryContainer,
                    result.compatible_libraries || [],
                    selectedLibraryIds,
                );
            }

            showResult(row, {
                success: true,
                message: `${result.message} Connected to ${result.app_name} ${result.version}.`,
            });
        } else {
            showResult(row, result);
        }
    } finally {
        if (testButton) {
            testButton.disabled = false;
            testButton.textContent = "Test Connection";
        }

        updateSettingsSourceSaveState(row);
    }
}

async function saveSettingsSource(row) {
    if (row.dataset.connectionValid !== "true") {
        showResult(row, {
            success: false,
            message: "Test the source connection before saving.",
        });
        return;
    }

    const saveButton = row.querySelector("[data-source-save]");
    const sourceName = row.querySelector('input[name="source_name"]')?.value.trim() || "";
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "radarr";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";
    const libraries = getCheckedLibraries(row);

    if (!libraries.length) {
        showResult(row, {
            success: false,
            message: "Select at least one library before saving.",
        });
        return;
    }

    if (saveButton) {
        saveButton.disabled = true;
        saveButton.textContent = "Saving...";
    }

    const formData = new FormData();
    formData.append("source_id", row.dataset.sourceId || "");
    formData.append("source_name", sourceName || formatSourceName(sourceType));
    formData.append("source_type", sourceType);
    formData.append("source_url", sourceUrl);
    formData.append("api_key", apiKey);
    formData.append("version", row.dataset.sourceVersion || "Unknown");
    formData.append("libraries_json", JSON.stringify(libraries));

    const result = await fetchJson("/api/source/save", formData);

    showResult(row, result);

    if (result.success) {
        row.dataset.sourceId = result.source_id;
        row.dataset.connectionValid = "true";

        const description = row.querySelector(".settings-description");
        if (description) {
            description.textContent = `${formatSourceName(sourceType)} → ${libraries.length} mapped ${libraries.length === 1 ? "library" : "libraries"}`;
        }

        if (saveButton) {
            saveButton.textContent = "Saved ✓";
            saveButton.disabled = true;
        }

        await saveSourceOrder();
        updateSettingsSourceEmptyState();
        return;
    }

    if (saveButton) {
        saveButton.textContent = "Save Source";
    }

    updateSettingsSourceSaveState(row);
}

function getSelectedLibraryIds(row) {
    return Array.from(
        row.querySelectorAll(".source-library-checkbox:checked"),
    ).map((checkbox) => checkbox.value);
}

function getCheckedLibraries(row) {
    return Array.from(row.querySelectorAll(".source-library-checkbox:checked")).map((checkbox) => {
        const option = checkbox.closest(".source-library-option");
        const nameEl = option ? option.querySelector(".library-name") : null;

        return {
            id: checkbox.value,
            name: checkbox.dataset.libraryName || (nameEl ? nameEl.textContent.trim() : checkbox.value),
            type: checkbox.dataset.libraryType || "unknown",
            image_url: checkbox.dataset.libraryImageUrl || "",
        };
    });
}

function renderCompatibleLibraries(container, libraries, selectedLibraryIds = []) {
    if (!libraries.length) {
        container.className = "source-library-results source-placeholder warning";
        container.textContent = "No compatible libraries were found.";
        return;
    }

    const cards = libraries
        .map((library) => {
            const checked = selectedLibraryIds.includes(String(library.id)) ? "checked" : "";
            return `
                <label class="source-library-option">
                    <input
                        type="checkbox"
                        class="source-library-checkbox"
                        value="${escapeHtml(library.id)}"
                        data-library-name="${escapeHtml(library.name)}"
                        data-library-type="${escapeHtml(library.type || "unknown")}"
                        data-library-image-url="${escapeHtml(library.image_url || "")}"
                        ${checked}
                    >

                    ${libraryImageMarkup(library)}

                    <div>
                        <div class="library-name">
                            ${escapeHtml(library.name)}
                        </div>

                        <div class="library-type">
                            ${escapeHtml(formatLibraryType(library.type))}
                        </div>
                    </div>
                </label>
            `;
        })
        .join("");

    container.className = "source-library-results";
    container.innerHTML = `
        <div class="library-results-header">
            <div>
                <h3>Compatible Libraries</h3>
                <p>Select one or more libraries for this source.</p>
            </div>
        </div>

        <div class="library-grid">
            ${cards}
        </div>
    `;
}

function updateSettingsSourceSaveState(row) {
    const saveButton = row.querySelector("[data-source-save]");

    if (!saveButton) {
        return;
    }

    const checkedLibraries = row.querySelectorAll(".source-library-checkbox:checked");

    saveButton.disabled =
        row.dataset.connectionValid !== "true" ||
        checkedLibraries.length === 0;
}

function updateSettingsSourceEmptyState() {
    const rows = document.querySelectorAll("[data-source-row]");
    const emptyBox = document.querySelector("[data-settings-source-empty]");

    if (!emptyBox) {
        return;
    }

    if (rows.length) {
        emptyBox.classList.add("hidden");
    } else {
        emptyBox.classList.remove("hidden");
    }
}

function initSourceDragDrop() {
    const list = document.querySelector("[data-sortable-sources]");

    if (!list) {
        return;
    }

    let dragged = null;

    list.querySelectorAll("[data-source-row]").forEach((row) => {
        if (row.dataset.dragWired === "true") {
            return;
        }

        row.dataset.dragWired = "true";

        row.addEventListener("dragstart", () => {
            dragged = row;
            row.classList.add("dragging");
        });

        row.addEventListener("dragend", async () => {
            row.classList.remove("dragging");
            dragged = null;
            await saveSourceOrder();
        });

        row.addEventListener("dragover", (event) => {
            event.preventDefault();

            const target = event.currentTarget;

            if (!dragged || dragged === target) {
                return;
            }

            const box = target.getBoundingClientRect();
            const before = event.clientY < box.top + box.height / 2;

            if (before) {
                list.insertBefore(dragged, target);
            } else {
                list.insertBefore(dragged, target.nextSibling);
            }
        });
    });
}

async function saveSourceOrder() {
    const rows = Array.from(document.querySelectorAll("[data-source-row]"))
        .filter((row) => row.dataset.sourceId);
    const ids = rows.map((row) => row.dataset.sourceId).join(",");

    const formData = new FormData();
    formData.append("source_ids", ids);

    await fetchJson("/api/settings/sources/reorder", formData);
}

async function postForm(form, url) {
    const result = await fetchJson(url, new FormData(form));
    showResult(form, result);
    return result;
}

async function postEndpoint(url, container) {
    const result = await fetchJson(url, new FormData());
    showResult(container, result);
    return result;
}

async function fetchJson(url, formData) {
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

function showResult(container, result) {
    const resultBox = container.querySelector("[data-settings-result]");

    if (!resultBox) {
        return;
    }

    resultBox.className = `settings-result ${result.success ? "good" : "warning"}`;
    resultBox.textContent = result.message || (result.success ? "Success." : "Failed.");
}

function showConfirmModal({ title, body, actionText, onConfirm }) {
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

function initDashboardManualScans() {
    document.querySelectorAll("[data-manual-scan]").forEach((button) => {
        button.addEventListener("click", async () => {
            const scanKey = getManualScanKey(button);

            if (ACTIVE_MANUAL_SCANS.has(scanKey)) {
                return;
            }

            ACTIVE_MANUAL_SCANS.add(scanKey);
            setActiveSyncCount(ACTIVE_MANUAL_SCANS.size);
            setManualScanButtonState(button, "requested");

            const formData = new FormData();
            formData.append("source_id", button.dataset.sourceId);
            formData.append("library_id", button.dataset.libraryId);
            formData.append("library_name", button.dataset.libraryName);

            const result = await fetchJson("/api/settings/manual-scan", formData);

            window.setTimeout(() => {
                finishManualScanRequest(button, scanKey);
            }, 3000);

            if (!result.success) {
                addDashboardActivityBubble(
                    "error",
                    "Manual scan failed",
                    button.dataset.libraryName,
                    result.message || "Request failed."
                );
            }
        });
    });
}

function finishManualScanRequest(button, scanKey) {
    ACTIVE_MANUAL_SCANS.delete(scanKey);
    setActiveSyncCount(ACTIVE_MANUAL_SCANS.size);
    setManualScanButtonState(button, "idle");
}

function setManualScanButtonState(button, state) {
    if (!button) {
        return;
    }

    if (state === "requested") {
        button.disabled = false;
        button.setAttribute("aria-disabled", "true");
        button.dataset.scanState = "requested";
        button.textContent = "Requested";
        return;
    }

    button.disabled = false;
    button.removeAttribute("aria-disabled");
    button.dataset.scanState = "idle";
    button.textContent = "Scan";
}

function getManualScanKey(button) {
    return `${button.dataset.sourceId || ""}:${button.dataset.libraryId || ""}`;
}

function initLiveActivityStream() {
    const dashboardFeed = document.querySelector("[data-dashboard-activity-feed]");
    const activityFeed = document.querySelector("[data-activity-page-feed]");

    if (!dashboardFeed && !activityFeed) {
        return;
    }

    if (!window.EventSource) {
        return;
    }

    const stream = new EventSource("/api/activity/stream");
    let activityStreamReloaded = false;

    const reloadActivityViewOnce = () => {
        if (activityStreamReloaded) {
            return;
        }

        activityStreamReloaded = true;
        window.location.reload();
    };

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && stream.readyState === EventSource.CLOSED) {
            reloadActivityViewOnce();
        }
    });

    stream.onerror = () => {
        window.setTimeout(() => {
            if (stream.readyState === EventSource.CLOSED) {
                reloadActivityViewOnce();
            }
        }, 1500);
    };

    stream.onmessage = (message) => {
        if (!message.data) {
            return;
        }

        let event;

        try {
            event = JSON.parse(message.data);
        } catch (error) {
            return;
        }

        if (dashboardFeed) {
            removeIdleActivityPlaceholder(dashboardFeed);
            dashboardFeed.prepend(renderDashboardActivityEvent(event, dashboardFeed.dataset.dashboardFileDetail || "filename"));
            trimActivityFeed(dashboardFeed, 25);
        }

        if (activityFeed) {
            removeIdleActivityPlaceholder(activityFeed);
            activityFeed.prepend(renderActivityPageEvent(event, activityFeed.dataset.activityFileDetail || "filename"));
            trimActivityFeed(activityFeed, 250);
        }
    };
}

function renderDashboardActivityEvent(event, fileDetailLevel = "filename") {
    const item = document.createElement("div");
    item.className = `activity-event ${escapeHtml(event.status || "info")}`;

    const route = activityRouteText(event);
    const mediaTitle = event.media_title ? `<div class="dashboard-activity-extra">${escapeHtml(event.media_title)}</div>` : "";

    let fileValue = "";

    if (fileDetailLevel === "path" && event.file_path) {
        fileValue = event.file_path;
    } else if (event.file_name) {
        fileValue = event.file_name;
    } else if (event.file_path) {
        fileValue = event.file_path;
    }

    const fileHtml = fileValue ? `<div class="dashboard-activity-file">${escapeHtml(fileValue)}</div>` : "";
    const detailsHtml = event.details ? `<div class="dashboard-activity-details">${escapeHtml(event.details)}</div>` : "";

    item.innerHTML = `
        <div class="activity-event-dot"></div>
        <div class="activity-event-body">
            <div class="activity-event-top">
                <div class="activity-event-title">${escapeHtml(event.event_type || "Activity")}</div>
                <div class="activity-event-time">${escapeHtml(event.created_at || "Now")}</div>
            </div>
            <div class="activity-event-meta">${escapeHtml(route)}</div>
            ${mediaTitle}
            ${fileHtml}
            ${detailsHtml}
        </div>
    `;

    return item;
}

function renderActivityPageEvent(event, fileDetailLevel) {
    const item = document.createElement("article");
    item.className = `activity-page-event ${escapeHtml(event.status || "info")}`;

    const route = activityRouteText(event);
    const mediaTitle = event.media_title ? `<div class="activity-page-media">${escapeHtml(event.media_title)}</div>` : "";

    let fileValue = "";

    if (fileDetailLevel === "path" && event.file_path) {
        fileValue = event.file_path;
    } else if (event.file_name) {
        fileValue = event.file_name;
    } else if (event.file_path) {
        fileValue = event.file_path;
    }

    const fileHtml = fileValue ? `<div class="activity-page-file">${escapeHtml(fileValue)}</div>` : "";
    const detailsHtml = event.details ? `<div class="activity-page-details">${escapeHtml(event.details)}</div>` : "";

    item.innerHTML = `
        <div class="activity-event-dot"></div>
        <div class="activity-page-event-body">
            <div class="activity-page-event-top">
                <div>
                    <div class="activity-page-title">${escapeHtml(event.event_type || "Activity")}</div>
                    <div class="activity-page-route">${escapeHtml(route)}</div>
                </div>
                <div class="activity-page-time">${escapeHtml(event.created_at || "Now")}</div>
            </div>
            ${mediaTitle}
            ${fileHtml}
            ${detailsHtml}
        </div>
    `;

    return item;
}

function activityRouteText(event) {
    let route = event.source_name || "MediaSync";

    if (event.library_name) {
        route += ` -> ${event.library_name}`;
    }

    return route;
}

function removeIdleActivityPlaceholder(feed) {
    feed.querySelectorAll(".activity-event.idle, .activity-page-empty").forEach((item) => {
        item.remove();
    });
}

function trimActivityFeed(feed, limit) {
    const children = Array.from(feed.children);

    children.slice(limit).forEach((child) => {
        child.remove();
    });
}

function setActiveSyncCount(count) {
    const el = document.querySelector("[data-active-sync-count]");

    if (!el) {
        return;
    }

    el.textContent = `${count} Active Sync${count === 1 ? "" : "s"}`;
}

function addDashboardActivityBubble(status, title, libraryName, details) {
    const feed = document.querySelector("[data-dashboard-activity-feed]");

    if (!feed) {
        return;
    }

    const event = document.createElement("div");
    event.className = `activity-event ${status}`;
    event.innerHTML = `
        <div class="activity-event-dot"></div>
        <div class="activity-event-body">
            <div class="activity-event-top">
                <div class="activity-event-title">${escapeHtml(title)}</div>
                <div class="activity-event-time">Now</div>
            </div>
            <div class="activity-event-meta">${escapeHtml(libraryName || "MediaSync")} • ${escapeHtml(details || "")}</div>
        </div>
    `;

    feed.prepend(event);
}

function setLibrarySyncProgress(tile, percent, stateLabel = "Syncing") {
    const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));

    const orb = tile.querySelector("[data-library-orb]");
    const ring = tile.querySelector(".library-progress-value");
    const percentLabel = tile.querySelector("[data-library-percent]");
    const stateLabelElement = tile.querySelector("[data-library-state]");

    if (!orb || !ring || !percentLabel || !stateLabelElement) {
        return;
    }

    const radius = 52;
    const circumference = 2 * Math.PI * radius;
    const dashOffset = circumference - ((safePercent / 100) * circumference);

    ring.style.strokeDasharray = circumference;
    ring.style.strokeDashoffset = dashOffset;

    if (safePercent >= 100) {
        orb.classList.remove("syncing");
        orb.classList.add("complete");

        percentLabel.classList.add("hidden");
        percentLabel.textContent = "";

        stateLabelElement.textContent = "Complete";

        window.setTimeout(() => {
            orb.classList.remove("complete");
            stateLabelElement.textContent = "Idle";
        }, 1600);

        return;
    }

    if (safePercent <= 0) {
        orb.classList.remove("syncing", "complete");
        percentLabel.classList.add("hidden");
        percentLabel.textContent = "";
        stateLabelElement.textContent = "Idle";
        return;
    }

    orb.classList.add("syncing");
    orb.classList.remove("complete");

    percentLabel.classList.remove("hidden");
    percentLabel.textContent = `${Math.round(safePercent)}%`;

    stateLabelElement.textContent = stateLabel;
}

function libraryImageMarkup(library) {
    const icon = getLibraryIcon(library.type);

    if (library.image_url) {
        return `
            <img
                class="library-image"
                src="${escapeHtml(library.image_url)}"
                alt="${escapeHtml(library.name)}"
                onerror="this.remove(); this.nextElementSibling.style.display='grid';"
            >

            <div class="library-icon library-icon-fallback" style="display: none;">
                ${icon}
            </div>
        `;
    }

    return `
        <div class="library-icon">
            ${icon}
        </div>
    `;
}

function getLibraryIcon(type) {
    if (type === "movies") {
        return "🎬";
    }

    if (type === "tvshows") {
        return "📺";
    }

    if (type === "music") {
        return "🎵";
    }

    if (type === "homevideos") {
        return "🎥";
    }

    return "▣";
}

function formatLibraryType(type) {
    if (!type || type === "unknown") {
        return "Library";
    }

    const labels = {
        movies: "Movies",
        tvshows: "TV Shows",
        music: "Music",
        homevideos: "Home Videos",
        musicvideos: "Music Videos",
        boxsets: "Collections",
    };

    return labels[type] || type;
}

function formatSourceName(sourceType) {
    const labels = {
        radarr: "Radarr",
        sonarr: "Sonarr",
    };

    return labels[sourceType] || sourceType;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
