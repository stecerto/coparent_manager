# calendar_app/views.py
import logging
from datetime import datetime
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime as django_parse_datetime
from django.views.decorators.http import require_POST
from django.urls import reverse
from families.utils import get_family_of_user
from families.models import FamilyMember, Family
from calendar_app.models import CalendarEvent, ProfessionalEvent
from calendar_app.services.calendar_service import create_event, update_event, get_family_events

logger = logging.getLogger(__name__)
from .models import ProfessionalEvent
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from datetime import datetime


def _is_professional(user):
    role = getattr(user, 'profile', None)
    if not role: return False
    return str(role.role).replace('_a', '').replace('_b', '').lower() in ['lawyer', 'mediator', 'consultant']

@login_required
def professional_calendar_full_view(request):
    """Calendario visuale FullCalendar per professionisti"""
    if not _is_professional(request.user):
        messages.error(request, "⚠️ Accesso riservato ai professionisti")
        return redirect('home')

    return render(request, 'calendar_app/professional_calendar_full.html', {
        'event_types': ProfessionalEvent.EVENT_TYPES,
    })


@login_required
def professional_events_json(request):
    """JSON degli eventi professionali per FullCalendar"""
    if not _is_professional(request.user):
        return JsonResponse([], safe=False)

    events = ProfessionalEvent.objects.filter(
        user=request.user,
        is_active=True
    ).select_related('family').distinct()

    start, end = request.GET.get("start"), request.GET.get("end")
    if start and end:
        s_dt, e_dt = django_parse_datetime(start), django_parse_datetime(end)
        if s_dt and e_dt:
            events = events.filter(start_time__gte=s_dt, end_time__lte=e_dt)

    data = []
    color_map = {
        "meeting": "#0d6efd",
        "court": "#dc3545",
        "consultation": "#198754",
        "mediation": "#6f42c1",
        "deadline": "#fd7e14",
        "other": "#6c757d",
    }

    for ev in events:
        data.append({
            "id": ev.id,
            "title": ev.title,
            "start": ev.start_time.isoformat(),
            "end": ev.end_time.isoformat(),
            "description": ev.description,
            "location": ev.location,
            "family_name": ev.family.name if ev.family else None,
            "event_type": ev.event_type,
            "extendedProps": {
                "event_type": ev.event_type,
                "description": ev.description,
                "location": ev.location,
                "family_name": ev.family.name if ev.family else None,
                "edit_url": f"/calendar/professional/event/{ev.id}/edit/",
            },
            "backgroundColor": color_map.get(ev.event_type, "#6c757d"),
            "borderColor": color_map.get(ev.event_type, "#6c757d"),
        })

    return JsonResponse(data, safe=False)


