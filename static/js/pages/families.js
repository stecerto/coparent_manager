document.addEventListener("DOMContentLoaded", function () {
    function resetChartSelection() {

}
    // =========================
    // STATE
    // =========================
    let chartInstance = null;
    let selectedCategory = null; // 👈 SOLO QUESTA



    // =========================
    // ELEMENTI DOM
    // =========================
    const filter = document.getElementById('childFilter');
    const canvas = document.getElementById('categoryChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');






    // =========================
    // CHART
    // =========================
    function createChart(labels, data, colors) {
    if (!ctx) return;
    if (chartInstance) {
        chartInstance.destroy();
    }


    chartInstance = new Chart(ctx, {
        type: 'pie',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: colors
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },

            onClick: (evt, elements) => {

                if (!elements.length) return;

                const index = elements[0].index;
                const clickedCategory = labels[index];

                // toggle
                if (selectedCategory === clickedCategory) {
                    selectedCategory = null;
                } else {
                    selectedCategory = clickedCategory;
                }

                loadExpenses();
            }
        }
    });

    renderLegend(labels, data, colors);
}

    // =========================
    // LEGEND
    // =========================
    function renderLegend(labels, data, colors) {

    const container = document.getElementById("chartLegend");
    if (!container) return;

    container.innerHTML = "";

    labels.forEach((label, i) => {

        const color = colors[i];

        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.justifyContent = "space-between";
        row.style.alignItems = "center";
        row.style.padding = "4px 0";

        row.innerHTML = `
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="
                    width:12px;
                    height:12px;
                    background:${color};
                    display:inline-block;
                    border-radius:3px;
                "></span>
                <span>${label}</span>
            </div>
            <strong>${data[i]} €</strong>
        `;

        container.appendChild(row);
    });
}

    // =========================
    // LOAD DATA
    // =========================
    function loadExpenses() {

        const childId = filter?.value || "";

        const baseUrl = window.expensesByChildUrl || "/expenses/by-child/";
        const url = new URL(baseUrl, window.location.origin);

        if (childId) url.searchParams.append("child_id", childId);
        if (selectedCategory) url.searchParams.append("category", selectedCategory);

        fetch(url)
            .then(res => res.json())
            .then(data => {

                createChart(data.labels, data.data, data.colors);
                renderTable(data.expenses);
            });
    }

    // =========================
    // TABLE
    // =========================
    function renderTable(expenses) {

        const tbody = document.getElementById("expensesTableBody");
        if (!tbody) return;

        tbody.innerHTML = "";

        expenses.forEach(exp => {

            const row = document.createElement("tr");

            row.innerHTML = `
                <td>${exp.expense_date}</td>
                <td>${exp.expense_type__name}</td>
                <td>${exp.amount} €</td>
                <td>${exp.created_by__username || ""}</td>
                <td>—</td>
            `;

            tbody.appendChild(row);
        });
    }

    // =========================
    // RESET BUTTON
    // =========================
    document.getElementById("resetCategory")?.addEventListener("click", function () {

    selectedCategory = null;

    // reset dropdown
    if (filter) filter.value = "";

    loadExpenses();
});

    // =========================
    // CHILD FILTER
    // =========================
    if (filter) {
        filter.addEventListener("change", function () {
        resetChartSelection();
        loadExpenses();
    });
}


});