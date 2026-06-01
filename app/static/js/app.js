document.addEventListener("DOMContentLoaded", () => {
    initMediaServerSetup();
    initSourcesSetup();
});

function initMediaServerSetup() {
    const form = document.getElementById("server-test-form");

    if (!form) {
        return;
    }

    const resultBox = document.getElementById("server-test-result");
    const statusPill = document.getElementById("server-status-pill");
    const button = document.getElementById("server-test-button");
    const libraryResults = document.getElementById("library-results");
    const nextButton = document.getElementById("next-sources-button");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        resultBox.className = "result-box neutral";
        resultBox.textContent = "Testing connection...";

        libraryResults.className = "library-results hidden";
        libraryResults.innerHTML = "";

        nextButton.className = "primary-button secondary-action hidden";

        statusPill.className = "status-pill neutral";
        statusPill.textContent = "Testing";

        button.disabled = true;
        button.textContent = "Testing...";

        try {
            const formData = new FormData(form);

            const response = await fetch("/api/server/test", {
                method: "POST",
                body: formData,
            });

            const data = await response.json();

            if (data.success) {
                resultBox.className = "result-box good";
                resultBox.textContent =
                    `${data.message} Connected to ${data.server_name} running Emby ${data.version}.`;

                statusPill.className = "status-pill good";
                statusPill.textContent = "Connected";

                renderDetectedLibraries(
                    libraryResults,
                    data.libraries || [],
                    data.library_count || 0,
                );

                nextButton.className = "primary-button secondary-action";
            } else {
                resultBox.className = "result-box warning";
                resultBox.textContent = data.message;

                statusPill.className = "status-pill warning";
                statusPill.textContent = "Not Connected";
            }
        } catch (error) {
            resultBox.className = "result-box warning";
            resultBox.textContent =
                "Connection test failed. Check the server URL and try again.";

            statusPill.className = "status-pill warning";
            statusPill.textContent = "Not Connected";
        } finally {
            button.disabled = false;
            button.textContent = "Test Connection";
        }
    });
}

function initSourcesSetup() {
    const addSourceButton = document.getElementById("add-source-button");
    const sourceCardList = document.getElementById("source-card-list");

    if (!addSourceButton || !sourceCardList) {
        return;
    }

    let sourceCounter = 0;

    const savedSources = getSavedSources();

    savedSources.forEach((source) => {
        sourceCounter++;
        const card = createSourceCard(sourceCounter);
        sourceCardList.appendChild(card);
        wireSourceCard(card);
        hydrateSavedSourceCard(card, source);
    });

    renumberSourceCards();

    addSourceButton.addEventListener("click", () => {
        sourceCounter++;

        const card = createSourceCard(sourceCounter);
        sourceCardList.appendChild(card);
        wireSourceCard(card);
        renumberSourceCards();
    });
}

function getSavedSources() {
    const dataElement = document.getElementById("saved-sources-data");

    if (!dataElement) {
        return [];
    }

    try {
        return JSON.parse(dataElement.textContent || "[]");
    } catch (error) {
        return [];
    }
}

function createSourceCard(sourceNumber) {
    const card = document.createElement("div");
    card.className = "source-card";
    card.dataset.sourceId = "";

    card.innerHTML = `
        <div class="source-card-header">
            <h3>Source ${sourceNumber}</h3>

            <button
                type="button"
                class="danger-button remove-source-button"
            >
                − Remove
            </button>
        </div>

        <div class="form-grid">

            <label>
                <span>Source Name</span>

                <input
                    class="source-name-input"
                    type="text"
                    placeholder="Radarr"
                >
            </label>

            <label>
                <span>Source Type</span>

                <select class="source-type-input">
                    <option value="radarr">Radarr</option>
                    <option value="sonarr">Sonarr</option>
                </select>
            </label>

            <label>
                <span>Server URL</span>

                <input
                    class="source-url-input"
                    type="text"
                    placeholder="http://radarr:7878"
                >
            </label>

            <label>
                <span>API Key</span>

                <input
                    class="source-api-key-input"
                    type="password"
                    placeholder="Enter API Key"
                >
            </label>

        </div>

        <div class="source-actions">

            <button
                type="button"
                class="primary-button source-test-button"
            >
                Test Connection
            </button>

            <button
                type="button"
                class="primary-button secondary-action source-save-button"
                disabled
            >
                Save Source
            </button>

        </div>

        <div class="source-result-box result-box hidden"></div>

        <div class="source-library-results source-placeholder">
            Compatible libraries will appear after a successful connection test.
        </div>
    `;

    return card;
}