@login_required
def professional_event_form_view(request, event_id=None):
    """Crea o modifica evento personale per professionisti"""
    if not _is_professional(request.user):
        messages.error(request, "⚠️ Accesso riservato ai professionisti")
        return redirect('home')

    event = None
    is_edit = False
    if event_id:
        event = get_object_or_404(ProfessionalEvent, pk=event_id, user=request.user)
        is_edit = True

    if request.method == 'POST':
        print(f"\n🔍 DEBUG professional_event_form_view POST")
        print(f"  POST data: {request.POST.dict()}")

        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        event_type = request.POST.get('event_type', 'other')
        location = request.POST.get('location', '').strip()
        family_id = request.POST.get('family_id')

        start_str = request.POST.get('start_time')
        end_str = request.POST.get('end_time')

        print(f"  title: '{title}'")
        print(f"  start_time: '{start_str}'")
        print(f"  end_time: '{end_str}'")

        if not title or not start_str:
            print(f"  ❌ Validazione fallita: campi mancanti")
            messages.error(request, "⚠️ Compila almeno il titolo e la data di inizio")
        else:
            try:
                from datetime import timedelta
                start_dt = _parse_local_dt(start_str)

                # ✅ Se end_time non è fornito, usa start_time + 1 ora come default
                if end_str:
                    end_dt = _parse_local_dt(end_str)
                else:
                    end_dt = start_dt + timedelta(hours=1)
                    print(f"  ℹ️ end_time vuoto, uso default: {end_dt}")

                # ✅ CONTROLLO DUPLICATI: verifica se esiste già un evento identico
                if not is_edit:
                    duplicate = ProfessionalEvent.objects.filter(
                        user=request.user,
                        title=title,
                        start_time=start_dt,
                        end_time=end_dt,
                        is_active=True
                    ).exists()

                    if duplicate:
                        print(f"  ⚠️ Evento duplicato rilevato!")
                        messages.warning(request, "⚠️ Questo evento esiste già. Non è stato creato un duplicato.")
                        return redirect('calendar:professional_calendar')

                print(f"  ✅ Date parse: {start_dt} → {end_dt}")

                data = {
                    'title': title,
                    'description': description,
                    'event_type': event_type,
                    'location': location,
                    'start_time': start_dt,
                    'end_time': end_dt,
                    'family_id': family_id if family_id else None
                }

                if is_edit:
                    for k, v in data.items():
                        setattr(event, k, v)
                    event.save()
                    print(f"  ✅ Evento aggiornato ID={event.id}")
                    messages.success(request, "✅ Evento aggiornato")
                else:
                    event = ProfessionalEvent.objects.create(user=request.user, **data)
                    print(f"  ✅ Evento creato ID={event.id}")

                    # ✅ Avvia sync Google
                    try:
                        from calendar_app.tasks import sync_professional_event_to_google_task
                        sync_professional_event_to_google_task.delay(event.id)
                        print(f"  📅 Task Celery avviato per evento {event.id}")
                    except Exception as e:
                        print(f"  ⚠️ Errore avvio task Celery: {e}")

                    messages.success(request, "✅ Evento creato e sincronizzato")

                return redirect('calendar:professional_calendar_full')

            except Exception as e:
                print(f"  ❌ Errore durante il salvataggio: {e}")
                import traceback
                traceback.print_exc()
                messages.error(request, f"⚠️ Errore durante il salvataggio: {str(e)}")

    # ✅ Recupera le famiglie assegnate al professionista
    from families.models import FamilyMember, Family
    assigned_families = FamilyMember.objects.filter(
        user=request.user
    ).values_list('family', flat=True).distinct()

    families = Family.objects.filter(id__in=assigned_families).order_by('name').distinct()

    print(f"  ℹ️ Famiglie disponibili: {list(families.values_list('name', flat=True))}")

    return render(request, 'calendar_app/professional_event_form.html', {
        'event': event,
        'is_edit': is_edit,
        'families': families,
        'event_types': ProfessionalEvent.EVENT_TYPES
    })


@login_required
def professional_event_delete(request, event_id):
    if not _is_professional(request.user): return redirect('home')
    event = get_object_or_404(ProfessionalEvent, pk=event_id, user=request.user)
    event.is_active = False
    event.save()
    messages.success(request, "🗑️ Evento eliminato")
    return redirect('calendar:professional_calendar')

def _parse_local_dt(dt_str):
    """Helper sicuro per datetime-local con timezone"""
    if not dt_str: return None
    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


@login_required
def family_calendar_view(request):
    family = get_family_of_user(request.user, request=request)
    if not family:
        return render(request, "calendar_app/no_family.html")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        event_type = request.POST.get("event_type", "other")

        start_time = _parse_local_dt(request.POST.get("start_time"))
        end_time = _parse_local_dt(request.POST.get("end_time"))

        children = family.children.filter(id__in=request.POST.getlist("children")) if request.POST.getlist(
            "children") else []

        if not title or not start_time or not end_time:
            return render(request, "calendar_app/calendar_view.html", {
                "events": get_family_events(family), "family": family,
                "event_types": CalendarEvent.EVENT_TYPES,
                "error": "Compila titolo, date e categoria."
            })

        event_id = request.POST.get("event_id")
        if event_id:
            event = get_object_or_404(CalendarEvent, pk=event_id, family=family)
            update_event(event, request.user, {
                "title": title, "description": description, "event_type": event_type,
                "start_time": start_time, "end_time": end_time, "children": children,
            })
        else:
            create_event(family=family, title=title, start_time=start_time, end_time=end_time,
                         created_by=request.user, description=description, event_type=event_type, children=children)
        return redirect("calendar:calendar_view")

    return render(request, "calendar_app/calendar_view.html", {
        "events": get_family_events(family), "family": family,
        "event_types": CalendarEvent.EVENT_TYPES,
    })


@login_required
def events_json(request):
    family = get_family_of_user(request.user, request=request)
    if not family: return JsonResponse([], safe=False)

    queryset = CalendarEvent.objects.filter(family=family, is_active=True).select_related(
        "created_by").prefetch_related("children")

    start, end = request.GET.get("start"), request.GET.get("end")
    if start and end:
        s_dt, e_dt = django_parse_datetime(start), django_parse_datetime(end)
        if s_dt and e_dt:
            queryset = queryset.filter(start_time__gte=s_dt, end_time__lte=e_dt)

    data = []
    for ev in queryset:
        kids = [c.name for c in ev.children.all()]
        data.append({
            "id": ev.id, "title": f"{ev.title} {'👶' + ', '.join(kids) if kids else ''}",
            "start": ev.start_time.isoformat(), "end": ev.end_time.isoformat(),
            "event_type": ev.event_type,
            "extendedProps": {"event_type": ev.event_type, "children": kids, "description": ev.description},
            "backgroundColor": _get_event_color(ev.event_type), "borderColor": _get_event_color(ev.event_type),
        })
    return JsonResponse(data, safe=False)


