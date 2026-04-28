
document.addEventListener("DOMContentLoaded", function () {
console.log("expenses_dashboard JS caricato");
    // =========================
    // CATEGORY CHART
    // =========================

    const c1 = document.getElementById("categoryChart");

    if (c1 && window.categoryChartData) {
        if (window.categoryChartInstance) {
            window.categoryChartInstance.destroy();
        }
        if (!c1) return;
        window.categoryChartInstance = new Chart(c1.getContext("2d"), {
            type: "pie",
            data: window.categoryChartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    // =========================
    // PARENT CHART
    // =========================

    const c2 = document.getElementById("parentChart");

    if (c2 && window.parentChartData) {
        if (window.parentChartInstance) {
            window.parentChartInstance.destroy();
        }
        if (!c2) return;
        window.parentChartInstance = new Chart(c2.getContext("2d"), {
            type: "doughnut",
            data: window.parentChartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false // 🔥 importante anche qui
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.label + ": " + context.raw + " €";
                            }
                        }
                    }
                }
            }
        });
    }

    // =========================
    // CALENDAR
    // =========================

    const calendarEl = document.getElementById("calendar");

    if (calendarEl) {
        const calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: "dayGridMonth",
            locale: "it",
            height: 500,
            events: "/expenses/api/expenses-calendar/",

            dateClick: function (info) {
                fetch(`/expenses/day/${info.dateStr}/`)
                    .then(res => res.text())
                    .then(html => {
                        document.getElementById("modalContent").innerHTML = html;
                        document.getElementById("dayModal").style.display = "flex";
                    });
            },

            eventContent: function (arg) {
                const color = arg.event.extendedProps.color;
                const status = arg.event.extendedProps.status;



                return {
                    html: `
                        <div 
                            class="expense-dot"
                            style="background:${color || 'gray'};"
                            title="${arg.event.title}">
                        </div>
                    `
                };
            },

            eventDidMount: function (info) {
                info.el.style.backgroundColor = "transparent";
                info.el.style.border = "none";
            }
        });

        calendar.render();
    }



    // =========================
    // 🔄 STATUS UPDATE (AJAX)
    // =========================

    document.querySelectorAll(".status-btn").forEach(btn => {
        btn.addEventListener("click", function () {

            const expenseId = this.dataset.id;
            const newStatus = this.dataset.status;
            const csrfToken = document.getElementById("csrfToken").value;

            fetch(`/expenses/${expenseId}/update-status/`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify({status: newStatus})
            })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {

                        const row = this.closest("tr");

                        row.querySelectorAll(".status-btn").forEach(b => {
                            b.classList.remove("active");
                        });

                        this.classList.add("active");
                    }
                });

        });
    });
    

    // =========================
    // ❌ MODAL CLOSE
    // =========================


});