function hydrateSavedSourceCard(card, source) {
    const nameInput = card.querySelector(".source-name-input");
    const typeInput = card.querySelector(".source-type-input");
    const urlInput = card.querySelector(".source-url-input");
    const apiKeyInput = card.querySelector(".source-api-key-input");
    const saveButton = card.querySelector(".source-save-button");
    const resultBox = card.querySelector(".source-result-box");
    const libraryResults = card.querySelector(".source-library-results");

    card.dataset.sourceId = source.id || "";
    card.dataset.connectionValid = "true";
    card.dataset.testedVersion = source.version || "Unknown";

    nameInput.value = source.source_name || "";
    typeInput.value = source.source_type || "radarr";
    urlInput.value = source.source_url || "";
    apiKeyInput.value = source.api_key || "";

    resultBox.className = "source-result-box result-box good";
    resultBox.textContent =
        `${formatSourceName(source.source_type)} saved and connected.`;

    renderSavedLibraries(libraryResults, source.libraries || []);

    saveButton.textContent = "Saved ✓";
    saveButton.disabled = true;
}

function wireSourceCard(card) {
    const removeButton = card.querySelector(".remove-source-button");
    const testButton = card.querySelector(".source-test-button");
    const saveButton = card.querySelector(".source-save-button");
    const resultBox = card.querySelector(".source-result-box");
    const libraryResults = card.querySelector(".source-library-results");

    card.dataset.connectionValid = card.dataset.connectionValid || "false";
    card.dataset.testedVersion = card.dataset.testedVersion || "";

    removeButton.addEventListener("click", async () => {
        const sourceId = card.dataset.sourceId;

        if (sourceId) {
            await deleteSavedSource(sourceId);
        }

        card.remove();
        renumberSourceCards();
    });

    testButton.addEventListener("click", async () => {
        const sourceType = card.querySelector(".source-type-input").value;
        const sourceUrl = card.querySelector(".source-url-input").value.trim();
        const apiKey = card.querySelector(".source-api-key-input").value.trim();

        card.dataset.connectionValid = "false";
        card.dataset.testedVersion = "";

        saveButton.disabled = true;
        saveButton.textContent = "Save Source";

        libraryResults.className = "source-library-results source-placeholder";
        libraryResults.textContent =
            "Compatible libraries will appear after a successful connection test.";

        if (!sourceUrl || !apiKey) {
            resultBox.className = "source-result-box result-box warning";
            resultBox.textContent = "Enter a server URL and API key first.";
            return;
        }

        const selectedLibraryIds = getSelectedLibraryIds(card);

        resultBox.className = "source-result-box result-box neutral";
        resultBox.textContent = "Testing connection...";

        testButton.disabled = true;
        testButton.textContent = "Testing...";

        try {
            const formData = new FormData();

            formData.append("source_type", sourceType);
            formData.append("source_url", sourceUrl);
            formData.append("api_key", apiKey);

            const response = await fetch("/api/source/test", {
                method: "POST",
                body: formData,
            });

            const data = await response.json();

            if (data.success) {
                card.dataset.connectionValid = "true";
                card.dataset.testedVersion = data.version || "Unknown";

                resultBox.className = "source-result-box result-box good";
                resultBox.textContent =
                    `${data.message} Connected to ${data.app_name} ${data.version}.`;

                renderCompatibleLibraries(
                    libraryResults,
                    data.compatible_libraries || [],
                    selectedLibraryIds,
                );

                updateSourceSaveState(card);
            } else {
                resultBox.className = "source-result-box result-box warning";
                resultBox.textContent = data.message;
            }
        } catch (error) {
            resultBox.className = "source-result-box result-box warning";
            resultBox.textContent =
                "Connection test failed. Check the server URL and try again.";
        } finally {
            testButton.disabled = false;
            testButton.textContent = "Test Connection";
        }
    });

    card.addEventListener("change", (event) => {
        saveButton.textContent = "Save Source";

        if (event.target.classList.contains("source-type-input")) {
            card.dataset.connectionValid = "false";
            card.dataset.testedVersion = "";
            saveButton.disabled = true;

            resultBox.className = "source-result-box result-box hidden";
            resultBox.textContent = "";

            libraryResults.className = "source-library-results source-placeholder";
            libraryResults.textContent =
                "Compatible libraries will appear after a successful connection test.";
            return;
        }

        updateSourceSaveState(card);
    });

    card.addEventListener("input", () => {
        if (card.dataset.connectionValid === "true") {
            saveButton.textContent = "Save Source";
            updateSourceSaveState(card);
        }
    });

    saveButton.addEventListener("click", async () => {
        if (card.dataset.connectionValid !== "true") {
            return;
        }

        const sourceName =
            card.querySelector(".source-name-input").value.trim();

        const sourceType =
            card.querySelector(".source-type-input").value;

        const sourceUrl =
            card.querySelector(".source-url-input").value.trim();

        const apiKey =
            card.querySelector(".source-api-key-input").value.trim();

        const checkedLibraries = Array.from(
            card.querySelectorAll(".source-library-checkbox:checked"),
        );

        const libraryIds = checkedLibraries.map((checkbox) => checkbox.value);

        const libraryNames = checkedLibraries.map((checkbox) =>
            checkbox
                .closest(".source-library-option")
                .querySelector(".library-name")
                .textContent.trim(),
        );

        saveButton.disabled = true;
        saveButton.textContent = "Saving...";

        try {
            const formData = new FormData();

            formData.append("source_id", card.dataset.sourceId || "");
            formData.append("source_name", sourceName || sourceType);
            formData.append("source_type", sourceType);
            formData.append("source_url", sourceUrl);
            formData.append("api_key", apiKey);
            formData.append(
                "version",
                card.dataset.testedVersion || "Unknown",
            );
            formData.append("library_ids", libraryIds.join(","));
            formData.append("library_names", libraryNames.join(","));

            const response = await fetch("/api/source/save", {
                method: "POST",
                body: formData,
            });

            const data = await response.json();

            if (data.success) {
                card.dataset.sourceId = data.source_id;

                resultBox.className = "source-result-box result-box good";
                resultBox.textContent = data.message;

                saveButton.textContent = "Saved ✓";
                saveButton.disabled = true;
            } else {
                resultBox.className = "source-result-box result-box warning";
                resultBox.textContent = data.message;

                saveButton.textContent = "Save Source";
                updateSourceSaveState(card);
            }
        } catch (error) {
            resultBox.className = "source-result-box result-box warning";
            resultBox.textContent = "Save failed.";

            saveButton.textContent = "Save Source";
            updateSourceSaveState(card);
        }
    });
}

