// 🎯 Smooth Scroll per link interni
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href === '#' || href === '#demo') return;

        e.preventDefault();
        const target = document.querySelector(href);
        if (target) {
            const offset = 80; // Altezza navbar
            const targetPosition = target.offsetTop - offset;

            window.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });

            // Chiudi menu mobile se aperto
            const navbarCollapse = document.querySelector('.navbar-collapse');
            if (navbarCollapse.classList.contains('show')) {
                const bsCollapse = new bootstrap.Collapse(navbarCollapse);
                bsCollapse.hide();
            }
        }
    });
});

// 🎭 Animazione fade-in per sezioni
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('fade-in');
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

// Osserva tutte le sezioni
document.querySelectorAll('section').forEach(section => {
    observer.observe(section);
});

// 📊 Tracking CTA clicks (placeholder per analytics)
document.querySelectorAll('a[href*="register"]').forEach(link => {
    link.addEventListener('click', function() {
        console.log('CTA clicked:', this.textContent.trim());
        // Qui puoi aggiungere Google Analytics o altro
        // gtag('event', 'cta_click', { 'event_category': 'conversion' });
    });
});

// 🎨 Navbar background on scroll
window.addEventListener('scroll', function() {
    const navbar = document.querySelector('.navbar');
    if (window.scrollY > 50) {
        navbar.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
    } else {
        navbar.style.boxShadow = '0 1px 3px rgba(0,0,0,0.1)';
    }
});