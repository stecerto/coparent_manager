document.addEventListener('DOMContentLoaded', function() {
    console.log("🗓️ Calendar JS caricato");

    const calendarEl = document.getElementById('calendar');
    if (!calendarEl) {
        console.error("❌ Elemento #calendar non trovato");
        return;
    }

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'it',
        height: 650,
        editable: true,
        selectable: true,
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },

        // 📡 EVENTI DAL BACKEND
        events: "/calendar/events-json/",

        // ➕ CREAZIONE EVENTO (click su giorno)
        select: function(info) {
            // FullCalendar invia date ISO con timezone: "2026-05-17T00:00:00+02:00"
            const start = info.startStr.split('+')[0]; // Rimuovi timezone per il form
            const end = info.endStr ? info.endStr.split('+')[0] : start;

            window.location.href = `/calendar/event/create/?start=${start}&end=${end}`;
        },

        // ✏️ MODIFICA EVENTO (click evento)
        eventClick: function(info) {
            window.location.href = `/calendar/event/${info.event.id}/edit/`;
        },

        // 🔁 DRAG & DROP - Aggiorna date + mantieni children
        eventDrop: function(info) {
            updateEvent(info.event, { only_dates: true });
        },

        // 🔁 RESIZE EVENTO
        eventResize: function(info) {
            updateEvent(info.event, { only_dates: true });
        },

        // 🎨 COLORI + TOOLTIP CON NOMI FIGLI
        eventDidMount: function(info) {
            const eventType = info.event.extendedProps.event_type;
            const children = info.event.extendedProps.children || [];

            // ✅ Colori allineati al modello CalendarEvent.EVENT_TYPES
            const colors = {
                custody: "#6f42c1",    // Viola: Affidamento
                school: "#0d6efd",      // Blu: Scuola
                medical: "#198754",     // Verde: Medico
                expense: "#ffc107",     // Giallo: Spesa
                legal: "#dc3545",       // Rosso: Legale
                other: "#6c757d"        // Grigio: Altro
            };

            const color = colors[eventType] || "#6c757d";
            info.el.style.backgroundColor = color;
            info.el.style.borderColor = color;
            info.el.style.color = "#fff";

            // ✅ Tooltip con nomi figli (se presenti)
            if (children.length > 0) {
                info.el.title = `Figli: ${children.join(", ")}`;
            }

            // Badge figli nell'evento (opzionale, più visibile)
            if (children.length > 0) {
                const badge = document.createElement('span');
                badge.className = 'fc-event-badge';
                badge.textContent = `👶 ${children.length}`;
                badge.style.cssText = 'font-size:0.7em; margin-left:4px; background:rgba(255,255,255,0.3); padding:2px 4px; border-radius:4px;';
                info.el.querySelector('.fc-event-title').appendChild(badge);
            }
        }
    });

    calendar.render();

    // 📤 UPDATE EVENT (drag&drop / resize)
    function updateEvent(event, options = {}) {
        const { only_dates = false } = options;

        // ✅ Formattazione timezone-aware per Django
        function formatDateTime(date) {
            // Converte Date JS in ISO string con timezone
            return date.toISOString();
        }

        const formData = new FormData();
        formData.append("title", event.title);
        formData.append("start_time", formatDateTime(event.start));
        formData.append("end_time", formatDateTime(event.end || event.start));

        // ✅ Se non è solo aggiornamento date, invia anche altri campi
        if (!only_dates) {
            formData.append("description", event.extendedProps.description || "");
            formData.append("event_type", event.extendedProps.event_type || "other");

            // ✅ Invia children se presenti nell'evento
            const children = event.extendedProps.children || [];
            children.forEach(childName => {
                // Nota: qui dovresti inviare ID, non nomi.
                // Se il backend lo richiede, mappa nome→ID o invia solo per update completo.
                // Per drag&drop, di solito si mantengono i children esistenti → backend gestisce.
            });
        }

        fetch(`/calendar/event/${event.id}/update/`, {
            method: "POST",
            body: formData,
            headers: {
                "X-CSRFToken": getCSRFToken()
            }
        })
        .then(res => {
            if (!res.ok) {
                console.error("❌ Update failed:", res.status);
                // Opzionale: revert del drag&drop se fallisce
                // info.revert(); // se chiamato da eventDrop/eventResize
            } else {
                console.log("✅ Evento aggiornato");
            }
        })
        .catch(err => console.error("❌ Fetch error:", err));
    }

    // 🔐 CSRF TOKEN helper (più affidabile dei cookie)
    function getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        if (token) return token;

        // Fallback: cerca nei cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') return decodeURIComponent(value);
        }
        return null;
    }
});

// 💾 SAVE MODAL (se usi modale invece di form classico)
document.getElementById("saveEvent")?.addEventListener("click", function() {
    const id = document.getElementById("eventId")?.value;
    if (!id) return;

    const formData = new FormData();
    formData.append("title", document.getElementById("modalTitle").value);
    formData.append("description", document.getElementById("modalDescription").value);
    formData.append("start_time", document.getElementById("modalStart").value);
    formData.append("end_time", document.getElementById("modalEnd").value);
    formData.append("event_type", document.getElementById("modalEventType")?.value || "other");

    // ✅ Invia children selezionati (come ID)
    const childrenSelect = document.getElementById("modalChildren");
    if (childrenSelect) {
        for (let opt of childrenSelect.selectedOptions) {
            formData.append("children", opt.value);
        }
    }

    fetch(`/calendar/event/${id}/update/`, {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": getCSRFToken() }
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Aggiorna calendario e chiudi modale
            const calendar = FullCalendar.Calendar.getInstance(document.getElementById('calendar'));
            calendar?.refetchEvents();
            bootstrap.Modal.getInstance(document.getElementById('eventModal'))?.hide();
        } else {
            alert("❌ Errore: " + (data.error || "Aggiornamento fallito"));
        }
    })
    .catch(err => {
        console.error("❌ Fetch error:", err);
        alert("❌ Errore di connessione");
    });
});

// 🗑 DELETE EVENT
document.getElementById("deleteEvent")?.addEventListener("click", function(e) {
    e.preventDefault();
    const id = document.getElementById("eventId")?.value;
    if (!id || !confirm("Eliminare definitivamente questo evento?")) return;

    fetch(`/calendar/event/${id}/delete/`, {
        method: "POST",
        headers: { "X-CSRFToken": getCSRFToken() }
    })
    .then(res => {
        if (res.ok) {
            window.location.href = "/calendar/";
        } else {
            alert("❌ Eliminazione fallita");
        }
    });
});

// ➕ CREATE EVENT (form classico - se non usi modale)
document.getElementById("eventForm")?.addEventListener("submit", function(e) {
    // Il form classico Django fa submit normale, non serve fetch
    // Se vuoi AJAX, decommenta sotto:
    /*
    e.preventDefault();
    const formData = new FormData(this);

    fetch("", {
        method: "POST",
        body: formData,
        headers: { "X-Requested-With": "XMLHttpRequest" }
    })
    .then(res => {
        if (res.redirected) {
            window.location.href = res.url;
        }
    });
    */
});