async function deleteSavedSource(sourceId) {
    const formData = new FormData();

    formData.append("source_id", sourceId);

    try {
        await fetch("/api/source/delete", {
            method: "POST",
            body: formData,
        });
    } catch (error) {
        return;
    }
}

function renumberSourceCards() {
    const cards = document.querySelectorAll(".source-card");

    cards.forEach((card, index) => {
        const title = card.querySelector(".source-card-header h3");

        if (title) {
            title.textContent = `Source ${index + 1}`;
        }
    });
}

function renderDetectedLibraries(container, libraries, libraryCount) {
    if (!container) {
        return;
    }

    if (!libraries.length) {
        container.className = "library-results warning";
        container.innerHTML = `
            <div class="library-results-header">
                <h3>Detected Libraries</h3>
                <p>No libraries were returned by Emby.</p>
            </div>
        `;
        return;
    }

    const libraryCards = libraries
        .map((library) => {
            return `
                <div class="library-card">
                    ${libraryImageMarkup(library)}

                    <div>
                        <div class="library-name">
                            ${escapeHtml(library.name)}
                        </div>

                        <div class="library-type">
                            ${escapeHtml(formatLibraryType(library.type))}
                        </div>
                    </div>
                </div>
            `;
        })
        .join("");

    container.className = "library-results";
    container.innerHTML = `
        <div class="library-results-header">
            <div>
                <h3>Detected Libraries</h3>
                <p>${libraryCount} libraries detected from Emby.</p>
            </div>
        </div>

        <div class="library-grid">
            ${libraryCards}
        </div>
    `;
}

function getSelectedLibraryIds(card) {
    return Array.from(
        card.querySelectorAll(".source-library-checkbox:checked"),
    ).map((checkbox) => checkbox.value);
}

function renderCompatibleLibraries(container, libraries, selectedLibraryIds = []) {
    if (!libraries.length) {
        container.className = "source-library-results source-placeholder warning";
        container.textContent = "No compatible libraries were found.";
        return;
    }

    const cards = libraries
        .map((library) => {
            return `
                <label class="source-library-option">
                    <input
                        type="checkbox"
                        class="source-library-checkbox"
                        value="${escapeHtml(library.id)}"
                        ${selectedLibraryIds.includes(String(library.id)) ? "checked" : ""}
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

function renderSavedLibraries(container, libraries) {
    if (!libraries.length) {
        container.className = "source-library-results source-placeholder";
        container.textContent = "No libraries mapped.";
        return;
    }

    const cards = libraries
        .map((library) => {
            return `
                <label class="source-library-option saved">
                    <input
                        type="checkbox"
                        class="source-library-checkbox"
                        value="${escapeHtml(library.library_id)}"
                        checked
                    >

                    ${libraryImageMarkup({
                        id: library.library_id,
                        name: library.library_name,
                        type: library.library_type || library.type,
                        image_url: library.library_image_url || library.image_url,
                    })}

                    <div>
                        <div class="library-name">
                            ${escapeHtml(library.library_name)}
                        </div>

                        <div class="library-type">
                            Mapped Library
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
                <h3>Mapped Libraries</h3>
                <p>This source will sync these libraries.</p>
            </div>
        </div>

        <div class="library-grid">
            ${cards}
        </div>
    `;
}

function updateSourceSaveState(card) {
    const saveButton = card.querySelector(".source-save-button");
    const checkedLibraries = card.querySelectorAll(
        ".source-library-checkbox:checked",
    );

    saveButton.disabled =
        card.dataset.connectionValid !== "true" ||
        checkedLibraries.length === 0;
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
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
