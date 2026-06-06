# families/utils.py

from families.models import FamilyMember, Family


# families/utils.py

def generate_family_name(parent_user, suffix=None):
    """
    Genera un nome famiglia univoco e leggibile.
    Formato: "Famiglia [Cognome] [Nome] [Anno]"
    Esempio: "Famiglia Rossi Mario 1985"
    """
    # 1. Cognome (obbligatorio)
    cognome = parent_user.last_name.strip() if parent_user.last_name else "SenzaCognome"

    # 2. Nome (opzionale, ma utile)
    nome = parent_user.first_name.strip() if parent_user.first_name else ""

    # 3. Anno di nascita o telefono come discriminante (opzionale)
    # Priorità: birth_date > phone > suffix generico
    discriminante = ""
    if hasattr(parent_user, 'profile'):
        profile = parent_user.profile
        if profile.birth_date:
            discriminante = str(profile.birth_date.year)
        elif profile.phone:
            # Usa ultime 4 cifre del telefono per privacy
            discriminante = profile.phone.replace(" ", "").replace("-", "")[-4:]

    if not discriminante and suffix:
        discriminante = str(suffix)

    # Costruisci il nome finale
    parts = ["Famiglia", cognome]
    if nome:
        parts.append(nome)
    if discriminante:
        parts.append(f"({discriminante})")  # Parentesi per leggibilità

    return " ".join(parts)


def get_active_family(request):
    """
    Restituisce la famiglia attiva dalla sessione.
    ✅ Fallback automatico: se la sessione è vuota o scaduta,
       usa la tua get_family_of_user() esistente (zero rotture).
    """
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return None

    active_id = request.session.get('active_family_id')
    if active_id:
        # Import locale per evitare circolari se il file è usato in migrations/init
        from .models import FamilyMember
        mem = FamilyMember.objects.filter(
            user=request.user, family_id=active_id
        ).select_related('family').first()
        if mem:
            return mem.family

    # 🔙 Fallback sicuro: logica esistente invariata
    return get_family_of_user(request.user, request=request)

def is_lawyer(user):
    profile = getattr(user, "userprofile", None)

    if not profile:
        return False

    return profile.role in ["lawyer_a", "lawyer_b"]


def is_parent(user):
    profile = getattr(user, "userprofile", None)

    if not profile:
        return False

    return profile.role in ["parent_a", "parent_b"]


def get_user_families(user):
    """
    Restituisce tutte le famiglie collegate a un utente.
    Include:
        - Famiglie dove è membro (Parent A/B o Lawyer A/B)
    """
    return (
        Family.objects
        .filter(members__user=user)
        .distinct()
    )


