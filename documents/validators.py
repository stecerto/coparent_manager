# documents/validators.py
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat

# Limiti in MB
LIMIT_RICEVUTE = 1.5 * 1024 * 1024  # 1.5 MB
LIMIT_IMPORTANTI = 5 * 1024 * 1024  # 5 MB
LIMIT_DEFAULT = 3 * 1024 * 1024

def check_file_sizes(files, category):
    """
    Controlla le dimensioni dei file in base alla categoria.
    Restituisce una stringa di errore o None se tutto ok.
    """
    if category in ['tax_return', 'agreement', 'minutes', 'court_ruling']:
        limit = LIMIT_IMPORTANTI
        limit_label = "5 MB"
    elif category in ['payslip', 'payment_proof']:
        limit = LIMIT_RICEVUTE
        limit_label = "1.5 MB"
    else:
        limit = LIMIT_DEFAULT
        limit_label = "3 MB"

    errors = []
    for f in files:
        if f.size > limit:
            errors.append(f"⚠️ {f.name} ({filesizeformat(f.size)}) supera il limite di {limit_label}.")
        elif f.size == 0:
            errors.append(f"⚠️ {f.name} è vuoto.")

    return "\n".join(errors) if errors else None