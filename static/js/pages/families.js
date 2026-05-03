document.addEventListener('DOMContentLoaded', function() {
    const canvas = document.getElementById('categoryChart');
    const childFilter = document.getElementById('childFilter');
    const resetBtn = document.getElementById('resetCategory');
    const tbody = document.getElementById('expensesTableBody');
    const legendBox = document.getElementById('chartLegend');
    let chartInstance = null;

    const BASE_URLS = {
        api: window.DJANGO_URLS?.expensesByChild || '/expenses/by-child/',
        editBase: window.DJANGO_URLS?.expenseEditBase || '/expenses/edit/',
        deleteBase: window.DJANGO_URLS?.expenseDeleteBase || '/expenses/delete/',
        updateStatusBase: window.DJANGO_URLS?.expenseUpdateStatusBase || '/expenses/update-status/'
    };

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie) {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                cookie = cookie.trim();
                if (cookie.startsWith(name + '=')) {
                    cookieValue = decodeURIComponent(cookie.slice(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function fetchAndRender(childId = '', categoryId = '') {
        const url = `${BASE_URLS.api}?child_id=${childId}&category=${categoryId}`;

        fetch(url)
            .then(res => {
                if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
                return res.json();
            })
            .then(data => {
                // ✅ 0. Aggiorna totale spese
                const totalEl = document.getElementById('totalExpensesDisplay');
                if (totalEl && data.data) {
                    const total = data.data.reduce((a, b) => a + parseFloat(b || 0), 0);
                    totalEl.textContent = total.toFixed(2);
                }

                // ✅ 1. Grafico (SINTASSI CORRETTA CHART.JS)
                if (canvas && data.labels?.length > 0) {
                    if (chartInstance) chartInstance.destroy();
                    chartInstance = new Chart(canvas.getContext('2d'), {
                        type: 'doughnut',
                        data: {  // ✅ CHIAVE "data:" PRESENTE
                            labels: data.labels,
                            datasets: [{
                                data: data.data,  // ✅ CHIAVE "data:" PRESENTE
                                backgroundColor: data.colors,
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { legend: { display: false } }
                        }
                    });
                }

                // ✅ 2. Legenda
                if (legendBox && data.labels) {
                    legendBox.innerHTML = data.labels.map((lbl, i) =>
                        `<span class="badge me-1 mb-1" style="background-color:${data.colors[i] || '#6c757d'}">${lbl}</span>`
                    ).join('');
                }

                // ✅ 3. Tabella con logica is_editable
                if (tbody) {
                    tbody.innerHTML = '';
                    if (data.expenses?.length > 0) {
                        data.expenses.forEach(exp => {
                             const tr = document.createElement('tr');
                             const dateStr = exp.expense_date || '-';
                             const catName = exp.expense_type__display_name || 'N/D';
                             const catColor = exp.expense_type__color || '#6c757d';
                            // ✅ Indicatore stato (SOLO visuale, non cliccabile)
                            const statusIcons = {
                                'pending': '🟡',
                                'accepted': '🔵',
                                'paid': '🟢',
                                'rejected': '🔴'
                            };
                            const statusIcon = statusIcons[exp.status] || '⚪';

                            // Rimossa tutta la logica is_editable e i pulsanti
                            tr.innerHTML = `
                                <td>${dateStr}</td>
                                <td><span class="badge" style="background-color:${catColor}">${catName}</span></td>
                                <td>€ ${parseFloat(exp.amount || 0).toFixed(2)}</td>
                                <td>${exp.created_by_display || '-'}</td>
                                <td>
                                    <span title="Stato: ${exp.status_display}" 
                                          style="font-size: 1.4rem; cursor: default; user-select: none;">
                                        ${statusIcon}
                                    </span>
                                </td>
                            `;
                            tbody.appendChild(tr);
                        });
                    } else {
                        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">Nessuna spesa trovata</td></tr>';
                    }
                }
            })
            .catch(err => {
                console.error('❌ Errore fetchAndRender:', err);
                if (tbody) {
                    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Errore caricamento: ${err.message}</td></tr>`;
                }
            });
    }

    // Event listeners
    if (resetBtn) resetBtn.addEventListener('click', () => {
        if (childFilter) childFilter.value = '';
        fetchAndRender('', '');
    });

    if (childFilter) childFilter.addEventListener('change', () => {
        fetchAndRender(childFilter.value, '');
    });

    // Caricamento iniziale
    fetchAndRender('', '');
});