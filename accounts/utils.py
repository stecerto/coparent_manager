# accounts/utils.py
from accounts.models import UserProfile
import codicefiscale

# =========================
# UTENTE / PROFILO
# =========================
def get_user_profile(user):
    """Restituisce il profilo dell'utente, crea se non esiste"""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def is_setup_complete(user):
    """Controlla se l'utente ha completato il setup"""
    profile = get_user_profile(user)
    return profile.setup_complete





def generate_cf(first_name, last_name, birth_date, birth_place_code, gender):
    """
    Genera codice fiscale italiano
    """
    try:
        if not all([first_name, last_name, birth_date, birth_place_code, gender]):
            return None

        return codicefiscale.build(
            surname=last_name,
            name=first_name,
            birthday=birth_date,
            birthplace=birth_place_code,
            gender=gender
        )
    except Exception:
        return None


"""
Utility per ottenere la lista dei comuni italiani con codici catastali.
"""
from municipality_lookup.instance import get_db
import logging

logger = logging.getLogger(__name__)


def get_all_municipalities():
    """
    Restituisce la lista di tutti i comuni italiani.
    Ritorna: lista di dict con 'name', 'code', 'province'
    """
    try:
        db = get_db()

        # Ottieni tutti i comuni
        municipalities = []

        # Itera su tutti i comuni nel database
        for municipality in db.municipalities:
            municipalities.append({
                'name': municipality.name,
                'code': municipality.cadastral_code,  # codice catastale
                'province': municipality.province,
            })

        # Ordina per nome
        municipalities.sort(key=lambda x: x['name'])

        logger.info(f"✅ Caricati {len(municipalities)} comuni")
        return municipalities

    except Exception as e:
        logger.error(f"❌ Errore caricamento comuni: {e}")
        # Fallback comuni principali
        return [
            {'name': 'ROMA', 'code': 'H501', 'province': 'RM'},
            {'name': 'MILANO', 'code': 'F205', 'province': 'MI'},
            {'name': 'NAPOLI', 'code': 'F839', 'province': 'NA'},
            {'name': 'TORINO', 'code': 'L219', 'province': 'TO'},
            {'name': 'BARI', 'code': 'A662', 'province': 'BA'},
            {'name': 'PALERMO', 'code': 'G273', 'province': 'PA'},
        ]


def search_municipality(query):
    """
    Cerca un comune per nome (fuzzy search).
    """
    try:
        db = get_db()
        result = db.get_by_name(query)
        if result:
            return {
                'name': result.name,
                'code': result.cadastral_code,
                'province': result.province,
            }
        return None
    except Exception as e:
        logger.error(f"Errore ricerca comune '{query}': {e}")
        return None