@login_required
@require_POST
def update_event_ajax(request, event_id):
    try:
        ev = get_object_or_404(CalendarEvent, pk=event_id, family=get_family_of_user(request.user, request=request))
        start = _parse_local_dt(request.POST.get("start_time"))
        end = _parse_local_dt(request.POST.get("end_time"))
        if start: ev.start_time = start
        if end: ev.end_time = end
        if request.POST.get("title"): ev.title = request.POST["title"].strip()
        ev.save()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def delete_event_view(request, event_id):
    ev = get_object_or_404(CalendarEvent, pk=event_id, family=get_family_of_user(request.user, request=request))
    ev.is_active = False
    ev.archived_at = timezone.now()
    ev.archived_by = request.user
    ev.save()
    return redirect("calendar:events_list")


@login_required
def event_form_view(request, event_id=None):
    family = get_family_of_user(request.user, request=request)
    if not family: return render(request, "calendar_app/no_family.html")

    event = get_object_or_404(CalendarEvent, pk=event_id, family=family) if event_id else None
    is_edit = bool(event)
    # ✅ GENERA BREADCRUMBS COMPATIBILI CON IL TUO BASE.HTML
    breadcrumbs = [
        {"name": "Home", "url": reverse("home")},
        # ⚠️ Adatta se il tuo dashboard ha un nome diverso
        {"name": "Calendario", "url": reverse("calendar:calendar_view")},
        {"name": "Modifica evento" if is_edit else "Crea evento", "url": None}
        # url=None → base.html lo renderà attivo/non cliccabile
    ]
    if request.method == "POST":
        children = family.children.filter(id__in=request.POST.getlist("children")) if request.POST.getlist(
            "children") else []
        data = {
            "title": request.POST.get("title"), "description": request.POST.get("description"),
            "start_time": _parse_local_dt(request.POST.get("start_time")),
            "end_time": _parse_local_dt(request.POST.get("end_time")),
            "event_type": request.POST.get("event_type", "other"),
            "children": children
        }
        if event:
            update_event(event, request.user, data)
        else:
            create_event(family=family, created_by=request.user, **data)
        return redirect("calendar:calendar_view")

    # ✅ Ottimizza queryset figli per evitare duplicati
    children_queryset = family.children.filter(is_active=True).distinct()

    return render(request, "calendar_app/event_form.html", {
        "event": event, "is_edit": bool(event), "family": family,
        "children_list": children_queryset,  # ✅ Passa queryset ottimizzato
        "start": request.GET.get("start", ""), "end": request.GET.get("end", ""),
        "event_types": CalendarEvent.EVENT_TYPES, "breadcrumbs": breadcrumbs,
    })


def _get_event_color(event_type):
    return {
        "custody": "#6f42c1", "school": "#0d6efd", "medical": "#198754",
        "expense": "#ffc107", "legal": "#dc3545", "other": "#6c757d"
    }.get(event_type, "#6c757d")


from django.core.paginator import Paginator

@login_required
def events_list_view(request):
    """Lista eventi con filtri e paginazione"""
    family = get_family_of_user(request.user, request=request)
    if not family:
        return render(request, "calendar_app/no_family.html")

    # Query base
    events = CalendarEvent.objects.filter(
        family=family,
        is_active=True
    ).select_related("created_by").prefetch_related("children").order_by("-start_time")

    # Filtri
    event_type = request.GET.get("event_type")
    if event_type:
        events = events.filter(event_type=event_type)

    date_from = request.GET.get("date_from")
    if date_from:
        events = events.filter(start_time__date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        events = events.filter(end_time__date__lte=date_to)

    # Paginazione
    paginator = Paginator(events, 12)  # 12 eventi per pagina
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "calendar_app/lista_eventi.html", {
        "events": page_obj,
        "event_types": CalendarEvent.EVENT_TYPES,
        "family": family,
    })


