document.addEventListener("DOMContentLoaded", function () {
    console.log("🚀 Setup JS caricato");

    const addBtn = document.getElementById("add-child");
    const container = document.getElementById("children-forms");

    // ✅ FIX 1: Usa 'child' (singolare) per matchare prefix="child" nella view Django
    const totalForms = document.getElementById("id_child-TOTAL_FORMS");
    const emptyTemplate = document.getElementById("empty-form-template");

    if (!addBtn || !container || !totalForms || !emptyTemplate) {
        console.error("❌ Elementi formset non trovati");
        return;
    }

    let formCount = parseInt(totalForms.value) || 0;

    // ======================
    // ➕ AGGIUNGI FIGLIO
    // ======================
    addBtn.addEventListener("click", function () {
        console.log(`➕ Aggiungo figlio #${formCount}`);

        // ✅ FIX 2: Sostituzione corretta del prefisso (singolare)
        let newForm = emptyTemplate.innerHTML
            .replace(/child-__prefix__/g, `child-${formCount}`);  // Sostituisce sia name che id

        // Inserisci nel container
        container.insertAdjacentHTML("beforeend", newForm);

        // ✅ FIX 3: Incrementa il contatore (era -- invece di ++)
        totalForms.value = ++formCount;

        // ✅ FIX 4: Inizializza il calcolo % per il nuovo form appena aggiunto
        const newInputs = container.querySelectorAll('[name$="-contribution_pct_parent_a"]');
        if (newInputs.length > 0) {
            syncPercentages(newInputs[newInputs.length - 1]);
        }

        // Scroll al nuovo form
        const newFormEl = container.lastElementChild;
        newFormEl?.scrollIntoView({ behavior: "smooth", block: "center" });
    });

    // ======================
    // 🗑️ RIMUOVI FIGLIO (Soft Delete Django)
    // ======================
    container.addEventListener("click", function (e) {
        if (e.target.closest(".remove-child")) {
            const btn = e.target.closest(".remove-child");
            const form = btn.closest(".child-form");
            if (!form) return;

            const deleteInput = form.querySelector("input[name$='-DELETE']");
            const idInput = form.querySelector("input[name$='-id']");

            if (deleteInput) {
                if (idInput?.value) {
                    // Figlio esistente → soft delete
                    deleteInput.checked = true;
                    form.style.opacity = "0.6";
                    form.style.pointerEvents = "none";
                    btn.textContent = "✅ Rimosso";
                    btn.disabled = true;
                    console.log("🗑️ Figlio esistente marcato per eliminazione");
                } else {
                    // Figlio nuovo → rimuovi dal DOM e decrementa
                    form.remove();
                    totalForms.value = --formCount;
                    console.log("🗑️ Figlio nuovo rimosso dal DOM");
                }
            }
        }
    });

    // ======================
    // 📊 CALCOLO PERCENTUALE LIVE (UNICA FUNZIONE - Event Delegation)
    // ======================
    function syncPercentages(inputEl) {
        const formWrapper = inputEl.closest(".child-form");
        if (!formWrapper) return;

        const displayA = formWrapper.querySelector(".pctA_display");
        const displayB = formWrapper.querySelector(".pctB_display");
        const overrideInput = inputEl; // Questo è ora override_split_pct

        // ✅ Parsing robusto: gestisce input vuoti, virgole, valori non numerici
        let raw = inputEl.value ? inputEl.value.toString().trim().replace(',', '.') : "";
        let valA = parseFloat(raw);
        if (isNaN(valA) || valA < 0 || valA > 100) valA = 50;
        valA = Math.max(0, Math.min(100, valA));
        overrideInput.value = ''; // Pulisci l'override se invalido

        const valB = 100 - valA;
        // Fallback sicuro
        // Se vuoto o invalido, usa il valore dall'accordo (nascosto)
        const defaultVal = parseFloat(formWrapper.querySelector('[name$="-agreement_default"]')?.value || '50');

        if (displayA) displayA.textContent = valA.toFixed(2) + "%";
        if (displayB) {
            displayB.textContent = valB.toFixed(2) + "%";
            displayB.className = `pctB_display fw-bold ${valB >= 0 ? "text-success" : "text-danger"}`;
        }

    // ✅ AGGIUNGI QUESTA RIGA: forza il valore nell'input HTML prima del submit
        inputEl.value = valA.toFixed(2);
    }


    // Listener per l'input di override
    container.addEventListener("input", function(e) {
        if (e.target.matches('[name$="-override_split_pct"]')) {
            syncPercentages(e.target);
        }
    });

    // Inizializzazione al caricamento
    container.querySelectorAll('[name$="-override_split_pct"]').forEach(syncPercentages);

    // ======================
    // 🧹 PULIZIA FORM VUOTI PRIMA DEL SUBMIT
    // ======================
    document.querySelector("form")?.addEventListener("submit", function () {
        const forms = container.querySelectorAll(".child-form");

        forms.forEach(form => {
            const idInput = form.querySelector("input[name$='-id']");
            const deleteInput = form.querySelector("input[name$='-DELETE']");

            // Controlla se il form è vuoto (esclusi hidden e DELETE)
            let isEmpty = true;
            form.querySelectorAll("input:not([type='hidden']):not([name$='-DELETE']), textarea, select").forEach(field => {
                if (field.value.trim() !== "") isEmpty = false;
            });

            if (isEmpty) {
                if (idInput?.value) {
                    // Figlio esistente vuoto → marca per delete
                    if (deleteInput) deleteInput.checked = true;
                    form.style.display = "none";
                    console.log("🟡 Figlio esistente vuoto → marcato DELETE");
                } else {
                    // Figlio nuovo vuoto → rimuovi e aggiorna counter
                    form.remove();
                    totalForms.value = --formCount;
                    console.log("🗑️ Figlio nuovo vuoto → rimosso");
                }
            }
        });
    });

    console.log("✅ Setup JS inizializzato correttamente");
});

document.addEventListener('DOMContentLoaded', function() {
    // Seleziona tutti i campi del form
    const fields = document.querySelectorAll('.form-control, .form-select');

    // Funzione per verificare se un campo è "completo"
    function isFieldComplete(field) {
        const value = field.value.trim();
        // Per checkbox/radio: controlla se sono selezionati
        if (field.type === 'checkbox' || field.type === 'radio') {
            return field.checked;
        }
        // Per select: controlla che non sia il placeholder
        if (field.tagName === 'SELECT') {
            return value && value !== field.querySelector('option[value=""]')?.value;
        }
        // Per text/email/tel/etc: controlla che non sia vuoto
        return value.length > 0;
    }

    // Applica/rimuovi la classe in base allo stato
    function updateFieldStyle(field) {
        if (isFieldComplete(field)) {
            field.classList.add('profile-complete');
        } else {
            field.classList.remove('profile-complete');
        }
    }

    // Inizializza tutti i campi
    fields.forEach(field => {
        updateFieldStyle(field);
        // Aggiungi listener per aggiornamenti in tempo reale
        field.addEventListener('input', () => updateFieldStyle(field));
        field.addEventListener('change', () => updateFieldStyle(field));
        field.addEventListener('blur', () => updateFieldStyle(field));
    });

    // Bonus: evidenzia il campo attivo con un focus più visibile
    fields.forEach(field => {
        field.addEventListener('focus', function() {
            this.style.boxShadow = '0 0 0 3px rgba(40, 167, 69, 0.25)';
        });
        field.addEventListener('blur', function() {
            this.style.boxShadow = '';
            updateFieldStyle(this); // Riapplica lo stato dopo il blur
        });
    });
});
