document.addEventListener('DOMContentLoaded', function() {

    const calendarEl = document.getElementById('calendar');

    if (!calendarEl) {
        console.error("Calendar element not found");
        return;
    }

    const calendar = new FullCalendar.Calendar(calendarEl, {

        initialView: 'dayGridMonth',
        locale: 'it',
        height: 650,
        editable: true,
        selectable: true,

        // 📡 EVENTI DAL BACKEND
        events: "/calendar/events-json/",

        // ➕ CREAZIONE EVENTO (click su giorno)
        select: function(info) {

            let start = info.startStr;
            let end = info.endStr || info.startStr;

            window.location.href =
                `/calendar/event/create/?start=${start}&end=${end}`;
        },

        // ✏️ MODIFICA EVENTO (click evento)
        eventClick: function(info) {

            window.location.href =
                `/calendar/event/${info.event.id}/edit/`;
        },

        // 🔁 DRAG & DROP
        eventDrop: function(info) {
            updateEvent(info.event);
        },

        // 🔁 RESIZE EVENTO
        eventResize: function(info) {
            updateEvent(info.event);
        },

        // 🎨 COLORI PER CATEGORIA (PUNTO 4)
        eventDidMount: function(info) {

            const type = info.event.extendedProps.type;

            const colors = {
                expense: "#e74a3b",   // rosso
                medical: "#4e73df",   // blu
                school: "#f6c23e",    // giallo
                sport: "#1cc88a",     // verde
                legal: "#858796",     // grigio
                other: "#36b9cc"      // azzurro
            };

            const color = colors[type] || "#999";

            info.el.style.backgroundColor = color;
            info.el.style.borderColor = color;
            info.el.style.color = "#fff";
        }
    });

    calendar.render();

    // 📤 UPDATE EVENT (drag & drop / resize)
    function updateEvent(event) {

        function formatDate(date) {
            let pad = n => n.toString().padStart(2, '0');

            return date.getFullYear() + '-' +
                pad(date.getMonth() + 1) + '-' +
                pad(date.getDate()) + 'T' +
                pad(date.getHours()) + ':' +
                pad(date.getMinutes());
        }

        let formData = new FormData();

        formData.append("title", event.title);
        formData.append("start_time", formatDate(event.start));
        formData.append("end_time", formatDate(event.end || event.start));

        fetch(`/calendar/event/${event.id}/update/`, {
            method: "POST",
            body: formData,
            headers: {
                "X-CSRFToken": getCSRFToken()
            }
        })
        .then(res => {
            if (!res.ok) {
                console.error("Update failed");
            }
        });
    }

    // 🔐 CSRF TOKEN helper
    function getCSRFToken() {
        let cookieValue = null;

        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');

            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();

                if (cookie.substring(0, 10) === 'csrftoken=') {
                    cookieValue = decodeURIComponent(cookie.substring(10));
                    break;
                }
            }
        }

        return cookieValue;
    }

});

    // 💾 SAVE MODAL
    document.getElementById("saveEvent").addEventListener("click", function() {

        let id = document.getElementById("eventId").value;

        let formData = new FormData();
        formData.append("title", document.getElementById("modalTitle").value);
        formData.append("description", document.getElementById("modalDescription").value);
        formData.append("start_time", document.getElementById("modalStart").value);
        formData.append("end_time", document.getElementById("modalEnd").value);

        let selected = document.getElementById("modalChildren").selectedOptions;
        for (let opt of selected) {
            formData.append("children", opt.value);
        }

        fetch(`/calendar/event/${id}/update/`, {
            method: "POST",
            body: formData,
            headers: {
                "X-CSRFToken": "{{ csrf_token }}"
            }
        })
        .then(() => {
            calendar.refetchEvents();
            bootstrap.Modal.getInstance(document.getElementById('eventModal')).hide();
        });
    });

    // 🗑 DELETE EVENT
    document.getElementById("deleteEvent").addEventListener("click", function(e) {
    e.preventDefault();

    let id = document.getElementById("eventId").value;

    if (!confirm("Eliminare evento?")) return;

    fetch(`/calendar/event/${id}/delete/`, {
        method: "POST",
        headers: {
            "X-CSRFToken": "{{ csrf_token }}"
        }
    })
    .then(res => res.json())
    .then(() => {
        window.location.href = "/calendar/";
    });
});


    // ➕ CREATE EVENT (form classico)
    document.getElementById("eventForm").addEventListener("submit", function(e) {
        e.preventDefault();

        let form = this;
        let formData = new FormData(form);

        fetch("", {
            method: "POST",
            body: formData
        })
        .then(() => {
            calendar.refetchEvents();
            form.reset();
        });

});