@login_required
def event_detail_view(request, event_id):
    """Visualizza i dettagli di un singolo evento"""
    event = get_object_or_404(CalendarEvent, id=event_id)

    # ✅ Sicurezza: verifica che l'evento appartenga alla famiglia dell'utente loggato
    family = get_family_of_user(request.user, request=request)
    if event.family != family:
        return HttpResponseForbidden("Non hai i permessi per visualizzare questo evento.")

    # 3. Recupera i figli coinvolti (se presenti)
    involved_children = event.children.all()

    context = {
        "event": event,
        "involved_children": involved_children,
    }
    return render(request, "calendar_app/event_detail.html", context)


from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from calendar_app.models import GoogleCalendarToken


@login_required
def google_auth_view(request):
    """Inizia flusso OAuth Google"""
    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_CALENDAR_REDIRECT_URI],
                }
            },
            scopes=settings.GOOGLE_CALENDAR_SCOPES,
        )

        flow.redirect_uri = settings.GOOGLE_CALENDAR_REDIRECT_URI

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )

        # Salva state in sessione
        request.session['google_oauth_state'] = state

        return redirect(authorization_url)

    except Exception as e:
        messages.error(request, f"❌ Errore avvio autenticazione Google: {e}")
        return redirect('families:setup')


@login_required
def google_callback_view(request):
    """Callback OAuth Google"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        from google_auth_oauthlib.flow import Flow
        from calendar_app.models import GoogleCalendarToken

        logger.info(f"🔍 Google callback ricevuto per utente: {request.user.email}")

        state = request.session.get('google_oauth_state')
        if not state:
            logger.error("❌ Stato OAuth non trovato in sessione")
            messages.error(request, "❌ Stato OAuth non valido")
            return redirect('families:setup')

        logger.info(f"✅ Stato OAuth trovato: {state[:20]}...")

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_CALENDAR_REDIRECT_URI],
                }
            },
            scopes=settings.GOOGLE_CALENDAR_SCOPES,
            state=state,
        )

        flow.redirect_uri = settings.GOOGLE_CALENDAR_REDIRECT_URI

        # Scambia codice con token
        authorization_response = request.build_absolute_uri()
        logger.info(f"🔄 Scambio codice OAuth con token...")

        flow.fetch_token(authorization_response=authorization_response)
        credentials = flow.credentials

        logger.info(f"✅ Credenziali ottenute:")
        logger.info(f"   - Token: {credentials.token[:20]}..." if credentials.token else "   - Token: None")
        logger.info(
            f"   - Refresh token: {credentials.refresh_token[:20]}..." if credentials.refresh_token else "   - Refresh token: None")
        logger.info(f"   - Scopes: {credentials.scopes}")

        # ✅ SALVA/AGGIORNA TOKEN
        logger.info(f"💾 Salvataggio token per utente: {request.user.email} (ID: {request.user.id})")

        token_obj, created = GoogleCalendarToken.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': ' '.join(credentials.scopes) if credentials.scopes else '',
                'expiry': credentials.expiry,
                'is_active': True,
            }
        )

        logger.info(f"✅ Token salvato: created={created}, token_id={token_obj.id}, is_active={token_obj.is_active}")

        # Pulisci sessione
        del request.session['google_oauth_state']

        if created:
            messages.success(request, f"✅ Google Calendar collegato con successo per {request.user.email}!")
        else:
            messages.success(request, "✅ Google Calendar aggiornato con successo!")

        return redirect('families:setup')

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        logger.error(f"❌ Errore callback Google:\n{error_msg}")
        messages.error(request, f"❌ Errore callback Google: {e}")
        return redirect('families:setup')


@login_required
def google_disconnect_view(request):
    """Disconnette Google Calendar"""
    try:
        from calendar_app.models import GoogleCalendarToken

        GoogleCalendarToken.objects.filter(user=request.user).update(is_active=False)

        messages.success(request, "✅ Google Calendar disconnesso")
        return redirect('families:setup')

    except Exception as e:
        messages.error(request, f"❌ Errore disconnessione: {e}")
        return redirect('families:setup')


@login_required
def google_sync_view(request):
    """Sincronizza tutti gli eventi su Google"""
    try:
        from calendar_app.services.google_calendar_service import sync_all_events_to_google
        from families.utils import get_family_of_user

        family = get_family_of_user(request.user, request=request)
        if not family:
            messages.error(request, "❌ Nessuna famiglia trovata")
            return redirect('families:setup')

        result = sync_all_events_to_google(request.user, family)

        if result['success']:
            stats = result['stats']
            messages.success(
                request,
                f"✅ Sync completato: {stats['synced']}/{stats['total']} eventi sincronizzati"
            )
        else:
            messages.error(request, f"❌ Errore sync: {result.get('error')}")

        return redirect('families:setup')

    except Exception as e:
        messages.error(request, f"❌ Errore sync: {e}")
        return redirect('families:setup')