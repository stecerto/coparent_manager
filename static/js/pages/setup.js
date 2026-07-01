document.addEventListener("DOMContentLoaded", function () {
    console.log("🚀 Setup JS caricato");

    // =========================
    // 📊 PERCENTUALI FIGLI (FIXED)
    // =========================
    function syncPercentages(inputEl) {
        const wrapper = inputEl.closest(".child-form");
        if (!wrapper) return;

        const displayA = wrapper.querySelector(".pctA_display");
        const displayB = wrapper.querySelector(".pctB_display");

        let raw = (inputEl.value || "").toString().trim().replace(",", ".");
        let valA = parseFloat(raw);

        if (isNaN(valA)) valA = 50;
        valA = Math.max(0, Math.min(100, valA));

        const valB = 100 - valA;

        if (displayA) displayA.textContent = valA.toFixed(2) + "%";
        if (displayB) {
            displayB.textContent = valB.toFixed(2) + "%";
            displayB.className =
                "pctB_display fw-bold " + (valB >= 0 ? "text-success" : "text-danger");
        }

        inputEl.value = valA.toFixed(2);
    }

    // Event delegation (FIX: niente container undefined)
    document.addEventListener("input", function (e) {
        if (e.target.matches('[name$="-override_split_pct"]')) {
            syncPercentages(e.target);
        }
    });

    // init iniziale
    document
        .querySelectorAll('[name$="-override_split_pct"]')
        .forEach(syncPercentages);

    // =========================
    // 🧹 STILE CAMPI FORM
    // =========================
    const fields = document.querySelectorAll(".form-control, .form-select");

    function isFieldComplete(field) {
        const value = field.value.trim();

        if (field.type === "checkbox" || field.type === "radio") {
            return field.checked;
        }

        if (field.tagName === "SELECT") {
            return value && value !== "";
        }

        return value.length > 0;
    }

    function updateFieldStyle(field) {
        if (isFieldComplete(field)) {
            field.classList.add("profile-complete");
        } else {
            field.classList.remove("profile-complete");
        }
    }

    fields.forEach(field => {
        updateFieldStyle(field);

        field.addEventListener("input", () => updateFieldStyle(field));
        field.addEventListener("change", () => updateFieldStyle(field));

        field.addEventListener("focus", function () {
            this.style.boxShadow = "0 0 0 3px rgba(40, 167, 69, 0.25)";
        });

        field.addEventListener("blur", function () {
            this.style.boxShadow = "";
            updateFieldStyle(this);
        });
    });
});