from xml.etree.ElementInclude import include

from django.urls import path, include
from .views import dashboard, home
from families.services.setup_service import handle_setup


urlpatterns = [
    path("", home, name="home"),
    path("dashboard/", dashboard, name="dashboard"),
]