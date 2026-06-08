// static/js/sw.js


// Installazione
self.addEventListener('install', (event) => {
    console.log('Service Worker installato');
    self.skipWaiting(); // Attiva immediatamente
});

// Attivazione
self.addEventListener('activate', (event) => {
    console.log('Service Worker attivato');
    event.waitUntil(clients.claim()); // Diventa immediatamente il controller
});

// Gestione notifiche push
self.addEventListener('push', (event) => {
    if (!event.data) return;

    const data = event.data.json();

    // Mostra notifica di sistema
    event.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.message,
            icon: '/static/img/logo_coparent.png', // Cambia con il tuo logo
            badge: '/static/img/logo_coparent.png',
            data: { url: data.url || '/' },
            vibrate: [200, 100, 200],
            tag: 'notification-' + data.id // Evita duplicati
        })
    );

    // Aggiorna badge app
    if ('setAppBadge' in self.registration) {
        self.registration.setAppBadge(data.badge_count || 1);
    }
});

// Click su notifica
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    const urlToOpen = event.notification.data?.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
            // Se c'è già una finestra aperta, focalizzala
            for (let client of windowClients) {
                if (client.url.includes(urlToOpen) && 'focus' in client) {
                    return client.focus();
                }
            }
            // Altrimenti apri una nuova finestra
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});