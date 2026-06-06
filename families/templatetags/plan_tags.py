from django import template
from families.utils import get_lawyer_limits

register = template.Library()

@register.filter(name='get_lawyer_limits')
def get_lawyer_limits_filter(user):
    """
    Filtro template per ottenere i limiti del piano dell'utente.
    Uso: {{ user|get_lawyer_limits }}
    """
    return get_lawyer_limits(user)