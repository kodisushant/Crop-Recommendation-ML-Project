/**
 * Crop Advisor - Frontend Client Logic
 * 
 * Clean, standard, and explainable JavaScript architecture.
 * Communicates with the FastAPI backend endpoints using native fetch().
 * Renders interactive visual analytics using Chart.js.
 */

// ============================================================================
// 1. GLOBAL CONSTANTS & METADATA
// ============================================================================

/**
 * Metadata and validation limits for the 7 agricultural input features.
 * Matches the dataset features expected by the trained Scikit-Learn models.
 */
const FIELD_DEFINITIONS = {
    N: {
        label: "Nitrogen (N)",
        unit: "dataset units",
        min: 0,
        max: 300,
        defaultValue: 90,
        icon: "fa-flask",
        description: "Soil nitrogen content",
        group: "Soil Nutrients",
        step: 1
    },
    P: {
        label: "Phosphorus (P)",
        unit: "dataset units",
        min: 0,
        max: 300,
        defaultValue: 42,
        icon: "fa-flask",
        description: "Soil phosphorus content",
        group: "Soil Nutrients",
        step: 1
    },
    K: {
        label: "Potassium (K)",
        unit: "dataset units",
        min: 0,
        max: 400,
        defaultValue: 43,
        icon: "fa-flask",
        description: "Soil potassium content",
        group: "Soil Nutrients",
        step: 1
    },
    ph: {
        label: "Soil pH",
        unit: "0–14",
        min: 0,
        max: 14,
        defaultValue: 6.5,
        icon: "fa-droplet",
        description: "Acidity (7 = neutral)",
        group: "Soil Properties",
        step: 0.1
    },
    temperature: {
        label: "Temperature",
        unit: "°C",
        min: -5,
        max: 55,
        defaultValue: 20.9,
        icon: "fa-temperature-half",
        description: "Average temperature",
        group: "Weather Conditions",
        step: 0.1
    },
    humidity: {
        label: "Humidity",
        unit: "%",
        min: 0,
        max: 100,
        defaultValue: 82,
        icon: "fa-cloud",
        description: "Relative humidity",
        group: "Weather Conditions",
        step: 0.1
    },
    rainfall: {
        label: "Rainfall",
        unit: "mm",
        min: 0,
        max: 1000,
        defaultValue: 203,
        icon: "fa-cloud-rain",
        description: "Rainfall",
        group: "Weather Conditions",
        step: 0.1
    }
};

/** Palette for charts and graphical elements */
const CHART_COLORS = [
    "#174D32", "#4C956C", "#9BC53D", "#DCECCB",
    "#B7791F", "#5B8E7D", "#8A9A5B", "#C9A227"
];

/** Active Chart.js instances registry to allow clean updates and avoid memory leaks */
const activeChartInstances = {};

/** In-memory cache for crops list to reduce redundant network calls */
let cachedCropsList = null;


// ============================================================================
// 2. UTILITY & HELPER FUNCTIONS
// ============================================================================

/** Shortcut to select a single DOM element */
function getElement(selector, root = document) {
    return root.querySelector(selector);
}

/** Shortcut to select multiple DOM elements as an Array */
function getAllElements(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
}

