from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Recupera un valore da un dizionario nel template"""
    return dictionary.get(key, 0)