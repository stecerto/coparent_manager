from django import template

register = template.Library()

@register.filter
def event_color(event_type):
    """Restituisce il colore HEX in base al tipo di evento"""
    colors = {
        'custody': '#6f42c1',      # Viola - Affidamento
        'support': '#198754',      # Verde - Mantenimento
        'school': '#0d6efd',       # Blu - Scuola
        'medical': '#dc3545',      # Rosso - Medico
        'expense': '#ffc107',      # Giallo - Spesa
        'legal': '#fd7e14',        # Arancione - Legale
        'holiday_a': '#20c997',    # Verde acqua - Ferie A
        'holiday_b': '#0dcaf0',    # Ciano - Ferie B
        'child_event': '#d63384',  # Rosa - Evento figlio
        'mediation': '#6610f2',    # Indaco - Mediazione
        'consulting': '#6f42c1',   # Viola - Consulenza
        'other': '#6c757d',        # Grigio - Altro
    }
    return colors.get(event_type, '#6c757d')  # Default grigio