/** Capitalizes the first letter of a string (e.g. 'rice' -> 'Rice') */
function capitalizeFirstLetter(str) {
    if (!str) return "";
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/** Safely escapes HTML special characters to prevent XSS and rendering errors */
function escapeHtml(text) {
    return String(text ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

/** Formats a numeric value with a fallback string when null or undefined */
function formatValue(value, fallback = "–") {
    return value === null || value === undefined ? fallback : value;
}

/** Formats a numeric value into Indian Rupee currency string (e.g. ₹2,369) */
function formatRupees(amount) {
    if (isNaN(amount) || amount === null) return "₹0";
    return "₹" + Math.round(amount).toLocaleString("en-IN");
}

/**
 * Creates and displays a floating toast notification
 * @param {string} message - Notification text
 * @param {string} type - 'ok' or 'error'
 */
function showToast(message, type = "ok") {
    const toastContainer = getElement("#toasts");
    if (!toastContainer) return;

    const toastElement = document.createElement("div");
    toastElement.className = "toast " + (type === "error" ? "error" : "");
    toastElement.setAttribute("role", "status");
    toastElement.textContent = message;

    toastContainer.appendChild(toastElement);

    setTimeout(() => {
        toastElement.remove();
    }, 4200);
}

/**
 * Sends HTTP requests to the FastAPI backend and parses the JSON response
 * @param {string} url - API endpoint path (e.g. '/predict')
 * @param {object|null} requestBody - Optional request payload for POST requests
 * @returns {Promise<object>} Parsed JSON response
 */
async function fetchApi(url, requestBody = null) {
    let response;
    try {
        const fetchOptions = requestBody ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody)
        } : undefined;

        response = await fetch(url, fetchOptions);
    } catch (networkError) {
        throw new Error("Cannot reach the server. Please check your network connection.");
    }

    const jsonResponse = await response.json().catch(() => ({}));

    if (!response.ok) {
        let errorMessage = jsonResponse.detail;
        if (Array.isArray(errorMessage)) {
            // Unpack Pydantic field validation error messages
            errorMessage = errorMessage
                .map(err => `${(err.loc || []).slice(-1)[0]}: ${err.msg}`)
                .join("; ");
        }
        throw new Error(errorMessage || `Request failed with status ${response.status}`);
    }

    return jsonResponse;
}

/**
 * Renders or updates a responsive Chart.js chart on a <canvas> element
 * @param {string} canvasId - Canvas DOM element ID
 * @param {object} chartConfig - Chart.js configuration object
 */
function renderChart(canvasId, chartConfig) {
    const canvasElement = document.getElementById(canvasId);
    if (!canvasElement) return;

    // Destroy existing instance to prevent overlapping canvases
    if (activeChartInstances[canvasId]) {
        activeChartInstances[canvasId].destroy();
    }

    // Ensure responsive layout
    chartConfig.options = Object.assign(
        { responsive: true, maintainAspectRatio: false },
        chartConfig.options || {}
    );

    activeChartInstances[canvasId] = new Chart(canvasElement, chartConfig);
}

/**
 * Wraps an async form submission action with loading spinner state on the button
 * @param {HTMLButtonElement} submitButton - Submit button element
 * @param {Function} asyncAction - Async function to run
 */
async function executeWithLoadingState(submitButton, asyncAction) {
    if (!submitButton) {
        await asyncAction();
        return;
    }

    submitButton.classList.add("loading");
    submitButton.disabled = true;

    try {
        await asyncAction();
    } catch (error) {
        showToast(error.message, "error");
        const resultContainer = getElement("#result");
        if (resultContainer) {
            resultContainer.innerHTML = `
                <div class="alert bad">
                    <b>Something went wrong:</b> ${error.message}
                </div>
            `;
        }
    } finally {
        submitButton.classList.remove("loading");
        submitButton.disabled = false;
    }
}

/**
 * Generates an HTML badge element
 * @param {string} status - Badge status key ('ok', 'low', 'out', 'ideal', etc.)
 * @param {string} text - Display text
 */
function renderBadge(status, text = null) {
    const normalizedStatus = String(status).toLowerCase();
    const displayText = text || String(status).replace("_", " ");
    return `<span class="badge b-${normalizedStatus}">${displayText}</span>`;
}

/**
 * Returns an empty placeholder view with an icon
 */
function renderEmptyPlaceholder(iconClass, messageText) {
    return `<div class="empty"><i class="fa-solid ${iconClass}"></i>${messageText}</div>`;
}

/**
 * Retrieves the last-used input values saved in browser localStorage
 */
function getLastSavedFormValues() {
    try {
        return JSON.parse(localStorage.getItem("ca_last")) || {};
    } catch {
        return {};
    }
}

/**
 * Persists the latest user input values into browser localStorage
 */
function saveFormValues(values) {
    try {
        const mergedValues = { ...getLastSavedFormValues(), ...values };
        localStorage.setItem("ca_last", JSON.stringify(mergedValues));
    } catch (e) {
        console.warn("Could not save to localStorage", e);
    }
}


// ============================================================================
// 3. SHARED DATA LOADERS & FORM READERS
// ============================================================================

/**
 * Fetches and caches the list of crops from the backend (/crops)
 */
async function getCropsList() {
    if (!cachedCropsList) {
        cachedCropsList = await fetchApi("/crops");
    }
    return cachedCropsList;
}

/**
 * Populates a <select> element with all crops dynamically (no hardcoding)
 * @param {HTMLSelectElement} selectElement - Target dropdown element
 * @param {boolean} includeBlankOption - Whether to prefix with "Select crop..."
 */
async function populateCropDropdown(selectElement, includeBlankOption = false) {
    if (!selectElement) return;
    const crops = await getCropsList();

    const optionsHtml = crops.map(item => {
        return `<option value="${item.crop}">${capitalizeFirstLetter(item.crop)}</option>`;
    }).join("");

    selectElement.innerHTML = (includeBlankOption ? `<option value="">Select crop…</option>` : "") + optionsHtml;
}

/**
 * Populates a <select> element with Indian States dynamically from /states
 * @param {HTMLSelectElement} selectElement - Target dropdown element
 */
async function populateStateDropdown(selectElement, blankLabel = "All India") {
    if (!selectElement) return;
    let statesList = [];

    try {
        const response = await fetchApi("/states");
        statesList = response.states || [];
    } catch (error) {
        showToast("Could not load states list", "error");
    }

    const optionsHtml = statesList.map(stateName => `<option>${stateName}</option>`).join("");
    selectElement.innerHTML = `<option value="">${blankLabel}</option>` + optionsHtml;
}

/**
 * Reads and validates numeric input values from the form fields
 * @param {Array<string>} featureKeys - Array of feature keys ('N', 'P', 'K', etc.)
 * @param {string} prefix - Field ID prefix (defaults to 'f-')
 * @returns {object} Dictionary of validated numeric values
 */
function readFormFeatures(featureKeys, prefix = "f-") {
    const extractedValues = {};
    let hasValidationErrors = false;

    featureKeys.forEach(key => {
        const inputElement = getElement("#" + prefix + key);
        const errorElement = getElement("#e-" + prefix + key);
        const definition = FIELD_DEFINITIONS[key];

        if (!inputElement) return;

        const numericValue = parseFloat(inputElement.value);
        const isOutOfRange = isNaN(numericValue) || numericValue < definition.min || numericValue > definition.max;

        inputElement.classList.toggle("bad", isOutOfRange);

        if (errorElement) {
            errorElement.textContent = isOutOfRange ? `Enter between ${definition.min} and ${definition.max}` : "";
        }

        if (isOutOfRange) {
            hasValidationErrors = true;
        }

        extractedValues[key] = numericValue;
    });

    if (hasValidationErrors) {
        throw new Error("Please correct the highlighted fields with valid ranges.");
    }

    // Persist for convenience
    saveFormValues(extractedValues);
    return extractedValues;
}

/**
 * Populates existing HTML inputs with previously saved or default values
 */
function restoreFieldInputs(featureKeys, prefix = "f-") {
    const saved = getLastSavedFormValues();
    featureKeys.forEach(key => {
        const inputElement = getElement("#" + prefix + key);
        if (inputElement && saved[key] !== undefined) {
            inputElement.value = saved[key];
        }
    });
}

/**
 * Sets up State and District auto-suggestions on input elements.
 * Simple, beginner-friendly helper reusable across Recommendation and Land Check pages.
 */
function setupLocationAutocomplete({ stateInput, stateSuggestions, districtInput, districtSuggestions }) {
    let allStates = [];
    let currentDistricts = [];
    let activeStateIndex = -1;
    let activeDistrictIndex = -1;

    function hideStateSuggestions() {
        if (!stateSuggestions) return;
        stateSuggestions.hidden = true;
        stateSuggestions.innerHTML = "";
        activeStateIndex = -1;
        stateInput?.setAttribute("aria-expanded", "false");
    }

    function hideDistrictSuggestions() {
        if (!districtSuggestions) return;
        districtSuggestions.hidden = true;
        districtSuggestions.innerHTML = "";
        activeDistrictIndex = -1;
        districtInput?.setAttribute("aria-expanded", "false");
    }

    async function loadDistricts(stateName) {
        if (!stateName) {
            currentDistricts = [];
            return [];
        }
        try {
            currentDistricts = await fetchApi(`/districts?state=${encodeURIComponent(stateName)}`);
            return currentDistricts;
        } catch {
            currentDistricts = [];
            return [];
        }
    }

    function renderStates(list) {
        if (!stateSuggestions) return;
        activeStateIndex = -1;
        if (!list.length) {
            hideStateSuggestions();
            return;
        }
        stateSuggestions.innerHTML = list.map((st, idx) => `
            <li class="ac-item" role="option" data-value="${escapeHtml(st)}" data-index="${idx}">
                <i class="fa-solid fa-location-dot" style="color:var(--fresh);margin-right:6px"></i>${escapeHtml(st)}
            </li>
        `).join("");
        stateSuggestions.hidden = false;
        stateInput?.setAttribute("aria-expanded", "true");
    }

    function renderDistricts(list) {
        if (!districtSuggestions) return;
        activeDistrictIndex = -1;
        if (!list.length) {
            hideDistrictSuggestions();
            return;
        }
        districtSuggestions.innerHTML = list.map((dst, idx) => `
            <li class="ac-item" role="option" data-value="${escapeHtml(dst)}" data-index="${idx}">
                <i class="fa-solid fa-map-pin" style="color:var(--forest);margin-right:6px"></i>${escapeHtml(dst)}
            </li>
        `).join("");
        districtSuggestions.hidden = false;
        districtInput?.setAttribute("aria-expanded", "true");
    }

    async function selectState(st) {
        if (!st) return;
        if (stateInput) stateInput.value = st;
        hideStateSuggestions();
        if (districtInput) {
            districtInput.value = "";
            districtInput.placeholder = `Loading districts for ${st}…`;
        }
        showToast(`Loading districts for ${st}…`);
        const dists = await loadDistricts(st);
        if (districtInput) {
            districtInput.placeholder = `Type or click to search District (e.g. Hyderabad)`;
            districtInput.focus();
            renderDistricts(dists.slice(0, 15));
        }
    }

    function selectDistrict(dst) {
        if (!dst || dst === "none") return;
        if (districtInput) districtInput.value = dst;
        hideDistrictSuggestions();
    }

    // State input events
    if (stateInput && stateSuggestions) {
        const filterAndShowStates = async () => {
            if (!allStates.length) {
                try {
                    const resp = await fetchApi("/states");
                    allStates = resp.states || [];
                } catch {
                    allStates = [];
                }
            }
            const query = (stateInput.value || "").trim().toLowerCase();
            const filtered = query
                ? allStates.filter(s => s.toLowerCase().includes(query))
                : allStates;
            renderStates(filtered.slice(0, 10));
        };

        stateInput.addEventListener("input", filterAndShowStates);
        stateInput.addEventListener("focus", filterAndShowStates);
        stateInput.addEventListener("click", filterAndShowStates);

        stateSuggestions.addEventListener("mousedown", event => {
            const item = event.target.closest(".ac-item");
            if (!item) return;
            event.preventDefault();
            const val = item.dataset.value;
            if (val) selectState(val);
        });

        stateInput.addEventListener("keydown", event => {
            if (stateSuggestions.hidden) return;
            const items = getAllElements(".ac-item", stateSuggestions);
            if (!items.length) return;
            if (event.key === "ArrowDown") {
                event.preventDefault();
                activeStateIndex = (activeStateIndex + 1) % items.length;
                items.forEach((el, i) => el.classList.toggle("active", i === activeStateIndex));
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                activeStateIndex = (activeStateIndex - 1 + items.length) % items.length;
                items.forEach((el, i) => el.classList.toggle("active", i === activeStateIndex));
            } else if (event.key === "Enter" && activeStateIndex >= 0) {
                event.preventDefault();
                const val = items[activeStateIndex].dataset.value;
                if (val) selectState(val);
            } else if (event.key === "Escape") {
                hideStateSuggestions();
            }
        });
    }

    // District input events
    if (districtInput && districtSuggestions) {
        const filterAndShowDistricts = async () => {
            const st = (stateInput?.value || "").trim();
            if (!st) {
                districtSuggestions.innerHTML = `<li class="ac-item" data-value="none" style="color:var(--muted);cursor:default">Please select a State / UT first</li>`;
                districtSuggestions.hidden = false;
                districtInput?.setAttribute("aria-expanded", "true");
                return;
            }
            if (!currentDistricts.length) {
                districtSuggestions.innerHTML = `<li class="ac-item" data-value="none" style="color:var(--muted);cursor:default">Loading districts…</li>`;
                districtSuggestions.hidden = false;
                await loadDistricts(st);
            }
            const query = (districtInput.value || "").trim().toLowerCase();
            const filtered = query
                ? currentDistricts.filter(d => d.toLowerCase().includes(query))
                : currentDistricts;
            renderDistricts(filtered.slice(0, 15));
        };

        districtInput.addEventListener("input", filterAndShowDistricts);
        districtInput.addEventListener("focus", filterAndShowDistricts);
        districtInput.addEventListener("click", filterAndShowDistricts);

        districtSuggestions.addEventListener("mousedown", event => {
            const item = event.target.closest(".ac-item");
            if (!item) return;
            event.preventDefault();
            const val = item.dataset.value;
            if (val && val !== "none") selectDistrict(val);
        });

        districtInput.addEventListener("keydown", event => {
            if (districtSuggestions.hidden) return;
            const items = getAllElements(".ac-item", districtSuggestions);
            if (!items.length) return;
            if (event.key === "ArrowDown") {
                event.preventDefault();
                activeDistrictIndex = (activeDistrictIndex + 1) % items.length;
                items.forEach((el, i) => el.classList.toggle("active", i === activeDistrictIndex));
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                activeDistrictIndex = (activeDistrictIndex - 1 + items.length) % items.length;
                items.forEach((el, i) => el.classList.toggle("active", i === activeDistrictIndex));
            } else if (event.key === "Enter" && activeDistrictIndex >= 0) {
                event.preventDefault();
                const val = items[activeDistrictIndex].dataset.value;
                if (val && val !== "none") selectDistrict(val);
            } else if (event.key === "Escape") {
                hideDistrictSuggestions();
            }
        });
    }

    // Close on click outside
    document.addEventListener("click", event => {
        if (!event.target.closest(".city-ac")) {
            hideStateSuggestions();
            hideDistrictSuggestions();
        }
    });

    return {
        hideAll: () => {
            hideStateSuggestions();
            hideDistrictSuggestions();
        },
        loadDistricts,
        setStateAndDistrict: async (st, dst) => {
            if (stateInput) stateInput.value = st;
            await loadDistricts(st);
            if (districtInput) districtInput.value = dst;
        }
    };
}


// ============================================================================
// 4. PAGE CONTROLLER IMPLEMENTATIONS
// ============================================================================

const pageControllers = {};

// ----------------------------------------------------------------------------
// 4.1 Home Page
// ----------------------------------------------------------------------------
pageControllers.index = async function () {
    try {
        const metadata = await fetchApi("/meta");
        const cropsElement = getElement("#h-crops");
        const accuracyElement = getElement("#h-acc");
        const modelElement = getElement("#h-model");

        if (cropsElement) cropsElement.textContent = metadata.n_crops;
        if (accuracyElement) accuracyElement.textContent = (metadata.test_accuracy * 100).toFixed(1) + "%";
        if (modelElement) modelElement.textContent = metadata.best_model;
    } catch (e) {
        console.warn("Could not load homepage metadata", e);
    }
};

// ----------------------------------------------------------------------------
// 4.2 Dashboard Page
// ----------------------------------------------------------------------------
pageControllers.dashboard = async function () {
    // 1. Fetch metadata and model performance comparison in parallel
    const [metadata, metricsData] = await Promise.all([
        fetchApi("/meta"),
        fetchApi("/metrics")
    ]);

    // 2. Populate stats cards
    getElement("#d-crops").textContent = metadata.n_crops;
    getElement("#d-model").textContent = metadata.best_model;
    getElement("#d-acc").textContent = (metadata.test_accuracy * 100).toFixed(1) + "%";
    getElement("#d-rows").textContent = metadata.rows;

    // 3. Render model comparison bar chart (5-fold CV vs Test Accuracy)
    renderChart("c-models", {
        type: "bar",
        data: {
            labels: metricsData.comparison.map(m => m.Model),
            datasets: [
                {
                    label: "CV Accuracy",
                    data: metricsData.comparison.map(m => m["CV Accuracy"] * 100),
                    backgroundColor: "#174D32"
                },
                {
                    label: "Test Accuracy",
                    data: metricsData.comparison.map(m => m["Test Accuracy"] * 100),
                    backgroundColor: "#4C956C"
                }
            ]
        },
        options: {
            scales: {
                y: {
                    min: 90,
                    max: 100,
                    title: { display: true, text: "Accuracy (%)" }
                }
            }
        }
    });

};

// ----------------------------------------------------------------------------
// 4.3 Crop Recommendation Page
// ----------------------------------------------------------------------------
pageControllers.recommendation = async function () {
    const stateInput = getElement("#state");
    const stateSuggestions = getElement("#state-suggestions");
    const districtInput = getElement("#district");
    const districtSuggestions = getElement("#district-suggestions");
    const fillExampleBtn = getElement("#fill-example");
    const formElement = getElement("#predict-form");

    // 1. Restore saved soil inputs
    restoreFieldInputs(["N", "P", "K", "ph"]);

    // 2. Setup State & District autocomplete
    const locationPicker = setupLocationAutocomplete({
        stateInput,
        stateSuggestions,
        districtInput,
        districtSuggestions
    });

    // 3. Pre-fill typical Rice example values
    if (fillExampleBtn) {
        fillExampleBtn.onclick = async function () {
            ["N", "P", "K", "ph"].forEach(key => {
                const def = FIELD_DEFINITIONS[key];
                const input = getElement("#f-" + key);
                if (input) input.value = def.defaultValue;
            });
            await locationPicker.setStateAndDistrict("Telangana", "Hyderabad");
            showToast("Example values loaded (Rice in Hyderabad, Telangana)");
        };
    }

    // 4. Form submit handler
    formElement.onsubmit = function (event) {
        event.preventDefault();
        locationPicker.hideAll();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const stateVal = stateInput?.value.trim();
            const districtVal = districtInput?.value.trim();

            if (!stateVal) {
                throw new Error("Please enter or select a State / UT.");
            }
            if (!districtVal) {
                throw new Error("Please enter or select a District.");
            }

            const conditionsPayload = readFormFeatures(["N", "P", "K", "ph"]);
            conditionsPayload.location = {
                state: stateVal,
                district: districtVal
            };

            // Send to FastAPI /predict
            const predictionResult = await fetchApi("/predict", conditionsPayload);

            // Display results in UI
            displayRecommendationResult(predictionResult);

            // Smooth scroll to result
            getElement("#result").scrollIntoView({ behavior: "smooth", block: "start" });
        });
    };
};

