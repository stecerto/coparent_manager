# core/templatetags/dict_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Permette di fare dictionary[key] nei template Django"""
    return dictionary.get(key)

'''
come usarlo nei template per fare get_item:family.id

{% load dict_extras %}

{# Ora puoi fare: #}
{% with client=assigned_parents|get_item:family.id %}

'''