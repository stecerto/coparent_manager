from xml.etree.ElementInclude import include

from django.urls import path, include
from .views import dashboard, home, lawyer_home_view



urlpatterns = [
    path("", home, name="home"),
    path("dashboard/", dashboard, name="dashboard"),
    path('lawyer/home/', lawyer_home_view, name='lawyer_home'),
]