/**
 * Renders the recommendation prediction results, confidence meters, and Chart.js graphs
 */
function displayRecommendationResult(result) {
    const status = result.status;
    let htmlContent = "";

    if (result.weather && result.location) {
        htmlContent += `
            <div class="panel">
                <h3><i class="fa-solid fa-cloud-sun"></i> Weather used for ${result.location.district}, ${result.location.state}</h3>
                <div class="kv">
                    <div><b>${result.weather.temperature.toFixed(1)}°C</b><span>Current temperature</span></div>
                    <div><b>${result.weather.humidity.toFixed(0)}%</b><span>Current humidity</span></div>
                    <div><b>${result.weather.annual_rainfall.toFixed(1)} mm</b><span>Rainfall, previous ${result.weather.rainfall_period_days} days</span></div>
                    <div><b>${result.weather.rainfall.toFixed(1)} mm</b><span>Monthly rainfall used by model</span></div>
                </div>
            </div>
        `;
    }

    // CASE A: Out of Distribution / Unusual Range
    if (status === "OUT_OF_RANGE") {
        htmlContent += `
            <div class="alert bad">
                <b><i class="fa-solid fa-triangle-exclamation"></i> Out of range – no crop recommended.</b>
                <p>These values are unlike anything the model was trained on, so any ML recommendation would be unreliable.</p>
                <ul>
                    ${result.reasons.map(r => `<li>${r}</li>`).join("")}
                </ul>
            </div>
        `;
    } 
    // CASE B: Valid Recommendation (OK or LOW_CONFIDENCE)
    else {
        const topCrop = result.top_k[0];
        const statusBadgeClass = status === "OK" ? "ok" : "low";

        htmlContent += `
            <div class="result-top">
                <span class="badge b-${statusBadgeClass}">${status.replace("_", " ")}</span>
                <div style="margin-top:8px;opacity:.85">Recommended crop</div>
                <h2>${capitalizeFirstLetter(topCrop.crop)}</h2>
                <div class="meter">
                    <i style="width:${topCrop.probability * 100}%"></i>
                </div>
                <div>
                    Model probability <b>${(topCrop.probability * 100).toFixed(1)}%</b> · Confidence <b>${result.confidence_label}</b>
                </div>
                ${result.schemes && result.schemes.length > 0 ? `
                    <div style="margin-top:14px">
                        <a class="btn sm" href="/government-schemes?crop=${encodeURIComponent(topCrop.crop)}&state=${encodeURIComponent(result.location?.state || '')}&district=${encodeURIComponent(result.location?.district || '')}" target="_blank" style="cursor:pointer;background:var(--fresh);color:#fff;text-decoration:none">
                            <i class="fa-solid fa-building-columns"></i> View Government Schemes (${result.schemes.length}) <i class="fa-solid fa-arrow-up-right-from-square" style="font-size:0.8em;margin-left:4px"></i>
                        </a>
                    </div>
                ` : ""}
            </div>
        `;

        if (result.reasons && result.reasons.length > 0) {
            htmlContent += `
                <div class="alert">
                    <b>Why confidence is not high:</b>
                    <ul>
                        ${result.reasons.map(reason => `<li>${reason}</li>`).join("")}
                    </ul>
                    <div>Consider the top 3 options below as a shortlist.</div>
                </div>
            `;
        }

        // Top 3 Crops Graph Container
        htmlContent += `
            <div class="panel">
                <h3><i class="fa-solid fa-ranking-star"></i> Top 3 Recommended Crops</h3>
                <div class="chart-box" style="height:200px">
                    <canvas id="c-top"></canvas>
                </div>
            </div>
            <div class="panel">
                <h3><i class="fa-solid fa-magnifying-glass-chart"></i> What Drove This Prediction</h3>
                <div class="chart-box" style="height:260px">
                    <canvas id="c-exp"></canvas>
                </div>
                <div class="note">
                    Positive values push towards ${capitalizeFirstLetter(topCrop.crop)}. Feature effect estimated via model-agnostic random permutation occlusion.
                </div>
            </div>
        `;
    }

    // Reliability & Sensitivity Diagnostics
    htmlContent += `
        <div class="kv">
            <div>
                <b>${result.normalized_entropy ?? "–"}</b>
                <span>Normalised entropy (0 sure – 1 unsure)</span>
            </div>
            <div>
                <b>${result.margin !== undefined && result.margin !== null ? (result.margin * 100).toFixed(1) + "%" : "–"}</b>
                <span>Top-2 probability margin</span>
            </div>
            <div>
                <b>${result.stability_change_rate !== undefined && result.stability_change_rate !== null ? (result.stability_change_rate * 100).toFixed(0) + "%" : "–"}</b>
                <span>Changed in ${result.stability_runs ?? 20} noisy re-runs</span>
            </div>
            <div>
                <b>${result.out_of_range_check?.distance ?? "–"}</b>
                <span>Unusualness (limit ${result.out_of_range_check?.threshold ?? "–"})</span>
            </div>
        </div>
        <div class="inl">
            <a class="btn ghost sm" href="/what-if"><i class="fa-solid fa-sliders"></i> Try What-If Analysis</a>
            <a class="btn ghost sm" href="/land-check"><i class="fa-solid fa-map"></i> Check Land Suitability</a>
            <a class="btn ghost sm" href="/fertilizer"><i class="fa-solid fa-flask"></i> Fertilizer Plan</a>
        </div>
        <p class="note">${result.note} Out-of-range detection is statistical (Mahalanobis distance vs 99th percentile).</p>
    `;

    getElement("#result").innerHTML = htmlContent;

    // Render Charts if recommendation was valid
    if (status !== "OUT_OF_RANGE") {
        // Chart 1: Top 3 Crop Probabilities
        if (result.top_k && Array.isArray(result.top_k)) {
            renderChart("c-top", {
                type: "bar",
                data: {
                    labels: result.top_k.map(item => capitalizeFirstLetter(item.crop)),
                    datasets: [{
                        data: result.top_k.map(item => item.probability * 100),
                        backgroundColor: CHART_COLORS
                    }]
                },
                options: {
                    indexAxis: "y",
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { max: 100, title: { display: true, text: "Probability (%)" } }
                    }
                }
            });
        }

        // Chart 2: Feature Attribution Explanation
        if (result.explanation && Array.isArray(result.explanation)) {
            renderChart("c-exp", {
                type: "bar",
                data: {
                    labels: result.explanation.map(item => `${item.feature} = ${item.value}`),
                    datasets: [{
                        data: result.explanation.map(item => item.effect),
                        backgroundColor: result.explanation.map(item => item.effect >= 0 ? "#4C956C" : "#B3392F")
                    }]
                },
                options: {
                    indexAxis: "y",
                    plugins: { legend: { display: false } }
                }
            });
        }
    }
}

