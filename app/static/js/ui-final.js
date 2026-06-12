document.addEventListener("DOMContentLoaded", () => {
    initTimezoneSelectors();
    initSecretToggles();
    initSettingsForms();
    initSourceManagement();
    initDashboardManualScans();
    initLiveActivityStream();
    initDownloaderCardPolling();
    initLifecyclePopup();
    initDashboardLibraryCounts();
    wireTvSeasonOpenTracking();
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
                    const container =
                        resetButton.closest(".settings-reset-strip") ||
                        resetButton.closest(".settings-card") ||
                        document.body;
                    const result = await postEndpoint("/api/settings/reset", container);

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
    row.className = "settings-source-item settings-source-compact is-editing is-new";
    row.draggable = true;
    row.dataset.sourceRow = "";
    row.dataset.sourceId = "";
    row.dataset.sourceVersion = "";
    row.dataset.connectionValid = "false";
    row.dataset.editing = "true";

    row.innerHTML = `
        <div class="source-order-controls">
            <div class="drag-handle" title="Drag to reorder">↕</div>
            <button class="mini-action-button source-order-button" type="button" data-source-move-up>Up</button>
            <button class="mini-action-button source-order-button" type="button" data-source-move-down>Down</button>
        </div>

        <img class="settings-source-logo" src="/static/img/default.png" alt="Source" data-source-logo>

        <div class="settings-source-main">
            <div class="settings-source-static hidden" data-source-static>
                <div class="settings-source-static-top">
                    <div>
                        <div class="settings-source-name-static" data-source-static-name>New Source</div>
                        <div class="settings-source-meta" data-source-static-meta>No mapped libraries</div>
                    </div>
                </div>
                <div class="settings-source-library-strip" data-source-static-libraries>
                    <div class="settings-source-no-libraries">No mapped libraries</div>
                </div>
            </div>

            <div class="settings-source-edit" data-source-edit>
                <div class="settings-source-edit-title">Edit Source</div>

                <div class="form-grid settings-source-form-grid">
                    <label>
                        <span>Source Name</span>
                        <input name="source_name" type="text" placeholder="Enter source name">
                    </label>

                    <label>
                        <span>Source Type</span>
                        <select class="settings-select" name="source_type" data-source-type>
                            <option value="" selected disabled>Select source type</option>
                            <option value="radarr">Radarr</option>
                            <option value="sonarr">Sonarr</option>
                        </select>
                    </label>

                    <label>
                        <span>Server URL</span>
                        <input name="source_url" type="text" placeholder="Enter server URL">
                    </label>

                    <label>
                        <span>API Key</span>
                        <div class="settings-secret-row">
                            <input name="api_key" type="password" placeholder="Enter API key">
                            <button class="mini-action-button" type="button" data-toggle-secret>Show</button>
                        </div>
                    </label>
                </div>

                <div class="settings-description" data-source-edit-description>
                    Select a source type, test the connection, refresh libraries, then save.
                </div>

                <div class="source-library-results" data-settings-compatible-libraries>
                    <div class="source-placeholder">
                        Use Refresh Libraries to load compatible media-server libraries.
                    </div>
                </div>
            </div>

            <div class="settings-source-actions settings-source-actions-compact">
                <button class="mini-action-button" type="button" data-source-test>Test Connection</button>
                <button class="mini-action-button" type="button" data-source-refresh-libraries>Refresh Libraries</button>
                <button class="mini-action-button hidden" type="button" data-source-edit-button>Edit</button>
                <button class="mini-action-button good" type="button" data-source-save disabled>Save Source</button>
                <button class="mini-action-button secondary-action" type="button" data-source-cancel-edit>Cancel</button>
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
    row.dataset.editing = row.dataset.editing || (row.dataset.sourceId ? "false" : "true");

    const testButton = row.querySelector("[data-source-test]");
    const refreshButton = row.querySelector("[data-source-refresh-libraries]");
    const editButton = row.querySelector("[data-source-edit-button]");
    const saveButton = row.querySelector("[data-source-save]");
    const cancelButton = row.querySelector("[data-source-cancel-edit]");
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
            invalidateSettingsSourceConnection(row, { clearLibraries: true });
            syncSettingsSourceLogo(row);
        });
    }

    [urlInput, apiKeyInput].forEach((input) => {
        if (!input) {
            return;
        }

        input.addEventListener("input", () => {
            invalidateSettingsSourceConnection(row, { clearLibraries: false });
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

    if (refreshButton) {
        refreshButton.addEventListener("click", async () => {
            await refreshSettingsSourceLibraries(row);
        });
    }

    if (editButton) {
        editButton.addEventListener("click", () => {
            setSettingsSourceEditing(row, true);
        });
    }

    if (cancelButton) {
        cancelButton.addEventListener("click", () => {
            if (row.dataset.sourceId) {
                restoreSettingsSourceEditSnapshot(row);
                setSettingsSourceEditing(row, false);
                return;
            }

            row.remove();
            updateSettingsSourceEmptyState();
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
            const sourceName = getSettingsSourceName(row) || "this source";

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
    setSettingsSourceEditing(row, row.dataset.editing === "true", { initialize: true });
    updateSettingsSourceSaveState(row);
}

function invalidateSettingsSourceConnection(row, options = {}) {
    const clearLibraries = options.clearLibraries !== false;

    row.dataset.connectionValid = "false";
    row.dataset.sourceVersion = "";

    const libraryContainer = row.querySelector("[data-settings-compatible-libraries]");
    const resultBox = row.querySelector("[data-settings-result]");

    if (clearLibraries && libraryContainer) {
        libraryContainer.className = "source-library-results";
        libraryContainer.innerHTML = `
            <div class="source-placeholder">
                Use Refresh Libraries to load compatible media-server libraries.
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
    const sourceType = typeSelect ? typeSelect.value : "";

    if (!logo) {
        return;
    }

    if (!sourceType) {
        logo.src = "/static/img/default.png";
        logo.alt = "Source";
        return;
    }

    logo.src = `/static/img/${sourceType}-logo.png`;
    logo.alt = formatSourceName(sourceType);
}

async function testSettingsSource(row) {
    const testButton = row.querySelector("[data-source-test]");
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";

    row.dataset.connectionValid = "false";
    row.dataset.sourceVersion = "";
    updateSettingsSourceSaveState(row);

    if (!sourceType) {
        showResult(row, {
            success: false,
            message: "Select a source type first.",
        });
        return;
    }

    if (!sourceUrl || !apiKey) {
        showResult(row, {
            success: false,
            message: "Enter a server URL and API key first.",
        });
        return;
    }

    showResult(row, {
        success: true,
        message: "Testing connection...",
    });

    if (testButton) {
        testButton.disabled = true;
        testButton.textContent = "Testing...";
    }

    try {
        const result = await fetchSettingsSourceTest(row);

        if (result.success) {
            row.dataset.connectionValid = "true";
            row.dataset.sourceVersion = result.version || "Unknown";
            updateSettingsSourceStatic(row);

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

async function refreshSettingsSourceLibraries(row) {
    const refreshButton = row.querySelector("[data-source-refresh-libraries]");
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";
    const libraryContainer = row.querySelector("[data-settings-compatible-libraries]");

    if (!sourceType) {
        showResult(row, {
            success: false,
            message: "Select a source type first.",
        });
        setSettingsSourceEditing(row, true);
        return;
    }

    if (!sourceUrl || !apiKey) {
        showResult(row, {
            success: false,
            message: "Enter a server URL and API key first.",
        });
        setSettingsSourceEditing(row, true);
        return;
    }

    const selectedLibraryIds = getSelectedLibraryIds(row);
    setSettingsSourceEditing(row, true);

    showResult(row, {
        success: true,
        message: "Refreshing libraries...",
    });

    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.textContent = "Refreshing...";
    }

    try {
        const result = await fetchSettingsSourceTest(row);

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
                message: `${(result.compatible_libraries || []).length} compatible libraries found. Review selections and save this source.`,
            });
        } else {
            showResult(row, result);
        }
    } finally {
        if (refreshButton) {
            refreshButton.disabled = false;
            refreshButton.textContent = "Refresh Libraries";
        }

        updateSettingsSourceSaveState(row);
    }
}

async function fetchSettingsSourceTest(row) {
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";

    const formData = new FormData();
    formData.append("source_type", sourceType);
    formData.append("source_url", sourceUrl);
    formData.append("api_key", apiKey);

    return await fetchJson("/api/source/test", formData);
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
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";
    const libraries = getCheckedLibraries(row);

    if (!sourceName) {
        showResult(row, {
            success: false,
            message: "Enter a source name before saving.",
        });
        return;
    }

    if (!sourceType) {
        showResult(row, {
            success: false,
            message: "Select a source type before saving.",
        });
        return;
    }

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
    formData.append("source_name", sourceName);
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
        row.classList.remove("is-new");

        if (saveButton) {
            saveButton.textContent = "Saved ✓";
            saveButton.disabled = true;
        }

        updateSettingsSourceStatic(row);
        setSettingsSourceEditing(row, false);
        await saveSourceOrder();
        updateSettingsSourceEmptyState();
        return;
    }

    if (saveButton) {
        saveButton.textContent = "Save Source";
    }

    updateSettingsSourceSaveState(row);
}

function setSettingsSourceEditing(row, editing, options = {}) {
    if (editing && !options.initialize) {
        storeSettingsSourceEditSnapshot(row);
    }

    const staticPanel = row.querySelector("[data-source-static]");
    const editPanel = row.querySelector("[data-source-edit]");
    const editButton = row.querySelector("[data-source-edit-button]");
    const saveButton = row.querySelector("[data-source-save]");
    const cancelButton = row.querySelector("[data-source-cancel-edit]");

    row.dataset.editing = editing ? "true" : "false";
    row.classList.toggle("is-editing", editing);
    row.classList.toggle("is-saved", !editing && !!row.dataset.sourceId);

    if (staticPanel) {
        staticPanel.classList.toggle("hidden", editing);
    }

    if (editPanel) {
        editPanel.classList.toggle("hidden", !editing);
    }

    if (editButton) {
        editButton.classList.toggle("hidden", editing || !row.dataset.sourceId);
    }

    if (saveButton) {
        saveButton.classList.toggle("hidden", !editing);
    }

    if (cancelButton) {
        cancelButton.classList.toggle("hidden", !editing);
    }

    if (!options.initialize) {
        updateSettingsSourceSaveState(row);
    }
}


function storeSettingsSourceEditSnapshot(row) {
    const snapshot = {
        sourceName: row.querySelector('input[name="source_name"]')?.value || "",
        sourceType: row.querySelector('select[name="source_type"]')?.value || "",
        sourceUrl: row.querySelector('input[name="source_url"]')?.value || "",
        apiKey: row.querySelector('input[name="api_key"]')?.value || "",
        checkedLibraryIds: getSelectedLibraryIds(row),
        connectionValid: row.dataset.connectionValid || "false",
        sourceVersion: row.dataset.sourceVersion || "",
    };

    row.dataset.sourceSnapshot = JSON.stringify(snapshot);
}

function restoreSettingsSourceEditSnapshot(row) {
    if (!row.dataset.sourceSnapshot) {
        return;
    }

    let snapshot = {};

    try {
        snapshot = JSON.parse(row.dataset.sourceSnapshot);
    } catch (error) {
        return;
    }

    const sourceNameInput = row.querySelector('input[name="source_name"]');
    const typeSelect = row.querySelector('select[name="source_type"]');
    const urlInput = row.querySelector('input[name="source_url"]');
    const apiKeyInput = row.querySelector('input[name="api_key"]');

    if (sourceNameInput) {
        sourceNameInput.value = snapshot.sourceName || "";
    }

    if (typeSelect) {
        typeSelect.value = snapshot.sourceType || "";
    }

    if (urlInput) {
        urlInput.value = snapshot.sourceUrl || "";
    }

    if (apiKeyInput) {
        apiKeyInput.value = snapshot.apiKey || "";
    }

    row.dataset.connectionValid = snapshot.connectionValid || "false";
    row.dataset.sourceVersion = snapshot.sourceVersion || "";

    row.querySelectorAll(".source-library-checkbox").forEach((checkbox) => {
        checkbox.checked = (snapshot.checkedLibraryIds || []).includes(checkbox.value);
    });

    syncSettingsSourceLogo(row);
    updateSettingsSourceSaveState(row);
}

