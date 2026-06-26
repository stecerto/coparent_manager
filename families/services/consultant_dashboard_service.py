from django.utils import timezone
from django.db.models import Sum, Count
from datetime import timedelta

from families.models import FamilyMember, ConsultantAssignment
from expenses.models import Expense


def get_consultant_dashboard_stats(user):
    """
    Statistiche specifiche per consulenti:
    - Incarichi attivi (CTU, consulente di parte)
    - Famiglie in consulenza
    - Analisi economiche completate
    - Report generati
    """
    # Incarichi attivi
    active_assignments = ConsultantAssignment.objects.filter(
        consultant=user,
        is_active=True
    ).select_related('family')

    family_ids = [a.family_id for a in active_assignments]

    if not family_ids:
        return {
            'active_assignments': 0,
            'active_families': 0,
            'total_analyzed': 0,
            'reports_generated': 0,
        }

    # Totale spese analizzate (somma di tutte le spese delle famiglie in consulenza)
    total_analyzed = Expense.objects.filter(
        family_id__in=family_ids,
        is_active=True
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Report generati (documenti di tipo report)
    from documents.models import Document
    reports = Document.objects.filter(
        family_id__in=family_ids,
        document_type='report',
        is_active=True
    ).count()

    return {
        'active_assignments': active_assignments.count(),
        'active_families': len(family_ids),
        'total_analyzed': total_analyzed,
        'reports_generated': reports,
    }


def get_consultant_active_assignments(user):
    """Incarichi di consulenza attivi con dettagli"""
    assignments = ConsultantAssignment.objects.filter(
        consultant=user,
        is_active=True
    ).select_related('family').order_by('-start_date')

    return [
        {
            'family': a.family.name,
            'family_id': a.family.id,
            'assignment_type': a.get_assignment_type_display(),
            'start_date': a.start_date,
            'end_date': a.end_date,
            'notes': a.notes,
        }
        for a in assignments
    ]