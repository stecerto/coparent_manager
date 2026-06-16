from xml.etree.ElementInclude import include

from django.urls import path
from . import views

app_name = "children"

urlpatterns = [
    # Lista
    path("", views.children_list, name="children_list"),

    # Creazione
    path("add/", views.child_create_view, name="child_form"),

    # ✅ AGGIUNTO: Dettaglio figlio
    path("<int:child_id>/", views.child_detail, name="child_detail"),

    # Modifica
    path("<int:pk>/edit/", views.child_update_view, name="child_edit"),

    # Archiviazione (Soft Delete)
    path("<int:pk>/delete/", views.child_delete_view, name="child_confirm_delete"),

    # ✅ AGGIUNTO: Aggiornamento mantenimento (utile se hai un bottone nel dettaglio)
    path("<int:child_id>/update-support/", views.update_support, name="update_support"),

    # PDF
    path("<int:child_id>/pdf/", views.child_pdf_view, name="child_pdf"),

]