def get_family_of_user(user, request=None):
    """
    Recupera la famiglia dell'utente.
    Per i professionisti (lawyer, mediator, consultant), NON usa fallback automatici.
    Devono selezionare esplicitamente una famiglia dalla dashboard.
    """
    print(f"\n[🔍 get_family_of_user] user={user.email}, request={'OK' if request else 'NONE'}")

    # Ottieni il ruolo dell'utente
    profile = getattr(user, 'profile', None)
    is_professional = profile and profile.role in ['lawyer', 'mediator', 'consultant']

    if request:
        # 1️⃣ URL Parameter (priorità massima)
        fid = request.GET.get('family_id')
        print(f"   → GET family_id: '{fid}' (type: {type(fid).__name__})")
        if fid:
            try:
                fid_int = int(fid)
                mem = FamilyMember.objects.select_related('family').get(user=user, family_id=fid_int)
                print(f"   ✅ TROVATA VIA URL: {mem.family.name} (ID={fid_int})\n")

                # ✅ Imposta in sessione SOLO se non è un professionista, o se esplicitamente richiesto via URL
                request.session['active_family_id'] = fid_int
                return mem.family
            except FamilyMember.DoesNotExist:
                print(f"   ❌ FamilyMember NON esiste per user={user.id}, family_id={fid}")
            except Exception as e:
                print(f"   ⚠️ Errore conversione/query URL: {e}")

        # 2️⃣ Session
        fid_sess = request.session.get('active_family_id')
        print(f"   → SESSION active_family_id: '{fid_sess}'")
        if fid_sess:
            try:
                fid_int = int(fid_sess)
                mem = FamilyMember.objects.select_related('family').get(user=user, family_id=fid_int)
                print(f"   ✅ TROVATA VIA SESSION: {mem.family.name} (ID={fid_int})\n")
                return mem.family
            except FamilyMember.DoesNotExist:
                print(f"   ❌ FamilyMember NON esiste in sessione per family_id={fid_sess}")
                # Pulisci la sessione corrotta
                if 'active_family_id' in request.session:
                    del request.session['active_family_id']
            except Exception as e:
                print(f"   ⚠️ Errore conversione/query sessione: {e}")

    # 3️⃣ FALLBACK: Solo per GENITORI o se non c'è request
    # ✅ I PROFESSIONISTI NON DEVONO AVERE UN FALLBACK AUTOMATICO
    if not is_professional:
        fallback_mem = FamilyMember.objects.filter(user=user).select_related('family').first()
        if fallback_mem:
            print(f"   ℹ️ FALLBACK (Genitore): {fallback_mem.family.name} (ID={fallback_mem.family.id})\n")
            if request:
                request.session['active_family_id'] = fallback_mem.family.id
            return fallback_mem.family

    # ✅ Per i professionisti, se non c'è URL o Sessione valida, ritorna None
    print(f"   ℹ️ NESSUNA FAMIGLIA ATTIVA (Professionista deve selezionare dalla dashboard)\n")
    return None


def get_family_lawyer(family, lawyer_role="lawyer_a"):
    """
    Restituisce l'utente che ricopre il ruolo di lawyer_a o lawyer_b nella famiglia.
    """
    return (
        family.members
        .select_related("user")
        .filter(role=lawyer_role)
        .first()
    )


def get_family_members_by_role(family, role):
    """
    Restituisce la lista dei membri di una famiglia con un ruolo specifico
    """
    return family.members.filter(role=role)

def get_family_parent(family, role="parent_a"):
    member = family.members.filter(role=role).first()
    return member.user if member else None

def get_user_role_in_family(user, family=None):
    qs = user.family_memberships.select_related("family")

    if family:
        qs = qs.filter(family=family)
    else:
        qs = qs.order_by("-is_primary", "-joined_at")

    membership = qs.first()

    return membership.role if membership else None


# families/utils.py
from accounts.models import UserProfile


def calculate_setup_progress(user):
    profile = UserProfile.objects.filter(user=user).first()

    # ✅ Differenzia i campi in base al ruolo
    is_professional = profile.role in ['lawyer', 'mediator', 'consultant']

    if is_professional:
        # AVVOCATI/MEDIATORI/CONSULENTI: campi professionali
        important_fields = [
            ("address", "Indirizzo"),
            ("phone", "Telefono"),
            ("firm_name", "Nome studio legale"),
            ("partita_iva", "Partita IVA"),
        ]
    else:
        # GENITORI: campi personali
        important_fields = [
            ("address", "Indirizzo"),
            ("phone", "Telefono"),
            ("birth_place", "Luogo di nascita"),
        ]

    completed_labels = []
    missing_labels = []
    completed = 0

    for field_name, label in important_fields:
        value = getattr(profile, field_name, "")

        # ✅ normalizza
        value = str(value).strip() if value is not None else ""

        if value != "":
            completed += 1
            completed_labels.append(label)
        else:
            missing_labels.append(label)

    total = len(important_fields)
    progress_pct = round((completed / total) * 100) if total else 0

    return (
        progress_pct,
        completed,
        len(missing_labels),
        important_fields,
        completed_labels,
    )

