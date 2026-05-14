# core/choices.py
from django.db import models

class RoleChoices(models.TextChoices):
    """Ruoli unificati per tutto il progetto"""
    PARENT_A = "parent_a", "Genitore A"
    PARENT_B = "parent_b", "Genitore B"
    LAWYER_A = "lawyer_a", "Avvocato A"
    LAWYER_B = "lawyer_b", "Avvocato B"
    MEDIATOR = "mediator", "Mediatore"
    CONSULTANT = "consultant", "Consulente"

    @classmethod
    def parent_roles(cls):
        """Solo i genitori"""
        return [cls.PARENT_A, cls.PARENT_B]

    @classmethod
    def lawyer_roles(cls):
        """Solo gli avvocati"""
        return [cls.LAWYER_A, cls.LAWYER_B]

    @classmethod
    def all_roles(cls):
        """Tutti i ruoli come lista di tuple (per Django forms/models)"""
        return list(cls.choices)

    @classmethod
    def as_dict(cls):
        """Utile per lookup rapidi: {'parent_a': 'Genitore A', ...}"""
        return dict(cls.choices)

    @classmethod
    def get_available_roles(cls, inviter_role: str, occupied_roles: set) -> list:
        """
        Restituisce i ruoli che un utente può invitare, escludendo quelli già occupati.
        """
        # Mappa: chi può invitare chi
        permissions = {
            cls.PARENT_A: {cls.PARENT_B, cls.LAWYER_A, cls.LAWYER_B, cls.MEDIATOR, cls.CONSULTANT},
            cls.PARENT_B: {cls.PARENT_A, cls.LAWYER_A, cls.LAWYER_B, cls.MEDIATOR, cls.CONSULTANT},
            cls.LAWYER_A: {cls.LAWYER_B, cls.MEDIATOR, cls.CONSULTANT},
            cls.LAWYER_B: {cls.LAWYER_A, cls.MEDIATOR, cls.CONSULTANT},
            cls.MEDIATOR: set(cls.choices),  # Può invitare tutti
            cls.CONSULTANT: set(cls.choices),
        }

        allowed = permissions.get(inviter_role, set())
        return [c for c in cls.choices if c[0] in (allowed - occupied_roles)]