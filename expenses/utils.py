# expenses/utils.py
from decimal import Decimal


def get_expense_shares(expense):
    """
    Calcola le quote della spesa leggendo la percentuale dal figlio collegato.
    Fallback: 50/50 se manca il figlio o la %.
    Returns: (quota_a, quota_b) come Decimal
    """
    child = getattr(expense, 'child', None)
    pct_a = Decimal("50.00")

    if child and child.contribution_pct_parent_a is not None:
        pct_a = child.contribution_pct_parent_a
        # Protezione contro valori >100 nel DB
        if pct_a > Decimal("100"):
            pct_a = Decimal("50.00")

    pct_b = Decimal("100") - pct_a
    amount = expense.amount or Decimal("0.00")

    share_a = amount * (pct_a / Decimal("100"))
    share_b = amount * (pct_b / Decimal("100"))
    return share_a.quantize(Decimal("0.01")), share_b.quantize(Decimal("0.01"))

def calculate_maintenance(user, children=None):
    """
    Placeholder per calcolo mantenimento.
    Da rifattorizzare sul nuovo modello Family.
    """
    return {}


    amount_float = float(amount or 0)
    quota_a = round(amount_float * (pct_a / 100), 2)
    quota_b = round(amount_float * (pct_b / 100), 2)

    return quota_a, quota_b
