# core/choices.py
from django.db import models

class RoleChoices(models.TextChoices):
    # ✅ RUOLI GENERICI (per UserProfile e registrazione)
    PARENT = 'parent', 'Genitore'
    LAWYER = 'lawyer', 'Avvocato'
    MEDIATOR = 'mediator', 'Mediatore'
    CONSULTANT = 'consultant', 'Consulente'
    SPOUSE = 'spouse', 'Coniuge'

    # ✅ RUOLI SPECIFICI (per FamilyMember, assegnati all'invito)
    PARENT_A = 'parent_a', 'Genitore A'
    PARENT_B = 'parent_b', 'Genitore B'
    LAWYER_A = 'lawyer_a', 'Avvocato A (del Genitore A)'
    LAWYER_B = 'lawyer_b', 'Avvocato B (del Genitore B)'

    @classmethod
    def is_spouse(cls, role):
        return cls.normalize_role(role) == cls.SPOUSE

    @classmethod
    def normalize_role(cls, role):
        """Normalizza il ruolo rimuovendo suffissi _a/_b"""
        if not role:
            return ''
        role_str = str(role).strip().lower()
        # Gestisce sia stringhe che enum
        if hasattr(role_str, 'value'):
            role_str = role_str.value
        return role_str.replace('_a', '').replace('_b', '')

    @classmethod
    def is_lawyer(cls, role):
        return cls.normalize_role(role) == cls.LAWYER

    @classmethod
    def is_mediator(cls, role):
        return cls.normalize_role(role) == cls.MEDIATOR

    @classmethod
    def is_consultant(cls, role):
        return cls.normalize_role(role) == cls.CONSULTANT

    @classmethod
    def is_professional(cls, role):
        return role in [cls.LAWYER, cls.MEDIATOR, cls.CONSULTANT,
                        cls.LAWYER_A, cls.LAWYER_B, cls.MEDIATOR, cls.CONSULTANT]
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


# ✅ NUOVO: Scelte per il tipo di incarico del consulente
class AssignmentTypeChoices(models.TextChoices):
    INDIVIDUAL = 'individual', 'Individuale (su richiesta di un singolo genitore)'
    FAMILY = 'family', 'Familiare (accordo congiunto tra i genitori)'
    CTU = 'ctu', 'CTU (Consulente Tecnico d\'Ufficio - Nomina Tribunale)'