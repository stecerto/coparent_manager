document.addEventListener("DOMContentLoaded", function () {

    const addBtn = document.getElementById("add-child");
    const container = document.getElementById("children-forms");
    const totalForms = document.getElementById("id_children-TOTAL_FORMS");

    if (!addBtn || !container || !totalForms) return;

    // ======================
    // AGGIUNGI
    // ======================
    addBtn.addEventListener("click", function () {

        addBtn.style.display = "none"; // 🔥 sparisce

        let formCount = parseInt(totalForms.value);

        const empty = document.getElementById("empty-form-template");
        let newForm = empty.innerHTML.replace(/__prefix__/g, formCount);

        container.insertAdjacentHTML("beforeend", newForm);

        totalForms.value = formCount + 1;
    });

    // ======================
    // DELETE (vero Django)
    // ======================
    container.addEventListener("click", function (e) {

        if (e.target.classList.contains("remove-child")) {

            const form = e.target.closest(".child-form");
            if (!form) return;

            const deleteInput = form.querySelector("input[name$='-DELETE']");

            if (deleteInput) {
                deleteInput.checked = true; // 🔥 fondamentale Django
                form.style.display = "none";
            }
        }
    });

    // ======================
    // SUBMIT
    // ======================
    const form = document.querySelector("form");

    if (form) {
        form.addEventListener("submit", function () {
            addBtn.style.display = "block"; // 🔥 riappare
        });
    }



    // ==============================
    // RIMUOVI FORM VUOTI PRIMA DEL SUBMIT
    // ==============================
    const formElement = document.querySelector("form");

    if (formElement) {
        formElement.addEventListener("submit", function () {
            const forms = container.querySelectorAll(".child-form");

            forms.forEach(form => {
                const idInput = form.querySelector("input[name$='-id']");
                const deleteInput = form.querySelector("input[name$='-DELETE']");
                let empty = true;

                form.querySelectorAll("input:not([type='hidden']), textarea, select").forEach(input => {
                    if (input.value.trim() !== "") empty = false;
                });

                if (empty) {
                    if (idInput && idInput.value) {
                        // Figlio salvato vuoto -> marca DELETE
                        if (deleteInput) deleteInput.value = "on";
                        form.style.display = "none";
                        console.log("🟡 Figlio salvato vuoto marcato per DELETE");
                    } else {
                        // Figlio nuovo vuoto -> rimuovi
                        form.remove();
                        totalForms.value = parseInt(totalForms.value) - 1;
                        console.log("🗑️ Figlio nuovo vuoto rimosso");
                    }
                }
            });
        });
    }

});