function updateSettingsSourceStatic(row) {
    const name = getSettingsSourceName(row) || "Unnamed Source";
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "";
    const version = row.dataset.sourceVersion || "Unknown";
    const libraries = getCheckedLibraries(row);
    const staticName = row.querySelector("[data-source-static-name]");
    const staticMeta = row.querySelector("[data-source-static-meta]");
    const staticLibraries = row.querySelector("[data-source-static-libraries]");

    if (staticName) {
        staticName.textContent = name;
    }

    if (staticMeta) {
        staticMeta.innerHTML = `v${escapeHtml(version)} <span>•</span> ${libraries.length} mapped ${libraries.length === 1 ? "library" : "libraries"}`;
    }

    if (staticLibraries) {
        renderStaticSourceLibraries(staticLibraries, libraries);
    }

    syncSettingsSourceLogo(row);
}

function renderStaticSourceLibraries(container, libraries) {
    if (!libraries.length) {
        container.innerHTML = `<div class="settings-source-no-libraries">No mapped libraries</div>`;
        return;
    }

    container.innerHTML = libraries.map((library) => `
        <div class="settings-source-library-chip">
            ${libraryImageMarkup({
                id: library.id,
                name: library.name,
                type: library.type,
                image_url: library.image_url,
            })}
            <span>${escapeHtml(library.name)}</span>
        </div>
    `).join("");
}

