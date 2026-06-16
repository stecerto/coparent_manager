from django import template

register = template.Library()


@register.filter
def get_child_color(child):
    """Assegna un colore Bootstrap coerente in base all'ID del figlio"""
    # Lista di colori Bootstrap validi per i bordi
    colors = ['primary', 'success', 'info', 'warning', 'danger', 'dark', 'secondary']

    # Usa l'ID del figlio per scegliere un colore in modo deterministico
    # Se non ha ID (es. nuovo oggetto), usa 0
    child_id = getattr(child, 'id', 0) or 0

    return colors[child_id % len(colors)]