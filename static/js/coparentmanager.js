document.addEventListener("DOMContentLoaded", function () {

    console.log("JS caricato correttamente");

    // ==============================
    // VALIDAZIONE IMPORTO
    // ==============================
    const amount = document.getElementById("id_amount");

    if (amount) {
        amount.addEventListener("input", () => {
            if (parseFloat(amount.value) < 0) {
                alert("Importo non valido");
                amount.value = "";
            }
        });
    }
    });



