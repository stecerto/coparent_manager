document.addEventListener("DOMContentLoaded", function () {
    const emailInput = document.getElementById("id_email");

    if (emailInput) {
        const emailField = emailInput.parentElement;
        console.log("Email field trovato");
    }
});