function getSettingsSourceName(row) {
    return row.querySelector('input[name="source_name"]')?.value.trim() ||
        row.querySelector("[data-source-static-name]")?.textContent.trim() ||
        "";
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
                <p>Select one or more libraries for this source, then save the source.</p>
            </div>
        </div>

        <div class="library-grid settings-library-grid-compact">
            ${cards}
        </div>
    `;
}

function updateSettingsSourceSaveState(row) {
    const saveButton = row.querySelector("[data-source-save]");

    if (!saveButton) {
        return;
    }

    const sourceName = row.querySelector('input[name="source_name"]')?.value.trim() || "";
    const sourceType = row.querySelector('select[name="source_type"]')?.value || "";
    const sourceUrl = row.querySelector('input[name="source_url"]')?.value.trim() || "";
    const apiKey = row.querySelector('input[name="api_key"]')?.value.trim() || "";
    const checkedLibraries = row.querySelectorAll(".source-library-checkbox:checked");

    saveButton.disabled =
        row.dataset.connectionValid !== "true" ||
        !sourceName ||
        !sourceType ||
        !sourceUrl ||
        !apiKey ||
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

    let stream = null;
    let reconnectTimer = null;

    const handleActivityMessage = (message) => {
        if (!message.data) {
            return;
        }

        let event;

        try {
            event = JSON.parse(message.data);
        } catch (error) {
            return;
        }

        if (!event.lifecycle_id) {
            return;
        }

        if (dashboardFeed) {
            removeIdleActivityPlaceholder(dashboardFeed);
            upsertActivityFeedItem(
                dashboardFeed,
                renderDashboardActivityEvent(event, dashboardFeed.dataset.dashboardFileDetail || "filename"),
                25,
            );
        }

        if (activityFeed) {
            removeIdleActivityPlaceholder(activityFeed);
            upsertActivityFeedItem(
                activityFeed,
                renderActivityPageEvent(event, activityFeed.dataset.activityFileDetail || "filename"),
                250,
            );
        }

        if (LIFECYCLE_CURRENT_DATA && String(event.lifecycle_id || "") === String(LIFECYCLE_CURRENT_DATA.lifecycle?.id || "")) {
            refreshOpenLifecyclePopup();
        }

        if (dashboardFeed) {
            refreshDashboardActionItems();

            if (event.library_id) {
                refreshDashboardLibraryCount(event.library_id);
            } else if (isLibraryCountRelatedActivity(event)) {
                refreshDashboardLibraryCounts();
            }
        }

        if (isDownloaderRelatedActivity(event)) {
            startDownloaderCardPolling();
            refreshDownloaderCards();
        }
    };

    const scheduleReconnect = () => {
        if (reconnectTimer) {
            return;
        }

        reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;

            if (stream && stream.readyState !== EventSource.CLOSED) {
                return;
            }

            if (stream) {
                try {
                    stream.close();
                } catch (error) {
                    // Ignore cleanup errors.
                }
            }

            stream = null;
            connect();
        }, 5000);
    };

    function connect() {
        if (stream && stream.readyState !== EventSource.CLOSED) {
            return;
        }

        stream = new EventSource("/api/activity/stream");

        stream.onopen = () => {
            if (reconnectTimer) {
                window.clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
        };

        stream.onerror = () => {
            scheduleReconnect();
        };

        stream.onmessage = handleActivityMessage;
    }

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && (!stream || stream.readyState === EventSource.CLOSED)) {
            connect();
        }
    });

    connect();
}


let DASHBOARD_ACTION_ITEMS_REFRESHING = false;
let DASHBOARD_ACTION_ITEMS_REFRESH_QUEUED = false;

async function refreshDashboardActionItems() {
    const grid = document.querySelector("[data-dashboard-action-items]");

    if (!grid) {
        return;
    }

    if (DASHBOARD_ACTION_ITEMS_REFRESHING) {
        DASHBOARD_ACTION_ITEMS_REFRESH_QUEUED = true;
        return;
    }

    DASHBOARD_ACTION_ITEMS_REFRESHING = true;

    try {
        const response = await fetch("/api/dashboard/action-items", {
            headers: {
                "Accept": "application/json",
            },
        });
        const data = await response.json();

        if (!response.ok || !data.success || !Array.isArray(data.items)) {
            return;
        }

        data.items.forEach((item) => {
            const tile = document.querySelector(`[data-action-item-kind="${cssEscape(String(item.kind || ""))}"][data-action-item-id="${cssEscape(String(item.id || ""))}"]`);

            if (!tile) {
                return;
            }

            const value = tile.querySelector("[data-action-item-value]");
            const helper = tile.querySelector("[data-action-item-helper]");

            if (value) {
                value.textContent = String(item.value ?? 0);
            }

            if (helper) {
                helper.textContent = item.helper || "";
            }

            tile.classList.toggle("warning", item.success === false);
        });

        const clock = document.querySelector("[data-dashboard-clock]");

        if (clock) {
            clock.textContent = "Now";
        }
    } catch (error) {
        // Keep current values if a refresh fails.
    } finally {
        DASHBOARD_ACTION_ITEMS_REFRESHING = false;

        if (DASHBOARD_ACTION_ITEMS_REFRESH_QUEUED) {
            DASHBOARD_ACTION_ITEMS_REFRESH_QUEUED = false;
            refreshDashboardActionItems();
        }
    }
}




function initDashboardLibraryCounts() {
    refreshDashboardLibraryCounts();
}

function refreshDashboardLibraryCounts() {
    document.querySelectorAll("[data-dashboard-library-count-tile][data-library-id]").forEach((tile) => {
        refreshDashboardLibraryCount(tile.dataset.libraryId);
    });
}

async function refreshDashboardLibraryCount(libraryId) {
    if (!libraryId) {
        return;
    }

    try {
        const response = await fetch(`/api/dashboard/library-count/${encodeURIComponent(libraryId)}`, {
            headers: { "Accept": "application/json" },
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            return;
        }

        document.querySelectorAll(`[data-dashboard-library-count-tile][data-library-id="${cssEscape(String(libraryId))}"]`).forEach((tile) => {
            const countEl = tile.querySelector("[data-library-count]");

            if (countEl) {
                countEl.textContent = data.label || data.item_count_label || "—";
            }
        });
    } catch (error) {
        // Keep current count if refresh fails.
    }
}

function isLibraryCountRelatedActivity(event) {
    const text = `${event.event_type || ""} ${event.stage || ""} ${event.details || ""}`.toLowerCase();
    return text.includes("library scan completed") || text.includes("available in") || text.includes("media server availability confirmed");
}


let DOWNLOADER_CARD_POLL_TIMER = null;

function initDownloaderCardPolling() {
    if (!document.querySelector("[data-downloader-row]")) {
        return;
    }

    if (document.querySelector(".dashboard-downloader-row.downloader-active")) {
        startDownloaderCardPolling();
    }
}

function isDownloaderRelatedActivity(event) {
    const text = `${event.event_type || ""} ${event.media_title || ""} ${event.source_type || ""}`.toLowerCase();

    return text.includes("grabbed") || text.includes("download started") || text.includes("download completed") || text.includes("download failed") || text.includes("downloader");
}

function startDownloaderCardPolling() {
    if (DOWNLOADER_CARD_POLL_TIMER) {
        return;
    }

    refreshDownloaderCards();
    DOWNLOADER_CARD_POLL_TIMER = window.setInterval(refreshDownloaderCards, 1000);
}

function stopDownloaderCardPolling() {
    if (!DOWNLOADER_CARD_POLL_TIMER) {
        return;
    }

    window.clearInterval(DOWNLOADER_CARD_POLL_TIMER);
    DOWNLOADER_CARD_POLL_TIMER = null;
}

async function refreshDownloaderCards() {
    const rows = document.querySelectorAll("[data-downloader-row]");

    if (!rows.length) {
        stopDownloaderCardPolling();
        return;
    }

    let result;

    try {
        const response = await fetch("/api/downloaders/queue/all", {
            headers: {
                "Accept": "application/json",
            },
        });
        result = await response.json();
    } catch (error) {
        return;
    }

    if (!result || !Array.isArray(result.queues)) {
        return;
    }

    let anyActive = false;

    result.queues.forEach((queue) => {
        const row = document.querySelector(`[data-downloader-row][data-downloader-id="${cssEscape(String(queue.downloader_id || ""))}"]`);

        if (!row) {
            return;
        }

        const activeCount = Number(queue.active_count || 0);
        const totalCount = Number(queue.total_count || activeCount || 0);

        if (activeCount > 0) {
            anyActive = true;
        }

        updateDownloaderRow(row, queue, activeCount, totalCount);
    });

    updateDownloadingStat(result.queues);

    if (!anyActive) {
        stopDownloaderCardPolling();
    }
}

function updateDownloaderRow(row, queue, activeCount, totalCount) {
    const meta = row.querySelector("[data-downloader-meta]");
    const status = row.querySelector("[data-downloader-status]");
    const dot = row.querySelector("[data-downloader-dot]");
    const version = queue.version || "Unknown";

    if (!meta || !status) {
        return;
    }

    row.classList.toggle("downloader-active", activeCount > 0);

    if (dot) {
        dot.classList.toggle("warning", !queue.success);
    }

    if (!queue.success) {
        meta.innerHTML = `
            <span>${escapeHtml(version)}</span>
            <span class="dashboard-downloader-state warning">Unavailable</span>
        `;
        status.className = "dashboard-service-status warning";
        status.textContent = "⚠ Warning";
        return;
    }

    if (activeCount > 0) {
        const parts = [
            `<span>${escapeHtml(version)}</span>`,
            `<span class="dashboard-downloader-state active">Downloading (${escapeHtml(String(activeCount))})</span>`,
        ];

        if (queue.size) {
            parts.push(`<span>${escapeHtml(queue.size)}</span>`);
        }

        if (queue.speed && queue.speed !== "0 B/s") {
            parts.push(`<span class="dashboard-downloader-speed">${escapeHtml(queue.speed)}</span>`);
        }

        if (queue.timeleft && queue.timeleft !== "0:00:00") {
            parts.push(`<span>${escapeHtml(queue.timeleft)} remaining</span>`);
        }

        if (totalCount > activeCount) {
            parts.push(`<span>${escapeHtml(String(totalCount))} queued</span>`);
        }

        meta.innerHTML = parts.join("\n");
        status.className = "dashboard-service-status good";
        status.textContent = "✓ Healthy";
        return;
    }

    meta.innerHTML = `
        <span>${escapeHtml(version)}</span>
        <span class="dashboard-downloader-state idle">Idle</span>
    `;
    status.className = "dashboard-service-status good";
    status.textContent = "✓ Healthy";
}

function updateDownloadingStat(queues) {
    queues.forEach((queue) => {
        const tile = document.querySelector(`[data-action-item-kind="downloader"][data-action-item-id="${cssEscape(String(queue.downloader_id || ""))}"]`);

        if (!tile) {
            return;
        }

        const value = tile.querySelector("[data-action-item-value]");

        if (value) {
            value.textContent = String(Number(queue.active_count || 0));
        }
    });
}

function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
        return window.CSS.escape(value);
    }

    return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function upsertActivityFeedItem(feed, item, limit) {
    const lifecycleId = item.dataset.lifecycleId || "";

    if (!lifecycleId) {
        return;
    }

    const existing = feed.querySelector(`[data-lifecycle-id="${cssEscape(lifecycleId)}"]`);

    if (existing) {
        existing.replaceWith(item);
        return;
    }

    feed.prepend(item);
    trimActivityFeed(feed, limit);
}

function renderDashboardActivityEvent(event, fileDetailLevel = "filename") {
    const item = document.createElement("div");
    item.className = `dashboard-2-activity-row ${escapeHtml(event.status || "info")}`;

    if (event.lifecycle_id) {
        item.classList.add("lifecycle-clickable");
        item.dataset.lifecycleId = event.lifecycle_id;
        item.dataset.lifecycleDisplayTitle = dashboardActivityTitle(event);
        item.setAttribute("role", "button");
        item.setAttribute("tabindex", "0");
        item.setAttribute("title", "Open details");
    }

    const title = dashboardActivityTitle(event);
    const subtitle = dashboardActivitySubtitle(event);
    const subtitleHtml = subtitle ? `<div class="dashboard-2-activity-subtitle">${escapeHtml(subtitle)}</div>` : "";
    const details = dashboardActivityDetails(event, fileDetailLevel);
    const detailsHtml = details ? `<div class="dashboard-2-activity-file">${escapeHtml(details)}</div>` : "";

    item.innerHTML = `
        <div class="dashboard-2-activity-dot"></div>
        <div class="dashboard-2-activity-body">
            <div class="dashboard-2-activity-title">${escapeHtml(title)}</div>
            ${subtitleHtml}
            ${detailsHtml}
        </div>
        <div class="dashboard-2-activity-time">${escapeHtml(event.created_at || "Now")}</div>
        <div class="dashboard-2-chevron">›</div>
    `;

    return item;
}

function dashboardActivityTitle(event) {
    return event.media_title || event.title || event.event_type || "Activity";
}

function dashboardActivitySubtitle(event) {
    const eventType = String(event.event_type || "").trim();
    const title = String(dashboardActivityTitle(event) || "").trim();
    const sourceName = String(event.source_name || "").trim();

    const parts = [];

    if (eventType && eventType !== title) {
        parts.push(eventType);
    }

    if (sourceName && sourceName !== eventType && sourceName !== title) {
        parts.push(sourceName);
    }

    return parts.join(" • ");
}

function dashboardActivityDetails(event, fileDetailLevel = "filename") {
    const details = String(event.details || "").trim();

    if (details && details !== event.event_type && details !== event.media_title) {
        return details;
    }

    if (fileDetailLevel === "path" && event.file_path) {
        return event.file_path;
    }

    if (event.file_name) {
        return event.file_name;
    }

    if (event.file_path) {
        return event.file_path;
    }

    return "";
}

function renderActivityPageEvent(event, fileDetailLevel) {
    const item = document.createElement("article");
    item.className = `activity-page-event ${escapeHtml(event.status || "info")} lifecycle-clickable`;

    if (event.lifecycle_id) {
        item.dataset.lifecycleId = event.lifecycle_id;
        item.dataset.lifecycleDisplayTitle = dashboardActivityTitle(event);
        item.setAttribute("role", "button");
        item.setAttribute("tabindex", "0");
        item.setAttribute("title", "Open details");
    }

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
    feed.querySelectorAll(".activity-event.idle, .dashboard-2-activity-row.idle, .activity-page-empty").forEach((item) => {
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


function initLifecyclePopup() {
    const backdrop = document.querySelector("[data-lifecycle-modal-backdrop]");

    if (!backdrop) {
        return;
    }

    const modal = backdrop.querySelector("[data-lifecycle-modal]");
    const title = backdrop.querySelector("[data-lifecycle-modal-title]");
    const body = backdrop.querySelector("[data-lifecycle-modal-body]");
    const closeButtons = backdrop.querySelectorAll("[data-lifecycle-close]");
    const maximizeButton = backdrop.querySelector("[data-lifecycle-maximize]");

    document.addEventListener("click", (event) => {
        const row = event.target.closest("[data-lifecycle-id]");

        if (!row) {
            return;
        }

        const lifecycleId = row.dataset.lifecycleId;

        if (!lifecycleId) {
            return;
        }

        event.preventDefault();
        const clickedTitle = row.dataset.lifecycleDisplayTitle || row.querySelector(".dashboard-2-activity-title, .activity-event-title, .activity-page-media, .activity-page-title")?.textContent?.trim() || "";
        openLifecycleModal(lifecycleId, backdrop, title, body, clickedTitle);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !backdrop.classList.contains("hidden")) {
            closeLifecycleModal(backdrop);
            return;
        }

        if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-lifecycle-id]")) {
            event.preventDefault();
            openLifecycleModal(event.target.dataset.lifecycleId, backdrop, title, body, event.target.dataset.lifecycleDisplayTitle || "");
        }
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", () => closeLifecycleModal(backdrop));
    });

    backdrop.addEventListener("click", (event) => {
        if (event.target === backdrop) {
            closeLifecycleModal(backdrop);
        }
    });

    if (maximizeButton && modal) {
        maximizeButton.addEventListener("click", () => {
            modal.classList.toggle("maximized");
            maximizeButton.textContent = modal.classList.contains("maximized") ? "❐" : "□";
        });
    }
}

async function refreshOpenLifecyclePopup() {
    if (!LIFECYCLE_CURRENT_DATA || !LIFECYCLE_CURRENT_DATA.lifecycle || !LIFECYCLE_CURRENT_DATA.lifecycle.id) {
        return;
    }

    const backdrop = document.querySelector("[data-lifecycle-modal-backdrop]");

    if (!backdrop || backdrop.classList.contains("hidden")) {
        return;
    }

    const titleElement = backdrop.querySelector("[data-lifecycle-modal-title]");
    const bodyElement = backdrop.querySelector("[data-lifecycle-modal-body]");

    if (!titleElement || !bodyElement) {
        return;
    }

    const lifecycleId = LIFECYCLE_CURRENT_DATA.lifecycle.id;

    try {
        const response = await fetch(`/api/lifecycle/${encodeURIComponent(lifecycleId)}`, {
            headers: {
                "Accept": "application/json",
            },
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            return;
        }

        syncTvSeasonOpenStateFromDom();
        if (displayTitle) {
            data.display_title = displayTitle;
        }

        renderLifecycleModal(data, titleElement, bodyElement);
    } catch (error) {
        // Keep the existing popup content if a live refresh fails.
    }
}

async function openLifecycleModal(lifecycleId, backdrop, titleElement, bodyElement, displayTitle = "") {
    backdrop.classList.remove("hidden");
    document.body.classList.add("modal-open");
    titleElement.textContent = "";
    bodyElement.innerHTML = `<div class="lifecycle-loading lifecycle-loading-quiet"></div>`;

    try {
        const response = await fetch(`/api/lifecycle/${encodeURIComponent(lifecycleId)}`);
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.detail || data.message || "Lifecycle unavailable.");
        }

        if (displayTitle) {
            data.display_title = displayTitle;
        }

        renderLifecycleModal(data, titleElement, bodyElement);
    } catch (error) {
        titleElement.textContent = "Lifecycle unavailable";
        bodyElement.innerHTML = `<div class="lifecycle-error">${escapeHtml(error.message || "Unable to load lifecycle.")}</div>`;
    }
}

let LIFECYCLE_CURRENT_DATA = null;
let LIFECYCLE_CURRENT_POLL_TIMER = null;
const LIFECYCLE_TV_SEASON_OPEN_STATE = new Map();

function tvSeasonStateKey(seasonNumber) {
    const lifecycleId = LIFECYCLE_CURRENT_DATA?.lifecycle?.id || "unknown";
    return `${lifecycleId}:${String(seasonNumber || "")}`;
}

function tvSeasonShouldOpen(season) {
    const seasonNumber = season?.season_number;
    const key = tvSeasonStateKey(seasonNumber);

    if (LIFECYCLE_TV_SEASON_OPEN_STATE.has(key)) {
        return LIFECYCLE_TV_SEASON_OPEN_STATE.get(key) === true;
    }

    return season?.status === "in_progress";
}

function syncTvSeasonOpenStateFromDom() {
    document.querySelectorAll("details.lifecycle-tv-season-row-wrap[data-season-number]").forEach((details) => {
        LIFECYCLE_TV_SEASON_OPEN_STATE.set(tvSeasonStateKey(details.dataset.seasonNumber), details.open === true);
    });
}

function wireTvSeasonOpenTracking() {
    if (window.__mediasyncTvSeasonOpenTrackingWired) {
        return;
    }

    window.__mediasyncTvSeasonOpenTrackingWired = true;

    document.addEventListener("toggle", (event) => {
        const details = event.target;

        if (!details || !details.matches || !details.matches("details.lifecycle-tv-season-row-wrap[data-season-number]")) {
            return;
        }

        LIFECYCLE_TV_SEASON_OPEN_STATE.set(tvSeasonStateKey(details.dataset.seasonNumber), details.open === true);
    }, true);
}

function closeLifecycleModal(backdrop) {
    stopLifecycleCurrentPolling();
    LIFECYCLE_CURRENT_DATA = null;
    LIFECYCLE_TV_SEASON_OPEN_STATE.clear();
    backdrop.classList.add("hidden");
    document.body.classList.remove("modal-open");
}

function renderLifecycleModal(data, titleElement, bodyElement) {
    const popupType = lifecyclePopupType(data);

    if (popupType === "tv") {
        renderTvLifecycleModal(data, titleElement, bodyElement);
        return;
    }

    renderMovieLifecycleModal(data, titleElement, bodyElement);
}

function renderMovieLifecycleModal(data, titleElement, bodyElement) {
    renderLifecycleDetailModal(data, titleElement, bodyElement, "movie");
}

function renderTvLifecycleModal(data, titleElement, bodyElement) {
    renderLifecycleDetailModal(data, titleElement, bodyElement, "tv");
}

function renderLifecycleDetailModal(data, titleElement, bodyElement, popupType) {
    const lifecycle = data.lifecycle || {};
    const events = Array.isArray(data.events) ? data.events : [];
    const mediaServer = data.media_server || {};
    const title = (popupType === "tv" && data.display_title) ? data.display_title : (lifecycle.title || "Unknown Title");
    const mediaLabel = popupType === "tv" ? "TV Series" : "Movie";
    const origin = lifecycleOriginInfo(lifecycle, events);
    const isRequestOrigin = origin.isRequestOrigin;
    const visibleEvents = normalizeVisibleLifecycleEvents(events, lifecycle, mediaServer, data.tv_overview || null);

    LIFECYCLE_CURRENT_DATA = {
        lifecycle,
        events: visibleEvents,
        rawEvents: events,
        mediaServer,
        popupType,
        tvOverview: data.tv_overview || null,
        displayTitle: data.display_title || LIFECYCLE_CURRENT_DATA?.displayTitle || "",
    };

    titleElement.innerHTML = `${escapeHtml(title)} <span class="lifecycle-title-badge">${escapeHtml(mediaLabel)}</span>`;
    bodyElement.dataset.lifecycleMediaType = popupType;

    bodyElement.innerHTML = `
        <section class="lifecycle-popup-shell lifecycle-popup-${escapeHtml(popupType)}" data-lifecycle-popup-type="${escapeHtml(popupType)}">
            <section class="lifecycle-popup-top lifecycle-popup-top-compact">
                <div class="lifecycle-hero-poster">
                    ${lifecyclePosterMarkup(lifecycle, data.tv_overview || null)}
                </div>

                <div class="lifecycle-hero-main">
                    <div class="lifecycle-hero-title-row">
                        <h3>${escapeHtml(title)}</h3>
                        <span class="lifecycle-title-badge inline">${escapeHtml(mediaLabel)}</span>
                    </div>
                    <div class="lifecycle-chip-row">
                        ${lifecycleChip(lifecycle.quality_profile)}
                    </div>
                    <div class="lifecycle-hero-meta-grid">
                        ${isRequestOrigin ? lifecycleHeroMeta("Requested By", origin.createdBy || "—") : ""}
                        ${lifecycleHeroMeta(isRequestOrigin ? "Via" : "Source", origin.sourceApp || lifecycleSourceLabel(origin.sourceType))}
                        ${lifecycleHeroMeta("Created", formatLifecycleTime(lifecycle.created_at))}
                    </div>
                </div>
            </section>

            <section class="lifecycle-popup-main-grid lifecycle-popup-main-grid-three">
                <aside class="lifecycle-detail-left">
                    ${renderLifecycleMetadataPanel(lifecycle, data.tv_overview, popupType, isRequestOrigin, origin)}
                </aside>

                <section class="lifecycle-detail-center">
                    <div class="lifecycle-section-title">Progress</div>
                    <div class="lifecycle-timeline" data-lifecycle-timeline>
                        ${renderLifecycleTimeline(visibleEvents, popupType)}
                    </div>
                    ${renderLifecycleMetrics(events, lifecycle, mediaServer)}
                </section>

                <aside class="lifecycle-current-card lifecycle-detail-right" data-lifecycle-current-card>
                    ${renderCurrentLifecycleActivity(visibleEvents, mediaServer, popupType, lifecycle, data.tv_overview)}
                </aside>
            </section>

            ${popupType === "tv" ? renderTvSeasonOverview(data.tv_overview) : ""}
        </section>
    `;

    startLifecycleCurrentPolling();
}

function lifecyclePopupType(data) {
    const lifecycle = data.lifecycle || {};
    const events = Array.isArray(data.events) ? data.events : [];
    const lifecycleMediaType = String(lifecycle.media_type || "").trim().toLowerCase();

    if (events.some((event) => String(event.source_type || "").trim().toLowerCase() === "sonarr")) {
        return "tv";
    }

    if (["tv", "show", "series", "tvshows"].includes(lifecycleMediaType)) {
        return "tv";
    }

    return "movie";
}

function lifecyclePosterMarkup(lifecycle, tvOverview) {
    const posterUrl = lifecycle.poster_url || (tvOverview && (tvOverview.poster_url || tvOverview.series?.poster_url)) || "";
    const proxiedPosterUrl = posterUrl && posterUrl.startsWith("http")
        ? `/api/image-proxy?url=${encodeURIComponent(posterUrl)}`
        : posterUrl;

    if (posterUrl) {
        return `
            <div class="lifecycle-poster-frame">
                <img class="lifecycle-poster" src="${escapeHtml(proxiedPosterUrl)}" alt="${escapeHtml(lifecycle.title || "Poster")}" onerror="
if (!this.dataset.retryAttempted) {
    this.dataset.retryAttempted='true';
    const img=this;
    setTimeout(() => {
        img.src = img.src + (img.src.includes('?') ? '&' : '?') + 'retry=' + Date.now();
    }, 2000);
} else {
    this.remove();
    this.parentElement.classList.add('poster-missing');
    this.parentElement.textContent='No Poster';
}
">
            </div>
        `;
    }

    return `<div class="lifecycle-poster-frame poster-missing">No Poster</div>`;
}

function lifecycleChip(value) {
    if (!value) {
        return "";
    }

    return `<span class="lifecycle-chip">${escapeHtml(value)}</span>`;
}

function lifecycleHeroMeta(label, value) {
    return `
        <div class="lifecycle-hero-meta-item">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value || "—")}</strong>
        </div>
    `;
}

function lifecycleOriginInfo(lifecycle, events) {
    const requestEvent = Array.isArray(events)
        ? events.find((event) => String(event.stage || "").trim().toLowerCase() === "requested")
        : null;

    if (requestEvent) {
        return {
            sourceApp: requestEvent.source_name || lifecycle.source_app || lifecycleSourceLabel(requestEvent.source_type || lifecycle.source_type),
            sourceType: requestEvent.source_type || lifecycle.source_type || "seerr",
            createdBy: lifecycle.created_by || "—",
            isRequestOrigin: true,
        };
    }

    return {
        sourceApp: lifecycle.source_app || lifecycleSourceLabel(lifecycle.source_type),
        sourceType: lifecycle.source_type || "",
        createdBy: lifecycle.created_by || "",
        isRequestOrigin: lifecycleHasRequestOrigin(lifecycle, events),
    };
}

function renderLifecycleMetadataPanel(lifecycle, tvOverview, popupType, isRequestOrigin = true, origin = null) {
    const originInfo = origin || lifecycleOriginInfo(lifecycle, []);
    const rows = isRequestOrigin
        ? [
            ["Requested By", originInfo.createdBy || lifecycle.created_by],
            ["Requested Via", originInfo.sourceApp || lifecycle.source_app || lifecycleSourceLabel(lifecycle.source_type)],
            ["Request Time", formatLifecycleTime(lifecycle.created_at)],
            ["Request Type", popupType === "tv" ? "TV Series" : "Movie"],
            ["Quality Profile", lifecycle.quality_profile],
        ]
        : [
            ["Source", originInfo.sourceApp || lifecycle.source_app || lifecycleSourceLabel(lifecycle.source_type)],
            ["Created", formatLifecycleTime(lifecycle.created_at)],
            ["Type", popupType === "tv" ? "TV Series" : "Movie"],
            ["Quality Profile", lifecycle.quality_profile],
        ];

    if (popupType === "tv") {
        const series = tvOverview && tvOverview.series ? tvOverview.series : {};
        const monitored = Array.isArray(series.monitored_seasons) ? series.monitored_seasons : [];
        rows.push(["Monitored Seasons", monitored.length ? [...monitored].sort((a, b) => Number(a) - Number(b)).join(", ") : "—"]);
        if (isRequestOrigin) {
            rows.push(["Requested", monitored.length ? monitoredSeasonLabel(monitored) : "—"]);
        }
    }

    const infoRows = [
        ["Year", lifecycleYear(lifecycle.title, lifecycle.created_at)],
        ["TMDB ID", lifecycle.tmdb_id],
        ["TVDB ID", lifecycle.tvdb_id],
        ["IMDB ID", lifecycle.imdb_id],
    ];

    if (popupType === "tv" && tvOverview && tvOverview.series) {
        infoRows.push(["Network", tvOverview.series.network]);
        infoRows.push(["Runtime", tvOverview.series.runtime ? `~ ${tvOverview.series.runtime} min` : ""]);
        infoRows.push(["Status", tvOverview.series.status]);
        infoRows.push(["Episodes", `${tvOverview.series.episodes_available || 0} / ${tvOverview.series.episodes_total || 0}`]);
    }

    return `
        <div class="lifecycle-side-card">
            <div class="lifecycle-section-title">${isRequestOrigin ? "Request Details" : "Media Details"}</div>
            ${rows.map(([label, value]) => lifecycleInfoRow(label, value)).join("")}
        </div>
        <div class="lifecycle-side-card">
            <div class="lifecycle-section-title">${popupType === "tv" ? "Series Information" : "Media Information"}</div>
            ${infoRows.map(([label, value]) => lifecycleInfoRow(label, value)).join("")}
        </div>
    `;
}

function lifecycleInfoRow(label, value) {
    if (value === undefined || value === null || value === "") {
        value = "—";
    }

    return `
        <div class="lifecycle-info-row">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>
    `;
}

function lifecycleHasRequestOrigin(lifecycle, rawEvents = []) {
    const sourceType = String(lifecycle.source_type || "").trim().toLowerCase();
    const sourceApp = String(lifecycle.source_app || "").trim().toLowerCase();

    if (sourceType === "seerr" || sourceApp.includes("seerr") || sourceApp.includes("overseerr") || sourceApp.includes("jellyseerr")) {
        return true;
    }

    return rawEvents.some((event) => {
        const stage = String(event.stage || event.title || event.event_type || "").trim().toLowerCase();
        const eventSource = String(event.source_type || "").trim().toLowerCase();
        return eventSource === "seerr" && stage === "requested";
    });
}

function normalizeVisibleLifecycleEvents(events, lifecycle, mediaServer, tvOverview = null) {
    const normalized = [];

    events.forEach((event) => {
        const item = normalizeLifecycleEvent(event, lifecycle, mediaServer);

        if (!item) {
            return;
        }

        normalized.push(item);
    });

    return buildLifecycleStageModel(normalized, lifecycle, mediaServer, tvOverview);
}

function normalizeLifecycleEvent(event, lifecycle, mediaServer) {
    const stageText = String(event.stage || event.title || event.activity_event_type || "").trim();
    const lowerStage = stageText.toLowerCase();
    const sourceType = String(event.source_type || "").trim().toLowerCase();
    const sourceName = event.source_name || lifecycleSourceLabel(sourceType);

    if (sourceType === "seerr" && lowerStage === "available") {
        return null;
    }

    if (["approved", "processing"].includes(lowerStage) && sourceType === "seerr") {
        return null;
    }

    let stage = stageText || "Lifecycle Event";
    let detail = event.details || "";
    let normalizedSourceType = sourceType;
    let normalizedSourceName = sourceName;
    let status = event.status || "success";
    let kind = "event";

    if (lowerStage === "requested") {
        stage = "Requested";
        kind = "requested";
        detail = "";
    } else if (lowerStage === "grabbed") {
        stage = `Sent to ${sourceName || lifecycleSourceLabel(sourceType)}`;
        kind = "grabbed";
        detail = "";
    } else if (lowerStage.includes("download started")) {
        stage = "Downloading";
        kind = "download_started";
        detail = "";
    } else if (lowerStage.includes("download completed")) {
        stage = "Downloaded";
        kind = "download_completed";
        detail = "";
    } else if (lowerStage.includes("download cancelled")) {
        stage = "Download Cancelled";
        kind = "download_cancelled";
        detail = "";
        status = "cancelled";
    } else if (lowerStage.includes("download failed")) {
        stage = "Download Failed";
        kind = "download_failed";
        detail = "";
        status = "error";
    } else if (lowerStage === "imported") {
        stage = "Imported";
        kind = "imported";
        detail = "";
    } else if (lowerStage.includes("library sync") || lowerStage.includes("library scan")) {
        stage = "Library Scan";
        kind = "library_scan";
        normalizedSourceType = "mediasync";
        normalizedSourceName = event.activity_library_name || "Library";
        detail = event.activity_library_name || "";
    } else if (lowerStage.startsWith("available in")) {
        stage = stageText;
        kind = "available";
        detail = event.activity_library_name || "";
    }

    return {
        ...event,
        stage,
        details: detail,
        source_type: normalizedSourceType,
        source_name: normalizedSourceName,
        status,
        kind,
    };
}


function _safeNumber(value, fallback = 0) {
    const parsed = Number(value);

    if (Number.isFinite(parsed)) {
        return parsed;
    }

    return fallback;
}

function buildLifecycleStageModel(events, lifecycle, mediaServer, tvOverview = null) {
    const isRequestOrigin = lifecycleHasRequestOrigin(lifecycle, events);
    const arrType = lifecycleArrType(events, lifecycle);
    const arrLabel = lifecycleArrLabel(events, arrType);
    const mediaServerType = String((mediaServer || {}).server_type || "").trim().toLowerCase();
    const mediaServerLabelText = mediaServerLabel(mediaServerType) || "Media Server";

    const requested = firstLifecycleEvent(events, ["requested"]);
    const grabbed = firstLifecycleEvent(events, ["grabbed"]);
    const downloadStarted = firstLifecycleEvent(events, ["download_started"]);
    const downloadCompleted = firstLifecycleEvent(events, ["download_completed"]);
    const downloadCancelled = firstLifecycleEvent(events, ["download_cancelled"]);
    const downloadFailed = firstLifecycleEvent(events, ["download_failed"]);
    const imported = firstLifecycleEvent(events, ["imported"]);
    const libraryScan = firstLifecycleEvent(events, ["library_scan"]);
    const available = firstLifecycleEvent(events, ["available"]);

    const mediaType = String(lifecycle.media_type || "").toLowerCase();
    const isTvLifecycle = arrType === "sonarr" || ["tv", "show", "series", "tvshows"].includes(mediaType);

    if (isTvLifecycle) {
        return buildTvLifecycleStageModel({
            events,
            lifecycle,
            mediaServer,
            isRequestOrigin,
            arrType,
            arrLabel,
            mediaServerType,
            mediaServerLabelText,
            requested,
            grabbed,
            downloadStarted,
            downloadCompleted,
            downloadCancelled,
            downloadFailed,
            imported,
            libraryScan,
            available,
            tvOverview,
        });
    }

    const stages = [];

    if (isRequestOrigin) {
        stages.push(lifecycleStage({
            id: "request",
            completeLabel: "Requested",
            activeLabel: "Requested",
            futureLabel: "Waiting for Request",
            source_type: requested?.source_type || lifecycle.source_type || "seerr",
            source_name: requested?.source_name || lifecycle.source_app || lifecycleSourceLabel(lifecycle.source_type),
            event: requested,
            complete: Boolean(requested || lifecycle.id),
            active: false,
        }));
    }

    stages.push(
        lifecycleStage({
            id: "arr",
            completeLabel: `Sent to ${arrLabel}`,
            activeLabel: `Sending to ${arrLabel}`,
            futureLabel: `Waiting for ${arrLabel}`,
            source_type: arrType,
            source_name: grabbed?.source_name || arrLabel,
            event: grabbed,
            complete: Boolean(grabbed || downloadStarted || downloadCompleted || imported || libraryScan || available),
            active: Boolean((isRequestOrigin ? requested : lifecycle.id) && !grabbed && !downloadStarted && !downloadCompleted && !downloadCancelled && !downloadFailed),
        }),
        lifecycleStage({
            id: "download",
            completeLabel: downloadCancelled ? "Download Cancelled" : (downloadFailed ? "Download Failed" : "Downloaded"),
            activeLabel: downloadStarted ? "Downloading" : "Waiting for Download",
            futureLabel: "Waiting for Download",
            source_type: downloadStarted?.source_type || downloadCompleted?.source_type || downloadCancelled?.source_type || downloadFailed?.source_type || "downloader",
            source_name: downloadStarted?.source_name || downloadCompleted?.source_name || downloadCancelled?.source_name || downloadFailed?.source_name || "Downloader",
            event: downloadFailed || downloadCancelled || downloadCompleted || downloadStarted,
            complete: Boolean(downloadCompleted || downloadCancelled || downloadFailed || imported || libraryScan || available),
            active: Boolean((grabbed || requested) && !downloadCompleted && !downloadCancelled && !downloadFailed && !imported && !libraryScan && !available),
            failed: Boolean(downloadFailed),
            cancelled: Boolean(downloadCancelled),
        }),
        lifecycleStage({
            id: "import",
            completeLabel: "Imported",
            activeLabel: "Importing",
            futureLabel: "Waiting for Import",
            source_type: imported?.source_type || grabbed?.source_type || arrType,
            source_name: imported?.source_name || grabbed?.source_name || arrLabel,
            event: imported || downloadCompleted,
            complete: Boolean(imported || libraryScan || available),
            active: Boolean(downloadCompleted && !imported && !libraryScan && !available),
        }),
        lifecycleStage({
            id: "scan",
            completeLabel: "Library Scanned",
            activeLabel: "Library Scan",
            futureLabel: "Waiting for Scan",
            source_type: "mediasync",
            source_name: libraryScan?.source_name || libraryScan?.activity_library_name || "Library",
            event: libraryScan,
            complete: Boolean(available),
            active: Boolean((imported || libraryScan) && !available),
        }),
        lifecycleStage({
            id: "available",
            completeLabel: `Available in ${mediaServerLabelText}`,
            activeLabel: `Waiting for ${mediaServerLabelText}`,
            futureLabel: `Waiting for ${mediaServerLabelText}`,
            source_type: mediaServerType || available?.source_type || "media_server",
            source_name: mediaServerLabelText,
            event: available,
            complete: Boolean(available),
            active: Boolean(libraryScan && !available),
        }),
    );

    const activeIndex = stages.findIndex((stage) => stage.state === "active");

    if (activeIndex === -1 && !stages[stages.length - 1].complete) {
        const firstFutureIndex = stages.findIndex((stage) => stage.state === "future");

        if (firstFutureIndex >= 0) {
            stages[firstFutureIndex].state = "active";
            stages[firstFutureIndex].label = stages[firstFutureIndex].activeLabel;
        }
    }

    return stages;
}

function buildTvLifecycleStageModel(context) {
    const {
        events,
        lifecycle,
        isRequestOrigin,
        arrType,
        arrLabel,
        mediaServerType,
        mediaServerLabelText,
        tvOverview,
    } = context;

    const requested = latestLifecycleEvent(events, ["requested"]);
    const grabbed = latestLifecycleEvent(events, ["grabbed"]);
    const downloadStarted = latestLifecycleEvent(events, ["download_started"]);
    const downloadCompleted = latestLifecycleEvent(events, ["download_completed"]);
    const downloadCancelled = latestLifecycleEvent(events, ["download_cancelled"]);
    const downloadFailed = latestLifecycleEvent(events, ["download_failed"]);
    const imported = latestLifecycleEvent(events, ["imported"]);
    const libraryScan = latestLifecycleEvent(events, ["library_scan"]);
    const available = latestLifecycleEvent(events, ["available"]);

    const activeTvDownloading = Boolean(_safeNumber((tvOverview || {}).series?.episodes_downloading) > 0 && !availableIsCurrentForSequence(available, downloadStarted));

    const successfulAfterDownload = latestOfLifecycleEvents([imported, libraryScan, available]);
    const downloadCancelledIsTerminal = Boolean(downloadCancelled && !successfulAfterDownload);
    const downloadFailedIsTerminal = Boolean(downloadFailed && !successfulAfterDownload);
    const downloadTerminal = latestOfLifecycleEvents([downloadCompleted, downloadCancelledIsTerminal ? downloadCancelled : null, downloadFailedIsTerminal ? downloadFailed : null]);
    const downloadTerminalAfterStart = Boolean(downloadTerminal && (!downloadStarted || lifecycleEventIsSameOrAfter(downloadTerminal, downloadStarted)));
    const importedAfterDownload = Boolean(imported && (!downloadStarted || lifecycleEventIsAfter(imported, downloadStarted)) && (!downloadCompleted || lifecycleEventIsSameOrAfter(imported, downloadCompleted)));
    const scanAfterImport = Boolean(libraryScan && (!imported || lifecycleEventIsSameOrAfter(libraryScan, imported)) && (!downloadStarted || lifecycleEventIsAfter(libraryScan, downloadStarted)));
    const availableAfterScan = Boolean(available && (!libraryScan || lifecycleEventIsSameOrAfter(available, libraryScan)) && (!downloadStarted || lifecycleEventIsAfter(available, downloadStarted)));

    const downloadIsActive = Boolean(activeTvDownloading || (downloadStarted && !downloadTerminalAfterStart && !importedAfterDownload && !availableAfterScan));
    const downloadIsComplete = Boolean(downloadTerminalAfterStart || importedAfterDownload || scanAfterImport || availableAfterScan);
    const importIsActive = Boolean(downloadIsComplete && !importedAfterDownload && !downloadCancelledIsTerminal && !downloadFailedIsTerminal && !availableAfterScan);
    const importIsComplete = Boolean(importedAfterDownload || scanAfterImport || availableAfterScan);
    const scanIsActive = Boolean(importIsComplete && !availableAfterScan);
    const scanIsComplete = Boolean(availableAfterScan);

    const stages = [];

    if (isRequestOrigin) {
        stages.push(lifecycleStage({
            id: "request",
            completeLabel: "Requested",
            activeLabel: "Requested",
            futureLabel: "Waiting for Request",
            source_type: requested?.source_type || lifecycle.source_type || "seerr",
            source_name: requested?.source_name || lifecycle.source_app || lifecycleSourceLabel(lifecycle.source_type),
            event: requested,
            complete: Boolean(requested || lifecycle.id),
            active: false,
        }));
    }

    stages.push(
        lifecycleStage({
            id: "arr",
            completeLabel: `Sent to ${arrLabel}`,
            activeLabel: `Sending to ${arrLabel}`,
            futureLabel: `Waiting for ${arrLabel}`,
            source_type: arrType,
            source_name: grabbed?.source_name || arrLabel,
            event: grabbed,
            complete: Boolean(grabbed || downloadStarted || lifecycle.id),
            active: false,
        }),
        lifecycleStage({
            id: "download",
            completeLabel: downloadCancelled ? "Download Cancelled" : (downloadFailed ? "Download Failed" : "Downloaded"),
            activeLabel: "Downloading",
            futureLabel: "Waiting for Download",
            source_type: downloadStarted?.source_type || downloadCompleted?.source_type || downloadCancelled?.source_type || downloadFailed?.source_type || "downloader",
            source_name: downloadStarted?.source_name || downloadCompleted?.source_name || downloadCancelled?.source_name || downloadFailed?.source_name || "Downloader",
            event: (downloadFailedIsTerminal ? downloadFailed : null) || (downloadCancelledIsTerminal ? downloadCancelled : null) || downloadTerminal || downloadStarted,
            complete: downloadIsComplete,
            active: downloadIsActive,
            failed: Boolean(downloadFailedIsTerminal && lifecycleEventIsSameOrAfter(downloadFailed, downloadStarted)),
            cancelled: Boolean(downloadCancelledIsTerminal && lifecycleEventIsSameOrAfter(downloadCancelled, downloadStarted)),
        }),
        lifecycleStage({
            id: "import",
            completeLabel: "Imported",
            activeLabel: "Importing",
            futureLabel: "Waiting for Import",
            source_type: imported?.source_type || grabbed?.source_type || arrType,
            source_name: imported?.source_name || grabbed?.source_name || arrLabel,
            event: importedAfterDownload ? imported : downloadTerminal,
            complete: importIsComplete,
            active: importIsActive,
        }),
        lifecycleStage({
            id: "scan",
            completeLabel: "Smart Scan",
            activeLabel: "Smart Scan Active",
            futureLabel: "Waiting for Smart Scan",
            source_type: "mediasync",
            source_name: libraryScan?.source_name || libraryScan?.activity_library_name || "Library",
            event: scanAfterImport ? libraryScan : imported,
            complete: scanIsComplete,
            active: scanIsActive,
        }),
        lifecycleStage({
            id: "available",
            completeLabel: `Available in ${mediaServerLabelText}`,
            activeLabel: `Waiting for ${mediaServerLabelText}`,
            futureLabel: `Waiting for ${mediaServerLabelText}`,
            source_type: mediaServerType || available?.source_type || "media_server",
            source_name: mediaServerLabelText,
            event: availableAfterScan ? available : null,
            complete: availableAfterScan,
            active: false,
        }),
    );

    return stages;
}

function lifecycleStage(config) {
    let state = "future";
    let label = config.futureLabel;

    if (config.failed) {
        state = "failed";
        label = config.completeLabel;
    } else if (config.cancelled) {
        state = "cancelled";
        label = config.completeLabel;
    } else if (config.complete) {
        state = "complete";
        label = config.completeLabel;
    } else if (config.active) {
        state = "active";
        label = config.activeLabel;
    }

    return {
        ...config,
        state,
        label,
        stage: label,
        title: label,
        source_type: config.source_type,
        source_name: config.source_name,
        created_at: config.event?.created_at || "",
        details: config.event?.details || "",
        activity_library_name: config.event?.activity_library_name || config.event?.details || "",
        activity_library_image_url: config.event?.activity_library_image_url || "",
        status: state === "active" ? "active" : (state === "failed" ? "error" : "success"),
        original_event: config.event || null,
    };
}

function lifecycleArrType(events, lifecycle) {
    if (events.some((event) => event.source_type === "sonarr")) {
        return "sonarr";
    }

    if (events.some((event) => event.source_type === "radarr")) {
        return "radarr";
    }

    const mediaType = String(lifecycle.media_type || "").toLowerCase();

    if (["tv", "series", "show", "tvshows"].includes(mediaType)) {
        return "sonarr";
    }

    return "radarr";
}

function lifecycleArrLabel(events, arrType) {
    const arrEvent = events.find((event) => event.source_type === arrType);

    if (arrEvent && arrEvent.source_name) {
        return arrEvent.source_name;
    }

    return lifecycleSourceLabel(arrType);
}

function firstLifecycleEvent(events, kinds) {
    return [...events]
        .filter((event) => kinds.includes(event.kind))
        .sort((a, b) => lifecycleEventTimestamp(a) - lifecycleEventTimestamp(b))[0] || null;
}

function latestLifecycleEvent(events, kinds) {
    return [...events]
        .filter((event) => kinds.includes(event.kind))
        .sort((a, b) => lifecycleEventTimestamp(b) - lifecycleEventTimestamp(a))[0] || null;
}

function latestOfLifecycleEvents(items) {
    return items
        .filter(Boolean)
        .sort((a, b) => lifecycleEventTimestamp(b) - lifecycleEventTimestamp(a))[0] || null;
}

function lifecycleEventTimestamp(event) {
    if (!event) {
        return 0;
    }

    const parsed = Date.parse(event.created_at || event.updated_at || "");

    if (Number.isFinite(parsed)) {
        return parsed;
    }

    return 0;
}

function lifecycleEventIsSameOrAfter(candidate, reference) {
    if (!candidate) {
        return false;
    }

    if (!reference) {
        return true;
    }

    return lifecycleEventTimestamp(candidate) >= lifecycleEventTimestamp(reference);
}

function lifecycleEventIsAfter(candidate, reference) {
    if (!candidate) {
        return false;
    }

    if (!reference) {
        return true;
    }

    return lifecycleEventTimestamp(candidate) > lifecycleEventTimestamp(reference);
}

function availableIsCurrentForSequence(available, downloadStarted) {
    return Boolean(available && (!downloadStarted || lifecycleEventIsAfter(available, downloadStarted)));
}

function renderLifecycleMetrics(rawEvents, lifecycle = {}, mediaServer = {}) {
    const events = Array.isArray(rawEvents)
        ? rawEvents.map((event) => normalizeLifecycleEvent(event, lifecycle, mediaServer)).filter(Boolean)
        : [];

    const grabbed = latestLifecycleEvent(events, ["grabbed"]);
    const available = latestLifecycleEvent(events, ["available"]);
    const downloadStarted = latestLifecycleEvent(events, ["download_started"]);
    const downloadCompleted = latestLifecycleEvent(
        events.filter((event) =>
            event &&
            event.kind === "download_completed" &&
            (!downloadStarted || lifecycleEventTimestamp(event) >= lifecycleEventTimestamp(downloadStarted))
        ),
        ["download_completed"]
    );

    const downloadTime = downloadStarted && downloadCompleted
        ? formatLifecycleDuration(downloadStarted.created_at, downloadCompleted.created_at)
        : "In progress";

    const totalTime = grabbed && available && lifecycleEventTimestamp(available) >= lifecycleEventTimestamp(grabbed)
        ? formatLifecycleDuration(grabbed.created_at, available.created_at)
        : "In progress";

    return `
        <div class="lifecycle-metrics" data-lifecycle-metrics>
            <div class="lifecycle-metric">
                <span>Download Time</span>
                <strong>${escapeHtml(downloadTime)}</strong>
            </div>
            <div class="lifecycle-metric">
                <span>Total Time</span>
                <strong>${escapeHtml(totalTime)}</strong>
            </div>
        </div>
    `;
}

function updateLifecycleMetrics(rawEvents, lifecycle = {}, mediaServer = {}) {
    const metrics = document.querySelector("[data-lifecycle-metrics]");

    if (!metrics) {
        return;
    }

    const wrapper = document.createElement("div");
    wrapper.innerHTML = renderLifecycleMetrics(rawEvents, lifecycle, mediaServer).trim();

    if (wrapper.firstElementChild) {
        metrics.replaceWith(wrapper.firstElementChild);
    }
}

function formatLifecycleDuration(startValue, endValue) {
    if (!startValue || !endValue) {
        return "In progress";
    }

    const start = new Date(startValue).getTime();
    const end = new Date(endValue).getTime();

    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) {
        return "—";
    }

    const totalSeconds = Math.round((end - start) / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    }

    if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    }

    return `${seconds}s`;
}

function renderLifecycleTimeline(events, popupType = "movie") {
    if (!events.length) {
        return `<div class="lifecycle-empty">No lifecycle stages yet.</div>`;
    }

    return events.map((event) => {
        const stateClass = event.state || "future";
        const icon = lifecycleIconMarkup(event);
        const sourceLabel = event.source_name || lifecycleSourceLabel(event.source_type);
        const stage = event.label || event.stage || event.title || "Lifecycle stage";
        const detail = event.details || "";
        const time = event.created_at ? formatLifecycleTime(event.created_at) : "";

        return `
            <div class="lifecycle-timeline-row ${stateClass}" data-lifecycle-timeline-row data-timeline-stage="${escapeHtml(stage)}">
                <div class="lifecycle-timeline-rail">
                    <div class="lifecycle-state-token"><span>${stateTokenSymbol(stateClass)}</span></div>
                    <div class="lifecycle-timeline-icon">${icon}</div>
                </div>
                <div class="lifecycle-timeline-content">
                    <div class="lifecycle-timeline-topline">
                        <div class="lifecycle-timeline-stage">${escapeHtml(stage)}</div>
                        <div class="lifecycle-timeline-time">${escapeHtml(time)}</div>
                    </div>
                    <div class="lifecycle-timeline-source">${escapeHtml(sourceLabel)}</div>
                    ${detail ? `<div class="lifecycle-timeline-detail">${escapeHtml(detail)}</div>` : ""}
                </div>
            </div>
        `;
    }).join("");
}

function lifecycleTimelineState(event, index, total) {
    return event.state || "future";
}

function stateTokenSymbol(stateClass) {
    if (stateClass === "failed") {
        return "!";
    }

    if (stateClass === "cancelled") {
        return "×";
    }

    if (stateClass === "active") {
        return "◉";
    }

    if (stateClass === "future") {
        return "";
    }

    return "✓";
}

function enrichLifecycleEventsWithActiveDownload(events, activeDownload) {
    if (!activeDownload || !Array.isArray(events)) {
        return events;
    }

    return events.map((stage) => {
        if (!stage || stage.id !== "download" || stage.state !== "active") {
            return stage;
        }

        return {
            ...stage,
            source_type: activeDownload.downloader_type || stage.source_type || "downloader",
            source_name: activeDownload.downloader_name || stage.source_name || "Downloader",
        };
    });
}

function renderCurrentLifecycleActivity(events, mediaServer, popupType = "movie", lifecycle = {}, tvOverview = null) {
    if (!events.length) {
        return `<div class="lifecycle-current-empty">Waiting for activity.</div>`;
    }

    if (popupType === "tv") {
        return renderTvCurrentLifecycleActivity(events, mediaServer, lifecycle, tvOverview);
    }

    const current = currentLifecycleStage(events);
    return renderStaticCurrentActivity(current, mediaServer, lifecycle);
}

function renderTvCurrentLifecycleActivity(events, mediaServer, lifecycle = {}, tvOverview = null, activeDownload = null) {
    const cards = [];

    const downloadingStage = events.find((stage) => stage.id === "download" && stage.state === "active");
    const importingStage = events.find((stage) => stage.id === "import" && stage.state === "active");
    const scanStage = events.find((stage) => stage.id === "scan" && stage.state === "active");
    const availableStage = events.find((stage) => stage.id === "available" && stage.state === "complete");

    if (activeDownload || downloadingStage) {
        cards.push(renderTvCurrentDownloadingCard(activeDownload, downloadingStage));
    }

    if (importingStage) {
        cards.push(renderTvCurrentSimpleCard(importingStage, "Importing", "Importing"));
    }

    if (scanStage) {
        cards.push(renderTvCurrentSimpleCard(scanStage, scanStage.label || "Smart Scan", smartScanDetail(scanStage)));
    }

    if (!cards.length && availableStage) {
        cards.push(renderTvAvailableCurrentCard(availableStage, mediaServer, tvOverview));
    }

    if (!cards.length) {
        return `<div class="lifecycle-current-empty">Waiting for active TV activity.</div>`;
    }

    return `<div class="lifecycle-tv-current-stack">${cards.join("")}</div>`;
}

function renderTvCurrentDownloadingCard(download, stage) {
    if (download) {
        const percent = Number(download.percent || 0);
        const safePercent = Math.max(0, Math.min(100, Math.round(percent)));
        const itemName = download.name || download.filename || stage?.source_name || "Download";
        const icon = lifecycleIconMarkup({ source_type: download.downloader_type || "downloader", source_name: download.downloader_name || "Downloader" });

        return `
            <div class="lifecycle-tv-current-card downloading">
                <div class="lifecycle-tv-current-title-row">
                    <div class="lifecycle-current-icon">${icon}</div>
                    <div>
                        <div class="lifecycle-current-title">Downloading</div>
                        <div class="lifecycle-current-meta">${escapeHtml(itemName)}</div>
                    </div>
                    <div class="lifecycle-tv-current-ring">
                        ${progressRingMarkup(safePercent, "compact")}
                    </div>
                </div>
                <div class="lifecycle-tv-current-subline">${escapeHtml(download.downloader_name || "Downloader")} ${download.speed ? `• ${escapeHtml(download.speed)}` : ""}${(download.eta || download.queue_timeleft) ? ` • ETA: ${escapeHtml(download.eta || download.queue_timeleft)}` : ""}</div>
            </div>
        `;
    }

    return renderTvCurrentSimpleCard(stage, "Downloading", "Active download in progress");
}

function renderTvCurrentSimpleCard(stage, title, detail) {
    const state = String(stage?.state || "active").toLowerCase();
    const icon = lifecycleIconMarkup(stage || { source_type: "mediasync", source_name: "MediaSync" });

    return `
        <div class="lifecycle-tv-current-card ${escapeHtml(stage?.id || state)}">
            <div class="lifecycle-tv-current-title-row">
                <div class="lifecycle-current-icon">${icon}</div>
                <div>
                    <div class="lifecycle-current-title">${escapeHtml(title || stage?.label || "Current Activity")}</div>
                    <div class="lifecycle-current-meta">${escapeHtml(stage?.source_name || lifecycleSourceLabel(stage?.source_type))}</div>
                    <div class="lifecycle-current-state ${escapeHtml(state)}">${escapeHtml(detail || "Active")}</div>
                </div>
            </div>
        </div>
    `;
}

function renderTvAvailableCurrentCard(stage, mediaServer, tvOverview) {
    const series = tvOverview && tvOverview.series ? tvOverview.series : {};
    const percent = Number(series.percent_available || 0);
    const count = series.count_label || `${series.episodes_available || 0} / ${series.episodes_total || 0} Episodes`;
    const title = stage?.label || `Available in ${mediaServerLabel((mediaServer || {}).server_type) || "Media Server"}`;

    return `
        <div class="lifecycle-tv-current-card available">
            <div class="lifecycle-tv-current-title-row">
                <div class="lifecycle-current-icon">${lifecycleIconMarkup(stage)}</div>
                <div>
                    <div class="lifecycle-current-title">${escapeHtml(title)}</div>
                    <div class="lifecycle-current-meta">${escapeHtml(count)}</div>
                    <div class="lifecycle-current-state complete">${escapeHtml(percent)}% Available</div>
                </div>
            </div>
        </div>
    `;
}

function smartScanDetail(stage) {
    const text = String(stage?.original_event?.stage || stage?.original_event?.event_type || stage?.label || "").toLowerCase();

    if (text.includes("interim")) {
        return "Interim scan running";
    }

    if (text.includes("final")) {
        return "Final scan running";
    }

    if (text.includes("queue")) {
        return "Monitoring Sonarr queue";
    }

    return "Monitoring Sonarr Queue";
}

function currentLifecycleStage(stages) {
    const active = stages.find((stage) => stage.state === "active");

    if (active) {
        return active;
    }

    const terminal = [...stages].reverse().find((stage) => ["failed", "cancelled"].includes(stage.state));

    if (terminal) {
        return terminal;
    }

    return [...stages].reverse().find((stage) => stage.state === "complete") || stages[0];
}

function renderStaticCurrentActivity(current, mediaServer, lifecycle = {}) {
    const icon = lifecycleIconMarkup(current);
    const mediaServerType = mediaServerLabel(mediaServer.server_type);
    const title = current.label || current.stage || current.title || "Current activity";
    const state = String(current.state || current.status || "success").toLowerCase();
    const statusLabel = state === "active" ? "In Progress" : (state === "future" ? "Waiting" : (state === "cancelled" ? "Cancelled" : (state === "failed" ? "Failed" : "Completed")));

    return `
        <div class="lifecycle-current-header-row">
            <div class="lifecycle-current-main">
                <div class="lifecycle-current-icon">${icon}</div>
                <div>
                    <div class="lifecycle-current-title">${escapeHtml(title)}</div>
                    <div class="lifecycle-current-meta">${escapeHtml(current.source_name || lifecycleSourceLabel(current.source_type))}</div>
                    <div class="lifecycle-current-state ${escapeHtml(state)}">${escapeHtml(statusLabel)}</div>
                </div>
            </div>
        </div>
        <div class="lifecycle-current-stat-list">
            ${current.details ? lifecycleCurrentStat("Details", current.details) : ""}
            ${current.activity_library_name ? lifecycleCurrentStat("Library", current.activity_library_name) : ""}
            ${mediaServerType ? lifecycleCurrentStat("Media Server", mediaServerType) : ""}
            ${current.created_at ? lifecycleCurrentStat("Updated", formatLifecycleTime(current.created_at)) : ""}
        </div>
    `;
}

function lifecycleCurrentStat(label, value) {
    if (!value) {
        return "";
    }

    return `
        <div class="lifecycle-current-stat">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>
    `;
}

function startLifecycleCurrentPolling() {
    stopLifecycleCurrentPolling();

    if (!LIFECYCLE_CURRENT_DATA) {
        return;
    }

    refreshLifecycleCurrentActivity();
    LIFECYCLE_CURRENT_POLL_TIMER = window.setInterval(refreshLifecycleCurrentActivity, 1000);
}

function stopLifecycleCurrentPolling() {
    if (!LIFECYCLE_CURRENT_POLL_TIMER) {
        return;
    }

    window.clearInterval(LIFECYCLE_CURRENT_POLL_TIMER);
    LIFECYCLE_CURRENT_POLL_TIMER = null;
}

async function refreshLifecycleCurrentActivity() {
    if (!LIFECYCLE_CURRENT_DATA) {
        stopLifecycleCurrentPolling();
        return;
    }

    let result;

    try {
        const response = await fetch("/api/downloaders/queue/all", { headers: { "Accept": "application/json" } });
        result = await response.json();
    } catch (error) {
        return;
    }

    const currentCard = document.querySelector("[data-lifecycle-current-card]");

    if (!currentCard) {
        stopLifecycleCurrentPolling();
        return;
    }

    const activeDownload = findLifecycleActiveDownload(result, LIFECYCLE_CURRENT_DATA.lifecycle, LIFECYCLE_CURRENT_DATA.tvOverview);

    if (LIFECYCLE_CURRENT_DATA.popupType === "tv") {
        try {
            const lifecycleId = LIFECYCLE_CURRENT_DATA.lifecycle?.id;

            if (lifecycleId) {
                const response = await fetch(`/api/lifecycle/${encodeURIComponent(lifecycleId)}`, {
                    headers: { "Accept": "application/json" },
                });
                const data = await response.json();

                if (response.ok && data.success) {
                    const lifecycle = data.lifecycle || LIFECYCLE_CURRENT_DATA.lifecycle;
                    const rawEvents = Array.isArray(data.events) ? data.events : [];
                    const mediaServer = data.media_server || LIFECYCLE_CURRENT_DATA.mediaServer || {};
                    const tvOverview = data.tv_overview || LIFECYCLE_CURRENT_DATA.tvOverview || null;
                    const visibleEvents = normalizeVisibleLifecycleEvents(rawEvents, lifecycle, mediaServer, tvOverview);

                    LIFECYCLE_CURRENT_DATA = {
                        lifecycle,
                        events: visibleEvents,
                        rawEvents,
                        mediaServer,
                        popupType: "tv",
                        tvOverview,
                    };

                    const timeline = document.querySelector("[data-lifecycle-timeline]");
                    if (timeline) {
                        timeline.innerHTML = renderLifecycleTimeline(visibleEvents, "tv");
                    }

                    updateLifecycleMetrics(rawEvents, lifecycle, mediaServer);

                    const leftPanel = document.querySelector(".lifecycle-detail-left");
                    if (leftPanel) {
                        const origin = lifecycleOriginInfo(lifecycle, rawEvents);
                        leftPanel.innerHTML = renderLifecycleMetadataPanel(lifecycle, tvOverview, "tv", origin.isRequestOrigin, origin);
                    }

                    const expandedSeasons = Array.from(document.querySelectorAll(".lifecycle-season-row.expanded"))
                        .map((row) => row.dataset.seasonNumber)
                        .filter(Boolean);

                    const seasonOverview = document.querySelector(".lifecycle-tv-overview");
                    if (seasonOverview) {
                        seasonOverview.outerHTML = renderTvSeasonOverview(tvOverview);

                        expandedSeasons.forEach((seasonNumber) => {
                            const row = document.querySelector(`.lifecycle-season-row[data-season-number="${cssEscape(String(seasonNumber))}"]`);
                            if (row) {
                                row.classList.add("expanded");
                            }
                        });
                    }
                }
            }
        } catch (error) {
            // Keep existing TV popup content if a live overview refresh fails.
        }

        const visibleTvEvents = enrichLifecycleEventsWithActiveDownload(
            LIFECYCLE_CURRENT_DATA.events,
            activeDownload,
        );

        const timeline = document.querySelector("[data-lifecycle-timeline]");
        if (timeline) {
            timeline.innerHTML = renderLifecycleTimeline(visibleTvEvents, LIFECYCLE_CURRENT_DATA.popupType);
        }

        currentCard.innerHTML = renderTvCurrentLifecycleActivity(
            visibleTvEvents,
            LIFECYCLE_CURRENT_DATA.mediaServer,
            LIFECYCLE_CURRENT_DATA.lifecycle,
            LIFECYCLE_CURRENT_DATA.tvOverview,
            activeDownload,
        );

        const availableStage = LIFECYCLE_CURRENT_DATA.events.find((stage) => stage.id === "available" && stage.state === "complete");

        if (!activeDownload && availableStage) {
            stopLifecycleCurrentPolling();
        }

        return;
    }

    try {
        const lifecycleId = LIFECYCLE_CURRENT_DATA.lifecycle?.id;

        if (lifecycleId) {
            const response = await fetch(`/api/lifecycle/${encodeURIComponent(lifecycleId)}`, {
                headers: { "Accept": "application/json" },
            });
            const data = await response.json();

            if (response.ok && data.success) {
                const lifecycle = data.lifecycle || LIFECYCLE_CURRENT_DATA.lifecycle;
                const rawEvents = Array.isArray(data.events) ? data.events : [];
                const mediaServer = data.media_server || LIFECYCLE_CURRENT_DATA.mediaServer || {};
                const visibleEvents = normalizeVisibleLifecycleEvents(rawEvents, lifecycle, mediaServer, null);

                if (activeDownload) {
                    const downloadStage = visibleEvents.find((stage) => stage && stage.id === "download");

                    if (downloadStage) {
                        downloadStage.state = "active";
                        downloadStage.label = "Downloading";
                        downloadStage.source_type = activeDownload.downloader_type || "downloader";
                        downloadStage.source_name = activeDownload.downloader_name || "Downloader";
                        downloadStage.event = activeDownload;
                    }
                }

                LIFECYCLE_CURRENT_DATA = {
                    lifecycle,
                    events: visibleEvents,
                    rawEvents,
                    mediaServer,
                    popupType: LIFECYCLE_CURRENT_DATA.popupType,
                    tvOverview: null,
                    displayTitle: LIFECYCLE_CURRENT_DATA.displayTitle || "",
                };

                const timeline = document.querySelector("[data-lifecycle-timeline]");
                if (timeline) {
                    timeline.innerHTML = renderLifecycleTimeline(visibleEvents, LIFECYCLE_CURRENT_DATA.popupType);
                }

                updateLifecycleMetrics(rawEvents, lifecycle, mediaServer);
            }
        }
    } catch (error) {
        // Keep current movie popup data if refresh fails.
    }

    if (activeDownload) {
        currentCard.innerHTML = renderDownloadingCurrentActivity(activeDownload);
        return;
    }

    currentCard.innerHTML = renderCurrentLifecycleActivity(
        LIFECYCLE_CURRENT_DATA.events,
        LIFECYCLE_CURRENT_DATA.mediaServer,
        LIFECYCLE_CURRENT_DATA.popupType,
        LIFECYCLE_CURRENT_DATA.lifecycle,
    );

    const terminalStage = LIFECYCLE_CURRENT_DATA.events.find((stage) =>
        (stage.id === "available" && stage.state === "complete") ||
        stage.state === "failed" ||
        stage.state === "cancelled"
    );

    if (terminalStage) {
        stopLifecycleCurrentPolling();
    }
}

function findLifecycleActiveDownload(result, lifecycle, tvOverview = null) {
    const queues = result && Array.isArray(result.queues) ? result.queues : [];
    const lookupTerms = new Set();

    const title = normalizeLookupText(lifecycle.title || "");
    if (title) {
        lookupTerms.add(title);
    }

    ((tvOverview || {}).seasons || []).forEach((season) => {
        (season.episodes || []).forEach((episode) => {
            if (episode.status !== "downloading") {
                return;
            }

            const code = normalizeLookupText(episode.episode_code || "");
            const episodeTitle = normalizeLookupText(episode.title || "");
            const combined = normalizeLookupText(`${lifecycle.title || ""} ${episode.episode_code || ""}`);

            if (code) {
                lookupTerms.add(code);
            }

            if (episodeTitle) {
                lookupTerms.add(episodeTitle);
            }

            if (combined) {
                lookupTerms.add(combined);
            }
        });
    });

    if (!lookupTerms.size) {
        return null;
    }

    for (const queue of queues) {
        const downloads = Array.isArray(queue.downloads) ? queue.downloads : [];

        for (const download of downloads) {
            const name = normalizeLookupText(download.name || download.filename || "");

            if (!name) {
                continue;
            }

            for (const term of lookupTerms) {
                if (!term) {
                    continue;
                }

                if (name.includes(term) || term.includes(name)) {
                    return {
                        ...download,
                        queue,
                        downloader_name: queue.downloader_name || queue.source || "Downloader",
                        downloader_type: queue.downloader_type || "downloader",
                        speed: queue.speed || "",
                        queue_timeleft: queue.timeleft || "",
                    };
                }
            }
        }
    }

    return null;
}

function renderDownloadingCurrentActivity(download) {
    const percent = Number(download.percent || 0);
    const safePercent = Math.max(0, Math.min(100, Math.round(percent)));
    const icon = lifecycleIconMarkup({ source_type: download.downloader_type || "downloader", source_name: download.downloader_name || "Downloader" });
    const downloaded = download.size && download.remaining ? `${download.remaining} left of ${download.size}` : (download.size || "");
    const itemName = download.name || download.filename || "Download";

    return `
        <div class="lifecycle-current-header-row downloading">
            <div class="lifecycle-current-progress-first">
                ${progressRingMarkup(safePercent)}
            </div>
            <div class="lifecycle-current-main centered">
                <div class="lifecycle-current-icon large">${icon}</div>
                <div>
                    <div class="lifecycle-current-title">Downloading</div>
                    <div class="lifecycle-current-meta">${escapeHtml(itemName)}</div>
                    <div class="lifecycle-current-state active">In Progress</div>
                </div>
            </div>
        </div>
        <div class="lifecycle-current-stat-list">
            ${lifecycleCurrentStat("Downloaded", downloaded || "—")}
            ${lifecycleCurrentStat("Download Rate", download.speed || "—")}
            ${lifecycleCurrentStat("ETA", download.eta || download.queue_timeleft || "—")}
            ${lifecycleCurrentStat("Category", download.category || "—")}
            ${lifecycleCurrentStat("Priority", download.priority || "—")}
            ${lifecycleCurrentStat("Path", download.filename || download.name || "—")}
        </div>
        <div class="lifecycle-current-note">This item is currently downloading. Progress will update automatically.</div>
    `;
}

function progressRingMarkup(percent, extraClass = "") {
    const degrees = Math.round((percent / 100) * 360);
    const className = ["lifecycle-progress-ring", extraClass].filter(Boolean).join(" ");

    return `
        <div class="${escapeHtml(className)}" style="--progress-deg:${degrees}deg">
            <div class="lifecycle-progress-ring-inner">${escapeHtml(String(percent))}%</div>
        </div>
    `;
}

function normalizeLookupText(value) {
    return String(value || "")
        .toLowerCase()
        .replace(/\(\d{4}\)/g, "")
        .replace(/[^a-z0-9]+/g, " ")
        .trim();
}

function renderTvSeasonOverview(tvOverview) {
    if (!tvOverview || !tvOverview.success) {
        return `
            <section class="lifecycle-tv-overview lifecycle-side-card wide">
                <div class="lifecycle-section-title">Season Overview</div>
                <div class="lifecycle-current-empty">${escapeHtml(tvOverview && tvOverview.message ? tvOverview.message : "Sonarr season data is not available yet.")}</div>
            </section>
        `;
    }

    const seasons = Array.isArray(tvOverview.seasons) ? tvOverview.seasons : [];

    if (!seasons.length) {
        return `
            <section class="lifecycle-tv-overview lifecycle-side-card wide">
                <div class="lifecycle-section-title">Season Overview</div>
                <div class="lifecycle-current-empty">No monitored seasons found in Sonarr.</div>
            </section>
        `;
    }

    return `
        <section class="lifecycle-tv-overview lifecycle-side-card wide">
            <div class="lifecycle-tv-overview-header">
                <div class="lifecycle-section-title">Season Overview</div>
                <span>Availability based on monitored episodes only</span>
            </div>
            <div class="lifecycle-tv-season-list">
                ${seasons.map(renderTvSeason).join("")}
            </div>
            <div class="lifecycle-tv-footnote">Seasons are ordered from newest to oldest.</div>
        </section>
    `;
}

function renderTvSeason(season) {
    const episodes = Array.isArray(season.episodes) ? season.episodes : [];
    const percent = Number(season.percent_available ?? season.progress ?? 0);
    const countLabel = season.count_label || `${season.available_count || 0} / ${season.total_count || 0} Episodes`;
    const statusLabel = season.status_label || (season.is_complete ? "Available" : "Scheduled");

    if (season.is_complete || !season.is_expandable) {
        return `
            <div class="lifecycle-tv-season-row complete ${escapeHtml(season.status || "available")}">
                <div class="lifecycle-tv-season-toggle-spacer"></div>
                <strong>${escapeHtml(season.label || `Season ${season.season_number}`)}</strong>
                <span class="lifecycle-tv-status-pill ${escapeHtml(season.status || "available")}">${escapeHtml(statusLabel)}</span>
                <div class="lifecycle-tv-season-progress">
                    <div class="lifecycle-tv-progress-bar"><span style="width:${escapeHtml(String(percent))}%"></span></div>
                </div>
                <span>${escapeHtml(countLabel)}</span>
                <span>${escapeHtml(String(percent))}% Available</span>
            </div>
        `;
    }

    const expanded = tvSeasonShouldOpen(season) ? " open" : "";

    return `
        <details class="lifecycle-tv-season-row-wrap" data-season-number="${escapeHtml(String(season.season_number || ""))}"${expanded}>
            <summary class="lifecycle-tv-season-row ${escapeHtml(season.status || "scheduled")}">
                <span class="lifecycle-tv-season-chevron">›</span>
                <strong>${escapeHtml(season.label || `Season ${season.season_number}`)}</strong>
                <span class="lifecycle-tv-status-pill ${escapeHtml(season.status || "scheduled")}">${escapeHtml(statusLabel)}</span>
                <div class="lifecycle-tv-season-progress">
                    <div class="lifecycle-tv-progress-bar"><span style="width:${escapeHtml(String(percent))}%"></span></div>
                </div>
                <span>${escapeHtml(countLabel)}</span>
                <span>${escapeHtml(String(percent))}% Available</span>
            </summary>
            <div class="lifecycle-tv-episode-table">
                ${episodes.map(renderTvEpisode).join("")}
            </div>
        </details>
    `;
}

function renderTvEpisode(episode) {
    const status = episode.status || "future";
    const symbol = status === "available" ? "✓" : (status === "downloading" ? "◉" : "○");

    return `
        <div class="lifecycle-tv-episode-row ${escapeHtml(status)}">
            <span class="lifecycle-tv-episode-indicator">${symbol}</span>
            <span>${escapeHtml(episode.episode_code || "")}</span>
            <strong>${escapeHtml(episode.title || "Episode")}</strong>
            <em>${escapeHtml(episode.status_label || "")}</em>
        </div>
    `;
}

function monitoredSeasonLabel(seasons) {
    if (!Array.isArray(seasons) || !seasons.length) {
        return "—";
    }

    if (seasons.length === 1) {
        return `Season ${seasons[0]} Requested`;
    }

    const sorted = seasons.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    const contiguous = sorted.every((value, index) => index === 0 || value === sorted[index - 1] + 1);

    if (contiguous) {
        return `Seasons ${sorted[0]}-${sorted[sorted.length - 1]} Requested`;
    }

    return `Seasons ${sorted.join(", ")} Requested`;
}

function lifecycleYear(title, createdAt) {
    const match = String(title || "").match(/\((\d{4})\)/);

    if (match) {
        return match[1];
    }

    if (createdAt) {
        return String(createdAt).slice(0, 4);
    }

    return "—";
}

function formatLifecycleTime(value) {
    if (!value) {
        return "—";
    }

    const raw = String(value).replace(" ", "T");
    const parsed = new Date(raw.endsWith("Z") ? raw : `${raw}Z`);

    if (Number.isNaN(parsed.getTime())) {
        return String(value);
    }

    return parsed.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function mediaServerLabel(serverType) {
    const labels = {
        emby: "Emby",
        jellyfin: "Jellyfin",
        plex: "Plex",
    };

    return labels[String(serverType || "").toLowerCase()] || "";
}

function lifecycleIconMarkup(eventOrSourceType, sourceName) {
    const event = typeof eventOrSourceType === "object" && eventOrSourceType !== null
        ? eventOrSourceType
        : { source_type: eventOrSourceType, source_name: sourceName };

    const file = lifecycleIconFile(event);
    const label = event.source_name || lifecycleSourceLabel(event.source_type);

    if (!file) {
        return `<span>${escapeHtml(lifecycleFallbackIcon(event.source_type))}</span>`;
    }

    return `<img src="${escapeHtml(file)}" alt="${escapeHtml(label)}" onerror="this.style.display='none'; this.parentElement.textContent='${escapeHtml(lifecycleFallbackIcon(event.source_type))}';">`;
}

function lifecycleIconFile(event) {
    const normalizedType = String(event.source_type || "").toLowerCase();
    const normalizedName = String(event.source_name || "").toLowerCase();

    if (normalizedType === "mediasync" && event.activity_library_image_url) {
        return event.activity_library_image_url;
    }

    if (normalizedType === "sabnzbd" || normalizedName.includes("sab")) {
        return "/static/img/sab-logo.png";
    }

    if (normalizedType === "qbittorrent" || normalizedName.includes("qbittorrent") || normalizedName.includes("qbit")) {
        return "/static/img/qbittorrent-logo.png";
    }

    if (normalizedType === "transmission" || normalizedName.includes("transmission")) {
        return "/static/img/transmission-logo.png";
    }

    if (normalizedType === "radarr" || normalizedName.includes("radarr")) {
        return "/static/img/radarr-logo.png";
    }

    if (normalizedType === "sonarr" || normalizedName.includes("sonarr")) {
        return "/static/img/sonarr-logo.png";
    }

    if (normalizedType === "seerr" || normalizedName.includes("seerr")) {
        return "/static/img/seerr-logo.png";
    }

    if (normalizedType === "emby") {
        return "/static/img/emby-logo.png";
    }

    if (normalizedType === "jellyfin") {
        return "/static/img/jellyfin-logo.png";
    }

    if (normalizedType === "plex") {
        return "/static/img/plex-logo.png";
    }

    if (normalizedType === "mediasync") {
        return "/static/img/default.png";
    }

    return "/static/img/default.png";
}

function lifecycleSourceLabel(sourceType) {
    const labels = {
        seerr: "Seerr",
        radarr: "Radarr",
        sonarr: "Sonarr",
        sabnzbd: "SABnzbd",
        qbittorrent: "qBittorrent",
        transmission: "Transmission",
        emby: "Emby",
        jellyfin: "Jellyfin",
        plex: "Plex",
        mediasync: "MediaSync",
    };

    return labels[String(sourceType || "").toLowerCase()] || "MediaSync";
}

function lifecycleFallbackIcon(sourceType) {
    const normalized = String(sourceType || "").toLowerCase();

    if (normalized === "sabnzbd") {
        return "⇩";
    }

    if (normalized === "radarr" || normalized === "sonarr") {
        return "⚙";
    }

    if (normalized === "emby" || normalized === "jellyfin" || normalized === "plex") {
        return "▶";
    }

    if (normalized === "seerr") {
        return "★";
    }

    return "✓";
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
