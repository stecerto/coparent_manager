from xml.etree.ElementInclude import include

from django.urls import path
from . import views

app_name = "children"
urlpatterns = [

    path("", views.children_list, name="children_list"),

    path("add/", views.child_create_view, name="child_form"),
    path("<int:pk>/edit/", views.child_update_view, name="child_edit"),
    path("<int:pk>/delete/", views.child_delete_view, name="child_confirm_delete"),
    path("child/<int:child_id>/pdf/", views.child_pdf_view, name="child_pdf"),
]