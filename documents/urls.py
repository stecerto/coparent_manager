from django.urls import path
from . import views

app_name = "documents"

urlpatterns = [
    path("", views.document_list_view, name="documents_list"),
    path("upload/", views.upload_document_view, name="documents_upload"),
    path("download/<int:doc_id>/", views.download_document_view, name="documents_download"),
    path("versions/<int:doc_id>/", views.document_versions_view, name="documents_versions"),
    path("upload-shared/",views.upload_shared_document_view,name="documents_upload_shared"),
    path("sign/<int:doc_id>/", views.sign_document_view, name="sign"),
    path("<int:doc_id>/", views.document_detail_view, name="documents_detail"),
    path("<int:doc_id>/approve/", views.approve_document_view, name="approve"),
    path("dossier/", views.family_dossier_view, name="dossier"),
]