// ----------------------------------------------------------------------------
// 4.4 Ideal Conditions Explorer
// ----------------------------------------------------------------------------
pageControllers.ideal_conditions = async function () {
    const searchInput = getElement("#q");
    const seasonFilter = getElement("#season");
    const cardsContainer = getElement("#cards");

    // Load full crops catalog
    const baseCrops = await getCropsList();
    const detailedCrops = await Promise.all(baseCrops.map(c => fetchApi("/crops/" + c.crop)));

    function renderFilteredCards() {
        const query = searchInput.value.toLowerCase().trim();
        const selectedSeason = seasonFilter.value;

        const filtered = detailedCrops.filter(c => {
            const matchesQuery = c.crop.toLowerCase().includes(query);
            const matchesSeason = !selectedSeason || c.seasons.includes(selectedSeason);
            return matchesQuery && matchesSeason;
        });

        if (filtered.length === 0) {
            cardsContainer.innerHTML = renderEmptyPlaceholder("fa-leaf", "No crops match your filter.");
            return;
        }

        cardsContainer.innerHTML = filtered.map(c => `
            <div class="card crop-card">
                <h3>${capitalizeFirstLetter(c.crop)} <span class="badge b-ideal">${c.duration_days} days</span></h3>
                <div class="tags">
                    <span>${c.seasons}</span>
                    <span>${c.family}</span>
                    <span>${c.soil}</span>
                </div>
                <table class="rng">
                    <tr><th>Feature</th><th>Ideal</th><th>Acceptable</th></tr>
                    ${Object.entries(c.ranges).map(([feat, rng]) => `
                        <tr>
                            <td>${FIELD_DEFINITIONS[feat].label.replace(/ \(.*/, "")}</td>
                            <td>${rng.ideal[0]}–${rng.ideal[1]}</td>
                            <td>${rng.acceptable[0]}–${rng.acceptable[1]}</td>
                        </tr>
                    `).join("")}
                </table>
                <div class="note">
                    Ref. price ${formatRupees(c.ref_price)}/q · yield ${c.yield_q_ha} q/ha · cost ${formatRupees(c.cost_ha)}/ha · N-P₂O₅-K₂O ${c.N}-${c.P2O5}-${c.K2O} kg/ha
                </div>
            </div>
        `).join("");
    }

    searchInput.oninput = renderFilteredCards;
    seasonFilter.onchange = renderFilteredCards;
    renderFilteredCards();
};

// ----------------------------------------------------------------------------
// 4.5 Land Suitability Checker
// ----------------------------------------------------------------------------
pageControllers.land_check = async function () {
    const cropSelect = getElement("#crop");
    const formElement = getElement("#form");
    const stateInput = getElement("#state");
    const stateSuggestions = getElement("#state-suggestions");
    const districtInput = getElement("#district");
    const districtSuggestions = getElement("#district-suggestions");

    // Populate dropdown with available crops
    await populateCropDropdown(cropSelect, false);

    // Restore soil nutrient values from localStorage
    restoreFieldInputs(["N", "P", "K", "ph"]);

    // Setup State & District auto-suggestions
    const locationPicker = setupLocationAutocomplete({
        stateInput,
        stateSuggestions,
        districtInput,
        districtSuggestions
    });

    formElement.onsubmit = function (event) {
        event.preventDefault();
        locationPicker.hideAll();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const stateVal = stateInput?.value.trim();
            const districtVal = districtInput?.value.trim();

            if (!stateVal) {
                throw new Error("Please enter or select a State / UT.");
            }
            if (!districtVal) {
                throw new Error("Please enter or select a District.");
            }

            // Read soil nutrient values (temperature, humidity, and rainfall come from the backend via weather)
            const soilNutrients = readFormFeatures(["N", "P", "K", "ph"]);
            const payload = {
                crop: cropSelect.value,
                N: soilNutrients.N,
                P: soilNutrients.P,
                K: soilNutrients.K,
                ph: soilNutrients.ph,
                location: {
                    state: stateVal,
                    district: districtVal
                }
            };

            const result = await fetchApi("/land-check", payload);

            getElement("#result").innerHTML = `
                ${result.weather ? `
                    <div class="weather-box" style="margin-bottom:16px">
                        <div class="weather-head">
                            <span class="city-name"><i class="fa-solid fa-location-dot"></i> Weather for ${escapeHtml(result.location?.district || '')}, ${escapeHtml(result.location?.state || '')}</span>
                            <span class="badge b-ok"><i class="fa-solid fa-cloud-sun"></i> Live Weather</span>
                        </div>
                        <div class="weather-metrics">
                            <div class="metric">
                                <span class="metric-val">${result.weather.temperature}°C</span>
                                <span class="metric-lbl"><i class="fa-solid fa-temperature-half"></i> Temperature</span>
                            </div>
                            <div class="metric">
                                <span class="metric-val">${result.weather.humidity}%</span>
                                <span class="metric-lbl"><i class="fa-solid fa-droplet"></i> Humidity</span>
                            </div>
                            <div class="metric">
                                <span class="metric-val">${result.weather.rainfall} mm</span>
                                <span class="metric-lbl"><i class="fa-solid fa-cloud-rain"></i> Rainfall</span>
                            </div>
                        </div>
                    </div>
                ` : ""}

                <div class="panel" style="text-align:center">
                    <div class="gauge" style="--p:${result.score}">
                        <span>${result.score}%</span>
                    </div>
                    <p style="margin:12px 0 0">Suitability score for <b>${capitalizeFirstLetter(result.crop)}</b></p>
                    ${renderBadge(result.verdict)}
                </div>

                <div class="panel tw">
                    <table>
                        <tr><th>Feature</th><th>Your Land / Climate Value</th><th>Ideal Range</th><th>Status</th></tr>
                        ${result.features.map(f => `
                            <tr>
                                <td>${FIELD_DEFINITIONS[f.feature] ? FIELD_DEFINITIONS[f.feature].label : f.feature}</td>
                                <td>${f.value}</td>
                                <td>${f.ideal.join(" – ")}</td>
                                <td>${renderBadge(f.status)}</td>
                            </tr>
                        `).join("")}
                    </table>
                </div>

                <div class="panel">
                    <h3><i class="fa-solid fa-screwdriver-wrench"></i> What to Improve</h3>
                    ${result.improvements.length > 0 
                        ? `<ul>${result.improvements.map(tip => `<li>${tip}</li>`).join("")}</ul>`
                        : "<p>All soil and climate conditions are within the crop's ideal range.</p>"
                    }
                </div>

                <div class="panel">
                    <h3><i class="fa-solid fa-brain"></i> Machine Learning Opinion</h3>
                    ${result.ml.status === "OUT_OF_RANGE"
                        ? `<div class="alert bad">Inputs are out of the model's range – no ML opinion available.</div>`
                        : `
                            <p>
                                Model's top recommendation for this land: <b>${capitalizeFirstLetter(result.ml.predicted_crop)}</b> 
                                (${renderBadge(result.ml.status === "OK" ? "ok" : "low", result.ml.status.replace("_", " "))}).
                            </p>
                            <p>
                                Probability score for <b>${capitalizeFirstLetter(result.crop)}</b>: 
                                <b>${((result.ml.probability_for_selected_crop || 0) * 100).toFixed(1)}%</b>.
                            </p>
                        `
                    }
                    <div class="note">${result.note}</div>
                </div>
            `;

            // Scroll to results
            getElement("#result").scrollIntoView({ behavior: "smooth", block: "start" });
        });
    };
};

// ----------------------------------------------------------------------------
// 4.6 Fertilizer Planning
// ----------------------------------------------------------------------------
pageControllers.fertilizer = async function () {
    const cropSelect = getElement("#crop");
    const areaInput = getElement("#area");
    const formElement = getElement("#form");

    await populateCropDropdown(cropSelect, false);
    restoreFieldInputs(["N", "P", "K"]);

    formElement.onsubmit = function (event) {
        event.preventDefault();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const soilNutrients = readFormFeatures(["N", "P", "K"]);
            const areaValue = parseFloat(areaInput.value);

            if (!(areaValue > 0)) {
                throw new Error("Land area must be greater than 0");
            }

            const payload = {
                crop: cropSelect.value,
                N: soilNutrients.N,
                P: soilNutrients.P,
                K: soilNutrients.K,
                area_ha: areaValue
            };

            const result = await fetchApi("/fertilizer", payload);
            const quantities = result.quantity;

            getElement("#result").innerHTML = `
                <div class="kv">
                    <div><b>${Math.round(quantities.urea_kg)} kg</b><span>Total Urea</span></div>
                    <div><b>${Math.round(quantities.dap_kg)} kg</b><span>Total DAP</span></div>
                    <div><b>${Math.round(quantities.mop_kg)} kg</b><span>Total MOP</span></div>
                    <div><b>${formatRupees(result.estimated_cost_inr)}</b><span>Estimated Fertilizer Cost</span></div>
                </div>

                <div class="panel tw">
                    <h3><i class="fa-solid fa-gauge-high"></i> Nutrient Requirement (kg/ha)</h3>
                    <table>
                        <tr><th>Nutrient</th><th>Soil Class</th><th>Crop Dose</th><th>Adjusted Need</th></tr>
                        <tr>
                            <td>Nitrogen (N)</td>
                            <td>${renderBadge(result.soil_class.N === "LOW" ? "low" : result.soil_class.N === "HIGH" ? "ideal" : "medium", result.soil_class.N)}</td>
                            <td>${result.recommended_dose_kg_ha.N} kg/ha</td>
                            <td>${result.nutrient_need_kg_ha.N} kg/ha (${result.adjustment.N})</td>
                        </tr>
                        <tr>
                            <td>Phosphorus (P₂O₅)</td>
                            <td>${renderBadge(result.soil_class.P === "LOW" ? "low" : result.soil_class.P === "HIGH" ? "ideal" : "medium", result.soil_class.P)}</td>
                            <td>${result.recommended_dose_kg_ha.P2O5} kg/ha</td>
                            <td>${result.nutrient_need_kg_ha.P2O5} kg/ha (${result.adjustment.P})</td>
                        </tr>
                        <tr>
                            <td>Potassium (K₂O)</td>
                            <td>${renderBadge(result.soil_class.K === "LOW" ? "low" : result.soil_class.K === "HIGH" ? "ideal" : "medium", result.soil_class.K)}</td>
                            <td>${result.recommended_dose_kg_ha.K2O} kg/ha</td>
                            <td>${result.nutrient_need_kg_ha.K2O} kg/ha (${result.adjustment.K})</td>
                        </tr>
                    </table>
                </div>

                <div class="panel">
                    <h3><i class="fa-solid fa-calendar-days"></i> Application Schedule (for ${result.area_ha} ha)</h3>
                    <p><b>Basal Dressing (at sowing):</b> ${result.basal.urea_kg} kg Urea + ${result.basal.dap_kg} kg DAP + ${result.basal.mop_kg} kg MOP</p>
                    ${result.top_dressing.map(split => `
                        <p><b>Top-Dressing:</b> ${split.urea_kg} kg Urea (${split.when})</p>
                    `).join("")}
                </div>

                <div class="sponsor">
                    <span class="badge b-low">SPONSORED</span>
                    ${result.sponsored.items.map(item => `
                        <p style="margin:6px 0"><b>${item.name}</b> – ${item.product}</p>
                    `).join("")}
                    <div class="note">${result.sponsored.note}</div>
                </div>

                <div class="note">
                    <b>Calculations & Assumptions:</b>
                    <ul>
                        ${result.assumptions.map(a => `<li>${a}</li>`).join("")}
                    </ul>
                </div>
            `;
        });
    };
};

// ----------------------------------------------------------------------------
// 4.7 Market Prices (Live Agmarknet & Reference)
// ----------------------------------------------------------------------------
pageControllers.market = async function () {
    const cropSelect = getElement("#crop");
    const stateSelect = getElement("#state");
    const formElement = getElement("#form");

    await Promise.all([
        populateCropDropdown(cropSelect, false),
        populateStateDropdown(stateSelect)
    ]);

    formElement.onsubmit = function (event) {
        event.preventDefault();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const cropName = cropSelect.value;
            const stateValue = stateSelect.value;
            let queryUrl = `/market/${cropName}`;
            if (stateValue) {
                queryUrl += `?state=${encodeURIComponent(stateValue)}`;
            }

            const marketData = await fetchApi(queryUrl);
            const isLive = marketData.type === "live";

            let html = `
                <div class="panel">
                    <div class="inl" style="justify-content:space-between">
                        ${renderBadge(isLive ? "live" : "ref", isLive ? "LIVE MANDI PRICES" : "REFERENCE PRICE (not live)")}
                        <span class="note">
                            Retrieved: ${marketData.retrieved_on}
                            ${marketData.latest_market_date ? " · Latest: " + marketData.latest_market_date : ""}
                            ${marketData.cached ? " · Cached (6h)" : ""}
                        </span>
                    </div>
                    <p style="margin-top:8px">${marketData.message}</p>
            `;

            if (isLive && marketData.records && marketData.records.length > 0) {
                html += `
                        <div class="chart-box"><canvas id="c-mk"></canvas></div>
                    </div>
                    <div class="panel tw">
                        <table>
                            <tr><th>State</th><th>Market (Mandi)</th><th>Arrival Date</th><th>Min</th><th>Max</th><th>Modal Price</th></tr>
                            ${marketData.records.map(rec => `
                                <tr>
                                    <td>${rec.state}</td>
                                    <td>${rec.market}</td>
                                    <td>${rec.date}</td>
                                    <td>₹${rec.min}</td>
                                    <td>₹${rec.max}</td>
                                    <td><b>₹${rec.modal}</b></td>
                                </tr>
                            `).join("")}
                        </table>
                        <div class="note">All prices in ₹ per quintal. Source: Agmarknet via data.gov.in.</div>
                    </div>
                `;

                getElement("#result").innerHTML = html;

                // Render Mandi Price Range Chart
                const sampleRecords = marketData.records.slice(0, 15);
                renderChart("c-mk", {
                    type: "bar",
                    data: {
                        labels: sampleRecords.map(r => r.market),
                        datasets: [
                            { label: "Min Price", data: sampleRecords.map(r => r.min), backgroundColor: "#DCECCB" },
                            { label: "Modal (Typical)", data: sampleRecords.map(r => r.modal), backgroundColor: "#4C956C" },
                            { label: "Max Price", data: sampleRecords.map(r => r.max), backgroundColor: "#174D32" }
                        ]
                    },
                    options: {
                        scales: {
                            y: { title: { display: true, text: "₹ / quintal" } }
                        }
                    }
                });
            } else {
                html += `
                    <div class="kv">
                        <div><b>${formatRupees(marketData.reference_price)}</b><span>Reference Price per Quintal</span></div>
                    </div>
                    <div class="note">No live mandi records returned for this commodity/state. Showing indicative MSP / baseline reference rates.</div>
                </div>`;
                getElement("#result").innerHTML = html;
            }
        });
    };
};

// ----------------------------------------------------------------------------
// 4.8 Profit & Yield Estimator
// ----------------------------------------------------------------------------
pageControllers.profit = async function () {
    const cropSelect = getElement("#crop");
    const stateSelect = getElement("#state");
    const areaInput = getElement("#area");
    const priceInput = getElement("#price");
    const yieldInput = getElement("#yld");
    const costInput = getElement("#cost");
    const durationInput = getElement("#dur");
    const formElement = getElement("#form");

    await Promise.all([
        populateCropDropdown(cropSelect, false),
        populateStateDropdown(stateSelect)
    ]);

    // Update input placeholders with default crop values on change
    async function updatePlaceholders() {
        const cropDetails = await fetchApi("/crops/" + cropSelect.value);
        priceInput.placeholder = cropDetails.ref_price;
        yieldInput.placeholder = cropDetails.yield_q_ha;
        costInput.placeholder = cropDetails.cost_ha;
        durationInput.placeholder = cropDetails.duration_days;
    }

    cropSelect.onchange = updatePlaceholders;
    await updatePlaceholders();

    formElement.onsubmit = function (event) {
        event.preventDefault();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const payload = {
                crop: cropSelect.value,
                area_ha: parseFloat(areaInput.value),
                state: stateSelect.value || null
            };

            const customPrice = parseFloat(priceInput.value);
            const customYield = parseFloat(yieldInput.value);
            const customCost = parseFloat(costInput.value);
            const customDuration = parseInt(durationInput.value, 10);

            if (!isNaN(customPrice)) payload.price_per_q = customPrice;
            if (!isNaN(customYield)) payload.yield_q_ha = customYield;
            if (!isNaN(customCost)) payload.cost_per_ha = customCost;
            if (!isNaN(customDuration)) payload.duration_days = customDuration;

            const result = await fetchApi("/profit", payload);
            const scenarios = result.scenarios;

            getElement("#result").innerHTML = `
                <div class="kv">
                    <div><b>${formatRupees(result.price_per_q)}</b><span>Price/q (${result.price_source})</span></div>
                    <div><b>${formatRupees(result.total_cost)}</b><span>Total Cultivation Cost</span></div>
                    <div><b>${result.break_even_yield_q_ha} q/ha</b><span>Break-even Yield</span></div>
                    <div><b>${formatRupees(result.break_even_price_per_q)}</b><span>Break-even Price/q</span></div>
                </div>

                <div class="panel tw">
                    <table>
                        <tr><th>Scenario</th><th>Yield (q/ha)</th><th>Revenue</th><th>Net Profit</th><th>Profit / Month</th></tr>
                        ${Object.entries(scenarios).map(([level, data]) => `
                            <tr>
                                <td>${capitalizeFirstLetter(level)}</td>
                                <td>${data.yield_q_ha}</td>
                                <td>${formatRupees(data.revenue)}</td>
                                <td><b style="color:${data.profit < 0 ? '#B3392F' : '#12623a'}">${formatRupees(data.profit)}</b></td>
                                <td>${formatRupees(data.profit_per_month)}</td>
                            </tr>
                        `).join("")}
                    </table>
                </div>

                <div class="panel">
                    <div class="chart-box" style="height:240px">
                        <canvas id="c-pf"></canvas>
                    </div>
                    <div class="note">${result.note} Crop duration: ${result.duration_days} days.</div>
                </div>
            `;

            renderChart("c-pf", {
                type: "bar",
                data: {
                    labels: Object.keys(scenarios).map(capitalizeFirstLetter),
                    datasets: [
                        { label: "Gross Revenue", data: Object.values(scenarios).map(s => s.revenue), backgroundColor: "#4C956C" },
                        { label: "Net Profit", data: Object.values(scenarios).map(s => s.profit), backgroundColor: "#174D32" }
                    ]
                },
                options: {
                    scales: {
                        y: { title: { display: true, text: "Indian Rupees (₹)" } }
                    }
                }
            });
        });
    };
};

// ----------------------------------------------------------------------------
// 4.9 What-If Analysis & Continuous Feature Sweep
// ----------------------------------------------------------------------------
pageControllers.what_if = async function () {
    const keys = Object.keys(FIELD_DEFINITIONS);
    restoreFieldInputs(keys);

    const featureSelect = getElement("#sw-f");
    const changesContainer = getElement("#changes");
    const addChangeBtn = getElement("#add-change");
    const whatIfForm = getElement("#form");
    const sweepForm = getElement("#sweep-form");

    // Populate sweep feature options
    featureSelect.innerHTML = keys.map(k => `<option value="${k}">${FIELD_DEFINITIONS[k].label}</option>`).join("");

    // Function to add a delta change row
    function createChangeRow() {
        const row = document.createElement("div");
        row.className = "inl chg";
        row.style.marginBottom = "8px";

        row.innerHTML = `
            <div>
                <label>Feature</label>
                <select class="c-f">
                    ${keys.map(k => `<option value="${k}">${FIELD_DEFINITIONS[k].label}</option>`).join("")}
                </select>
            </div>
            <div>
                <label>Mode</label>
                <select class="c-m">
                    <option value="set">Set to exact</option>
                    <option value="add">Add value</option>
                    <option value="pct">Change by %</option>
                </select>
            </div>
            <div>
                <label>Value</label>
                <input type="number" class="c-v" step="any" value="0">
            </div>
            <button type="button" class="btn ghost sm" aria-label="Remove change">
                <i class="fa-solid fa-xmark"></i>
            </button>
        `;

        row.querySelector("button").onclick = () => row.remove();
        changesContainer.appendChild(row);
    }

    createChangeRow();
    addChangeBtn.onclick = createChangeRow;

    // What-If Scenario Compare Submit
    whatIfForm.onsubmit = function (event) {
        event.preventDefault();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const changes = {};
            getAllElements(".chg").forEach(row => {
                const featureKey = row.querySelector(".c-f").value;
                const mode = row.querySelector(".c-m").value;
                const value = parseFloat(row.querySelector(".c-v").value);
                if (!isNaN(value)) {
                    changes[featureKey] = { mode, value };
                }
            });

            if (Object.keys(changes).length === 0) {
                throw new Error("Please specify at least one change.");
            }

            const baseConditions = readFormFeatures(keys);
            const payload = {
                base: baseConditions,
                changes: changes
            };

            const response = await fetchApi("/what-if", payload);
            const orig = response.original;
            const mod = response.modified;

            const formatTopCrop = cropObj => {
                if (!cropObj.crop) return "No recommendation (Out of range)";
                return `<b>${capitalizeFirstLetter(cropObj.crop)}</b> (${(cropObj.top_k[0].probability * 100).toFixed(0)}%)`;
            };

            getElement("#result").innerHTML = `
                <div class="grid g2">
                    <div class="card">
                        <div class="note">Original Prediction</div>
                        <h3>${formatTopCrop(orig)}</h3>
                        ${renderBadge(orig.status === "OK" ? "ok" : orig.status === "OUT_OF_RANGE" ? "out" : "low", orig.status.replace("_", " "))}
                    </div>
                    <div class="card">
                        <div class="note">Modified Prediction</div>
                        <h3>${formatTopCrop(mod)}</h3>
                        ${renderBadge(mod.status === "OK" ? "ok" : mod.status === "OUT_OF_RANGE" ? "out" : "low", mod.status.replace("_", " "))}
                    </div>
                </div>

                ${response.top_crop_changed ? `<div class="alert"><b>The recommended top crop changed under these modifications!</b></div>` : ""}

                <div class="panel">
                    <h3><i class="fa-solid fa-chart-column"></i> Probability Distribution Shift</h3>
                    <div class="chart-box"><canvas id="c-wi"></canvas></div>
                </div>

                <div class="panel tw">
                    <table>
                        <tr><th>Modified Feature</th><th>Original Value</th><th>New Value</th></tr>
                        ${response.influential_changes.map(ch => `
                            <tr>
                                <td>${FIELD_DEFINITIONS[ch.feature].label}</td>
                                <td>${ch.from}</td>
                                <td>${ch.to}</td>
                            </tr>
                        `).join("")}
                    </table>
                    <div class="note">${response.note}</div>
                </div>
            `;

            renderChart("c-wi", {
                type: "bar",
                data: {
                    labels: response.probability_changes.map(p => capitalizeFirstLetter(p.crop)),
                    datasets: [
                        { label: "Before (%)", data: response.probability_changes.map(p => p.before * 100), backgroundColor: "#DCECCB" },
                        { label: "After (%)", data: response.probability_changes.map(p => p.after * 100), backgroundColor: "#174D32" }
                    ]
                },
                options: {
                    scales: {
                        y: { title: { display: true, text: "Probability (%)" } }
                    }
                }
            });
        });
    };

    // Continuous Feature Sweep Submit
    sweepForm.onsubmit = function (event) {
        event.preventDefault();
        const sweepButton = getElement("#sw-go");

        executeWithLoadingState(sweepButton, async function () {
            const baseConditions = readFormFeatures(keys);
            const payload = {
                base: baseConditions,
                feature: featureSelect.value,
                start: parseFloat(getElement("#sw-a").value),
                end: parseFloat(getElement("#sw-b").value),
                steps: parseInt(getElement("#sw-n").value, 10)
            };

            const sweepResponse = await fetchApi("/what-if/sweep", payload);
            const distinctTopCrops = Array.from(new Set(sweepResponse.points.map(p => p.top_crop)));

            getElement("#sweep-result").innerHTML = `
                <div class="panel">
                    <h3><i class="fa-solid fa-chart-line"></i> Sensitivity Sweep: ${FIELD_DEFINITIONS[sweepResponse.feature].label}</h3>
                    <div class="chart-box"><canvas id="c-sw"></canvas></div>
                    ${sweepResponse.tipping_points.length > 0 
                        ? `
                            <div class="alert">
                                <b>Tipping Points Identified:</b>
                                <ul>
                                    ${sweepResponse.tipping_points.map(t => `
                                        <li>Between ${t.between[0]} and ${t.between[1]}: Top crop switches from <b>${capitalizeFirstLetter(t.from)}</b> → <b>${capitalizeFirstLetter(t.to)}</b></li>
                                    `).join("")}
                                </ul>
                            </div>
                        `
                        : `<p class="note">The recommended top crop remains constant across this entire range.</p>`
                    }
                </div>
            `;

            renderChart("c-sw", {
                type: "line",
                data: {
                    labels: sweepResponse.points.map(p => p.value),
                    datasets: distinctTopCrops.map((cropName, idx) => ({
                        label: capitalizeFirstLetter(cropName),
                        data: sweepResponse.points.map(p => p.probabilities[cropName] * 100),
                        borderColor: CHART_COLORS[idx % CHART_COLORS.length],
                        backgroundColor: CHART_COLORS[idx % CHART_COLORS.length],
                        tension: 0.25
                    }))
                },
                options: {
                    scales: {
                        y: { title: { display: true, text: "Probability (%)" } },
                        x: { title: { display: true, text: FIELD_DEFINITIONS[sweepResponse.feature].label } }
                    }
                }
            });
        });
    };

    // Pre-populate sweep range inputs when selected feature changes
    function autoSetSweepBounds() {
        const featDef = FIELD_DEFINITIONS[featureSelect.value];
        getElement("#sw-a").value = featDef.min === 0 ? 0 : featDef.min;
        getElement("#sw-b").value = Math.min(featDef.max, featDef.defaultValue * 2 || featDef.max);
    }

    featureSelect.onchange = autoSetSweepBounds;
    featureSelect.value = "rainfall";
    autoSetSweepBounds();
};

// ----------------------------------------------------------------------------
// 4.10 Crop Rotation Suggestions
// ----------------------------------------------------------------------------
pageControllers.rotation = async function () {
    const cropSelect = getElement("#crop");
    const seasonSelect = getElement("#season");
    const useMlCheckbox = getElement("#use-ml");
    const mlBox = getElement("#ml-box");
    const formElement = getElement("#form");

    await populateCropDropdown(cropSelect, false);
    restoreFieldInputs(Object.keys(FIELD_DEFINITIONS));

    useMlCheckbox.onchange = function () {
        mlBox.hidden = !useMlCheckbox.checked;
    };

    formElement.onsubmit = function (event) {
        event.preventDefault();
        const submitButton = getElement("#go");

        executeWithLoadingState(submitButton, async function () {
            const payload = {
                previous_crop: cropSelect.value,
                next_season: seasonSelect.value || null
            };

            if (useMlCheckbox.checked) {
                payload.conditions = readFormFeatures(Object.keys(FIELD_DEFINITIONS));
            }

            const response = await fetchApi("/rotation", payload);

            if (!response.suggestions || response.suggestions.length === 0) {
                getElement("#result").innerHTML = renderEmptyPlaceholder("fa-rotate", "No suitable crop rotations found for that season. Try another.");
                return;
            }

            getElement("#result").innerHTML = response.suggestions.map((sug, index) => `
                <div class="card" style="margin-bottom:14px">
                    <h3 style="text-transform:capitalize">
                        ${index + 1}. ${sug.crop} <span class="badge b-ideal">Agronomic Score: ${sug.score}</span>
                    </h3>
                    <div class="tags">
                        <span>Season: ${sug.seasons}</span>
                        <span>Duration: ${sug.duration_days} days</span>
                    </div>
                    <ul>
                        ${sug.reasons.map(reason => `<li>${reason}</li>`).join("")}
                    </ul>
                </div>
            `).join("") + `<div class="note">${response.disclaimer}</div>`;
        });
    };
};

// ----------------------------------------------------------------------------
// 4.11 Model Performance & Decision Tree Rules
// ----------------------------------------------------------------------------
pageControllers.model_performance = async function () {
    // Fetch metrics, class-wise F1, robustness tests, and surrogate tree rules in parallel
    const [metrics, classwiseMetrics, robustnessData, decisionRules] = await Promise.all([
        fetchApi("/metrics"),
        fetchApi("/metrics/classwise"),
        fetchApi("/metrics/robustness"),
        fetchApi("/metrics/decision-rules")
    ]);

    // 1. Display Selected Model & Tie-Break Logic
    getElement("#best").innerHTML = `
        ${metrics.best_model} 
        <small>(selected among ${metrics.tied_models.join(", ")} – tied within ±${metrics.tie_tolerance} CV accuracy)</small>
    `;

    // 2. Render Full 8-Model Comparison Table
    const comparisonTable = getElement("#cmp");
    comparisonTable.innerHTML = `
        <thead>
            <tr>
                <th>Model</th>
                <th>5-Fold CV Accuracy</th>
                <th>Test Accuracy</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>F1-Score</th>
                <th>Macro F1</th>
                <th>Top-3 Accuracy</th>
            </tr>
        </thead>
        <tbody>
            ${metrics.comparison.map(m => `
                <tr ${m.Model === metrics.best_model ? 'style="background:#eef6e8;font-weight:600"' : ''}>
                    <td>${m.Model}</td>
                    <td>${(m["CV Accuracy"] * 100).toFixed(2)}% ± ${(m["CV Std"] * 100).toFixed(2)}%</td>
                    <td>${(m["Test Accuracy"] * 100).toFixed(2)}%</td>
                    <td>${m.Precision.toFixed(4)}</td>
                    <td>${m.Recall.toFixed(4)}</td>
                    <td>${m["F1-score"].toFixed(4)}</td>
                    <td>${m["Macro F1"].toFixed(4)}</td>
                    <td>${(m["Top-3 Accuracy"] * 100).toFixed(1)}%</td>
                </tr>
            `).join("")}
        </tbody>
    `;

    // 3. Render Class-Wise F1 Chart
    const cropClasses = Object.keys(classwiseMetrics).filter(
        k => !["accuracy", "macro avg", "weighted avg"].includes(k)
    );

    renderChart("c-cw", {
        type: "bar",
        data: {
            labels: cropClasses.map(capitalizeFirstLetter),
            datasets: [{
                label: "F1-score",
                data: cropClasses.map(c => classwiseMetrics[c]["f1-score"]),
                backgroundColor: "#4C956C"
            }]
        },
        options: {
            scales: {
                y: { min: 0.90, max: 1.01, title: { display: true, text: "F1-Score" } }
            },
            plugins: { legend: { display: false } }
        }
    });

    // 4. Render Robustness & Feature Perturbation Chart
    renderChart("c-rb", {
        type: "bar",
        data: {
            labels: Object.keys(robustnessData.single_feature).map(k => FIELD_DEFINITIONS[k].label.replace(/ \(.*/, "")),
            datasets: [
                {
                    label: "Noise on Single Feature",
                    data: Object.values(robustnessData.single_feature).map(v => v * 100),
                    backgroundColor: "#174D32"
                },
                {
                    label: "Feature Missing (Mean-Imputed)",
                    data: Object.values(robustnessData.missing_feature).map(v => v * 100),
                    backgroundColor: "#B7791F"
                }
            ]
        },
        options: {
            scales: {
                y: { title: { display: true, text: "% Predictions Changed" } }
            }
        }
    });

    // 5. Global Noise Stability Summary
    getElement("#rb-all").textContent = Object.entries(robustnessData.all_features)
        .map(([level, val]) => `${level} noise → ${(val * 100).toFixed(1)}% prediction change`)
        .join(" · ");

    // 6. Decision Tree Human-Readable Surrogate Rules
    getElement("#rules").textContent = decisionRules.rules;
};

// ----------------------------------------------------------------------------
// 4.12 7-Day Weather Forecast (Open-Meteo)
// ----------------------------------------------------------------------------
pageControllers.weather = function () {
    const formElement = getElement("#form");
    const cityInput = getElement("#city");
    const submitButton = getElement("#go");
    const resultContainer = getElement("#result");
    const suggestionsBox = getElement("#city-suggestions");

    if (!formElement || !cityInput || !resultContainer) return;

    function escapeHtml(text) {
        return String(text ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function formatValue(value, fallback = "–") {
        return value === null || value === undefined ? fallback : value;
    }

    // ---- Live city / district / state autocomplete ----
    let suggestTimer = null;
    let latestSuggestId = 0;
    let currentSuggestions = [];
    let activeSuggestionIndex = -1;

    function hideSuggestions() {
        if (!suggestionsBox) return;
        suggestionsBox.hidden = true;
        suggestionsBox.innerHTML = "";
        currentSuggestions = [];
        activeSuggestionIndex = -1;
        if (cityInput) {
            cityInput.setAttribute("aria-expanded", "false");
        }
    }

    function selectSuggestion(item) {
        cityInput.value = item.value;
        hideSuggestions();
        cityInput.focus();
    }

    function renderSuggestions(items) {
        if (!suggestionsBox) return;
        currentSuggestions = items;
        activeSuggestionIndex = -1;

        if (!items.length) {
            hideSuggestions();
            return;
        }

        suggestionsBox.innerHTML = items.map((item, idx) => `
            <li class="ac-item" role="option" data-index="${idx}">
                <i class="fa-solid fa-location-dot" style="color:var(--fresh);margin-right:6px"></i>${escapeHtml(item.label)}
            </li>
        `).join("");
        suggestionsBox.hidden = false;
        if (cityInput) {
            cityInput.setAttribute("aria-expanded", "true");
        }
    }

    function updateActiveSuggestion() {
        if (!suggestionsBox) return;
        getAllElements(".ac-item", suggestionsBox).forEach((el, idx) => {
            el.classList.toggle("active", idx === activeSuggestionIndex);
        });
    }

    if (suggestionsBox) {
        cityInput.addEventListener("input", () => {
            const query = cityInput.value.trim();
            clearTimeout(suggestTimer);

            if (query.length < 2) {
                hideSuggestions();
                return;
            }

            suggestTimer = setTimeout(async () => {
                const requestId = ++latestSuggestId;
                try {
                    const data = await fetchApi(`/weather/suggest?q=${encodeURIComponent(query)}`);
                    if (requestId !== latestSuggestId) return;
                    renderSuggestions(data.suggestions || []);
                } catch {
                    if (requestId === latestSuggestId) hideSuggestions();
                }
            }, 250);
        });

        // Use mousedown so clicking a suggestion works before input blur
        suggestionsBox.addEventListener("mousedown", event => {
            const itemEl = event.target.closest(".ac-item");
            if (!itemEl) return;
            event.preventDefault();
            const idx = parseInt(itemEl.dataset.index, 10);
            if (!isNaN(idx) && currentSuggestions[idx]) {
                selectSuggestion(currentSuggestions[idx]);
            }
        });

        // Keyboard navigation (ArrowDown, ArrowUp, Enter, Escape)
        cityInput.addEventListener("keydown", event => {
            if (suggestionsBox.hidden || !currentSuggestions.length) return;

            if (event.key === "ArrowDown") {
                event.preventDefault();
                activeSuggestionIndex = (activeSuggestionIndex + 1) % currentSuggestions.length;
                updateActiveSuggestion();
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                activeSuggestionIndex = (activeSuggestionIndex - 1 + currentSuggestions.length) % currentSuggestions.length;
                updateActiveSuggestion();
            } else if (event.key === "Enter" && activeSuggestionIndex >= 0) {
                event.preventDefault();
                selectSuggestion(currentSuggestions[activeSuggestionIndex]);
            } else if (event.key === "Escape") {
                hideSuggestions();
            }
        });

        document.addEventListener("click", event => {
            if (!event.target.closest(".city-ac")) {
                hideSuggestions();
            }
        });
    }

    // ---- Fetch and render 7-day forecast ----
    formElement.onsubmit = function (event) {
        event.preventDefault();
        hideSuggestions();

        executeWithLoadingState(submitButton, async function () {
            const city = cityInput.value.trim();
            if (!city) {
                throw new Error("Please enter a city, district, or state name.");
            }

            // Show a clear loading message while fetching live forecast data
            resultContainer.innerHTML = `
                <div class="panel">
                    ${renderEmptyPlaceholder("fa-spinner fa-spin", `Loading 7-day weather forecast for ${escapeHtml(city)}...`)}
                </div>
            `;

            const url = `/weather?city=${encodeURIComponent(city)}`;
            const forecast = await fetchApi(url);

            const locationParts = [forecast.location];
            if (forecast.state && forecast.state.toLowerCase() !== String(forecast.location || "").toLowerCase()) {
                locationParts.push(forecast.state);
            }
            if (forecast.country) {
                locationParts.push(forecast.country);
            }
            const locationLabel = locationParts.filter(Boolean).join(", ");

            const rowsHtml = (forecast.days || []).map(day => `
                <tr>
                    <td><b>${escapeHtml(day.date)}</b></td>
                    <td>${formatValue(day.min_temp_c)}</td>
                    <td>${formatValue(day.max_temp_c)}</td>
                    <td>${formatValue(day.humidity_percent)}%</td>
                    <td>${formatValue(day.rain_mm)}</td>
                    <td>${formatValue(day.rain_probability)}%</td>
                </tr>
            `).join("");

            resultContainer.innerHTML = `
                <div class="panel">
                    <div class="inl" style="justify-content:space-between;align-items:center">
                        <h3 style="margin:0"><i class="fa-solid fa-location-dot"></i> ${escapeHtml(locationLabel)}</h3>
                        ${renderBadge("live", `Source: ${escapeHtml(forecast.source)}`)}
                    </div>
                </div>

                <div class="panel tw">
                    <h3><i class="fa-solid fa-calendar-week"></i> 7-Day Forecast</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Min Temperature (°C)</th>
                                <th>Max Temperature (°C)</th>
                                <th>Humidity (%)</th>
                                <th>Rainfall (mm)</th>
                                <th>Rain Probability (%)</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rowsHtml}
                        </tbody>
                    </table>
                    <div class="note">${escapeHtml(forecast.note)}</div>
                </div>
            `;
        });
    };
};

// ----------------------------------------------------------------------------
// 4.13 Government Agricultural Schemes Page
// ----------------------------------------------------------------------------
pageControllers.schemes = async function () {
    const cropSelect = getElement("#scheme-crop");
    const stateInput = getElement("#scheme-state");
    const stateSuggestions = getElement("#scheme-state-suggestions");
    const formElement = getElement("#schemes-form");
    const submitBtn = getElement("#schemes-go");
    const resultContainer = getElement("#schemes-result");

    if (!formElement || !resultContainer) return;

    // 1. Populate crops dropdown dynamically
    await populateCropDropdown(cropSelect);

    // 2. Read query parameters from URL (e.g. ?crop=rice&state=Telangana)
    const urlParams = new URLSearchParams(window.location.search);
    const initialCrop = (urlParams.get("crop") || "rice").toLowerCase();
    const initialState = urlParams.get("state") || "Telangana";

    if (cropSelect) cropSelect.value = initialCrop;
    if (stateInput) stateInput.value = initialState;

    // 3. Load state list for auto-suggestion
    let allStates = [];
    try {
        const resp = await fetchApi("/states");
        allStates = resp.states || [];
    } catch {
        allStates = [];
    }

    function hideStateSuggestions() {
        if (!stateSuggestions) return;
        stateSuggestions.hidden = true;
        stateSuggestions.innerHTML = "";
        stateInput?.setAttribute("aria-expanded", "false");
    }

    function renderStateSuggestions(list) {
        if (!stateSuggestions) return;
        if (!list.length) {
            hideStateSuggestions();
            return;
        }
        stateSuggestions.innerHTML = list.map((st, idx) => `
            <li class="ac-item" role="option" data-value="${escapeHtml(st)}" data-index="${idx}">
                <i class="fa-solid fa-location-dot" style="color:var(--fresh);margin-right:6px"></i>${escapeHtml(st)}
            </li>
        `).join("");
        stateSuggestions.hidden = false;
        stateInput?.setAttribute("aria-expanded", "true");
    }

    if (stateInput && stateSuggestions) {
        const showFilteredStates = async () => {
            if (!allStates.length) {
                try {
                    const resp = await fetchApi("/states");
                    allStates = resp.states || [];
                } catch {
                    allStates = [];
                }
            }
            const query = (stateInput.value || "").trim().toLowerCase();
            const filtered = query ? allStates.filter(s => s.toLowerCase().includes(query)) : allStates;
            renderStateSuggestions(filtered.slice(0, 10));
        };

        stateInput.addEventListener("input", showFilteredStates);
        stateInput.addEventListener("focus", showFilteredStates);
        stateInput.addEventListener("click", showFilteredStates);

        stateSuggestions.addEventListener("mousedown", event => {
            const item = event.target.closest(".ac-item");
            if (!item) return;
            event.preventDefault();
            const val = item.dataset.value;
            if (val) {
                stateInput.value = val;
                hideStateSuggestions();
            }
        });

        document.addEventListener("click", event => {
            if (!event.target.closest(".city-ac")) {
                hideStateSuggestions();
            }
        });
    }

    // 4. Function to fetch and render schemes
    async function loadAndDisplaySchemes(cropName, stateName) {
        resultContainer.innerHTML = `
            <div class="panel">
                ${renderEmptyPlaceholder("fa-spinner fa-spin", `Loading government schemes for ${escapeHtml(capitalizeFirstLetter(cropName))} in ${escapeHtml(stateName)}...`)}
            </div>
        `;

        try {
            const data = await fetchApi(`/schemes?crop=${encodeURIComponent(cropName)}&state=${encodeURIComponent(stateName)}`);
            const schemes = data.schemes || [];

            if (!schemes.length) {
                resultContainer.innerHTML = `
                    <div class="panel">
                        ${renderEmptyPlaceholder("fa-circle-info", `No specific government schemes found for ${escapeHtml(capitalizeFirstLetter(cropName))} in ${escapeHtml(stateName)}.`)}
                    </div>
                `;
                return;
            }

            const cardsHtml = schemes.map(s => `
                <div class="card" style="border:1px solid var(--line);background:#fff;border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:0 2px 8px rgba(0,0,0,0.03)">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:10px">
                        <h3 style="margin:0;font-size:1.15rem;color:var(--forest)">
                            <i class="fa-solid fa-award" style="color:var(--fresh);margin-right:8px"></i>${escapeHtml(s.name)}
                        </h3>
                        <span class="badge ${s.level === 'Central' ? 'b-ok' : 'b-ideal'}">
                            ${escapeHtml(s.badge || s.level + ' Scheme')}
                        </span>
                    </div>

                    <p style="margin:0 0 10px 0;font-size:0.95rem;line-height:1.55;color:var(--text)">
                        <b>Financial Assistance / Benefits:</b> ${escapeHtml(s.benefits)}
                    </p>

                    <div style="font-size:0.9rem;color:var(--muted);margin-bottom:14px;line-height:1.45;background:#f9fbf9;border-radius:8px;padding:10px 14px">
                        <div><b>Eligibility:</b> ${escapeHtml(s.eligibility)}</div>
                        <div style="margin-top:6px"><b>How to Apply:</b> ${escapeHtml(s.how_to_apply)}</div>
                    </div>

                    <div style="display:flex;justify-content:flex-end">
                        <a class="btn sm ghost" href="${escapeHtml(s.portal_link)}" target="_blank" rel="noopener noreferrer">
                            Visit Official Portal <i class="fa-solid fa-arrow-up-right-from-square" style="margin-left:4px"></i>
                        </a>
                    </div>
                </div>
            `).join("");

            resultContainer.innerHTML = `
                <div class="panel">
                    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
                        <h2 style="margin:0;font-size:1.35rem">
                            <i class="fa-solid fa-building-columns"></i> ${escapeHtml(capitalizeFirstLetter(cropName))} Schemes for ${escapeHtml(stateName)}
                        </h2>
                        <span class="badge b-ideal">${schemes.length} Schemes Available</span>
                    </div>
                    <p class="note" style="margin-top:6px;margin-bottom:0">
                        Eligible subsidies, financial grants, crop insurance, and farmer support programs for cultivating <b>${escapeHtml(capitalizeFirstLetter(cropName))}</b> in <b>${escapeHtml(stateName)}</b>.
                    </p>
                </div>
                <div class="schemes-list" style="margin-top:16px">
                    ${cardsHtml}
                </div>
            `;
        } catch (err) {
            resultContainer.innerHTML = `
                <div class="panel">
                    <div class="alert bad">
                        <b>Error loading schemes:</b> ${escapeHtml(err.message)}
                    </div>
                </div>
            `;
        }
    }

    // 5. Initial load based on URL or defaults
    await loadAndDisplaySchemes(initialCrop, initialState);

    // 6. Handle form submit for searching other crops / states
    formElement.onsubmit = function (event) {
        event.preventDefault();
        hideStateSuggestions();
        const selectedCrop = cropSelect?.value || "rice";
        const selectedState = stateInput?.value.trim() || "Telangana";
        executeWithLoadingState(submitBtn, async () => {
            await loadAndDisplaySchemes(selectedCrop, selectedState);
        });
    };
};


// ============================================================================
// 5. APPLICATION BOOTSTRAPPER
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
    // Mobile navigation burger menu toggle
    const burgerButton = getElement(".burger");
    if (burgerButton) {
        burgerButton.addEventListener("click", () => {
            const menu = getElement(".menu");
            if (menu) menu.classList.toggle("open");
        });
    }

    // Dropdown menu toggle
    const dropdownButtons = getAllElements(".dd > button");
    dropdownButtons.forEach(btn => {
        btn.addEventListener("click", event => {
            event.currentTarget.parentElement.classList.toggle("open");
        });
    });

    // Initialize controller matching the current page's data-page attribute
    const currentPageName = document.body.dataset.page;
    const controller = pageControllers[currentPageName];

    if (typeof controller === "function") {
        Promise.resolve(controller()).catch(err => {
            console.error(`Error initializing page '${currentPageName}':`, err);
            showToast(err.message, "error");
        });
    }
});