def can_lawyer_add_family(lawyer_user):
    """Controlla se un avvocato può aggiungere un'altra famiglia in base al piano"""
    profile = lawyer_user.profile

    # Mappa piano → limite famiglie
    plan_limits = {
        "starter": 5,
        "pro": 25,
        "enterprise": 50,
    }

    limit = plan_limits.get(profile.plan, 5)  # Default a 5 se piano non valido

    # Conta famiglie attive assegnate a questo avvocato
    active_families = FamilyMember.objects.filter(
        user=lawyer_user,
        role__in=['lawyer_a', 'lawyer_b'],
        #is_active=True
    ).count()

    return active_families < limit, limit, active_families


# =========================
# LIMITI PROFESSIONISTI (FUNZIONE CENTRALE)
# =========================
def get_lawyer_limits(user):
    """
    Restituisce i limiti e i consumi attuali per un professionista.
    Usato sia nel backend (validazione) che nei template (visualizzazione).
    """
    from core.plans import PLAN_LIMITS

    profile = getattr(user, 'profile', None)
    if not profile or profile.role not in ['lawyer', 'mediator', 'consultant']:
        return None

    plan = profile.plan if profile.plan in PLAN_LIMITS else 'starter'
    limits = PLAN_LIMITS[plan]

    # Conta le assegnazioni ATTIVE
    current_families = FamilyMember.objects.filter(
        user=user,
        role__in=['lawyer_a', 'lawyer_b']
    ).count()

    current_mediators = FamilyMember.objects.filter(
        user=user,
        role__in=['mediator', 'mediator_a', 'mediator_b']
    ).count()

    current_consultants = FamilyMember.objects.filter(
        user=user,
        role__in=['consultant', 'consultant_a', 'consultant_b']
    ).count()

    return {
        'plan': plan,
        'families': {'current': current_families, 'limit': limits['families']},
        'mediators': {'current': current_mediators, 'limit': limits['mediators']},
        'consultants': {'current': current_consultants, 'limit': limits['consultants']},
    }


# =========================
# CALCOLO DINAMICO RUOLO _a / _b
# =========================
def get_target_role(base_role, inviter_role):
    """
    Determina il ruolo finale dell'invitato in base al ruolo di chi invita.

    Regole:
    - Se l'invitante è un GENITORE che invita l'altro genitore:
      * parent_a → parent_b (e viceversa)
    - Se l'invitante è un GENITORE che invita un professionista:
      * parent_a → lawyer_a, mediator_a, consultant_a
      * parent_b → lawyer_b, mediator_b, consultant_b
    - Se l'invitante è un PROFESSIONISTA che invita un genitore:
      * lawyer_a → parent_a (stesso team)
      * lawyer_b → parent_b (stesso team)
    """
    inviter_role_str = str(inviter_role).lower()
    base_role_clean = base_role.replace('_a', '').replace('_b', '')

    # =========================
    # CASO 1: L'invitante è un GENITORE
    # =========================
    if inviter_role_str in ['parent_a', 'parent_b', 'parent']:
        if base_role_clean == 'parent':
            # ✅ Genitore invita l'ALTRO genitore: inverti il suffisso
            if inviter_role_str == 'parent_a':
                return 'parent_b'
            elif inviter_role_str == 'parent_b':
                return 'parent_a'
            else:
                return 'parent_b'  # fallback se role generico
        else:
            # ✅ Genitore invita professionista: stesso suffisso del genitore
            suffix = '_b' if inviter_role_str == 'parent_b' else '_a'
            if base_role_clean in ['lawyer', 'mediator', 'consultant']:
                return f"{base_role_clean}{suffix}"
            return base_role

    # =========================
    # CASO 2: L'invitante è un PROFESSIONISTA
    # =========================
    # ✅ Professionista invita genitore/professionista: stesso suffisso
    suffix = '_b' if '_b' in inviter_role_str else '_a'

    roles_with_suffix = ['parent', 'lawyer', 'mediator', 'consultant']
    if base_role_clean in roles_with_suffix:
        return f"{base_role_clean}{suffix}"

    # Fallback per ruoli che non hanno suffissi
    return base_role