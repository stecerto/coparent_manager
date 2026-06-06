# core/choices.py
from django.db import models

class RoleChoices(models.TextChoices):
    # ✅ RUOLI GENERICI (per UserProfile e registrazione)
    PARENT = 'parent', 'Genitore'
    LAWYER = 'lawyer', 'Avvocato'
    MEDIATOR = 'mediator', 'Mediatore'
    CONSULTANT = 'consultant', 'Consulente'

    # ✅ RUOLI SPECIFICI (per FamilyMember, assegnati all'invito)
    PARENT_A = 'parent_a', 'Genitore A'
    PARENT_B = 'parent_b', 'Genitore B'
    LAWYER_A = 'lawyer_a', 'Avvocato A (del Genitore A)'
    LAWYER_B = 'lawyer_b', 'Avvocato B (del Genitore B)'
    MEDIATOR_A = 'mediator_a', 'Mediatore A'
    MEDIATOR_B = 'mediator_b', 'Mediatore B'
    CONSULTANT_A = 'consultant_a', 'Consulente A'
    CONSULTANT_B = 'consultant_b', 'Consulente B'

    @classmethod
    def is_professional(cls, role):
        return role in [cls.LAWYER, cls.MEDIATOR, cls.CONSULTANT,
                        cls.LAWYER_A, cls.LAWYER_B, cls.MEDIATOR_A, cls.MEDIATOR_B, cls.CONSULTANT_A, cls.CONSULTANT_B]
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