import os
import json
import zipfile
from datetime import datetime
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone


def export_family_data(family, user_requesting):
    """
    Esporta tutti i dati della famiglia in un file ZIP
    Include: membri, figli, spese, eventi, documenti, chat
    """

    # Verifica permessi
    if not family.members.filter(user=user_requesting).exists():
        raise PermissionError("Non hai accesso a questa famiglia")

    # Crea cartella temporanea
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"export_{family.name.replace(' ', '_')}_{timestamp}"
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'exports', folder_name)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # 1. DATI FAMIGLIA
        family_data = {
            'nome': family.name,
            'data_creazione': family.created_at.isoformat(),
            'membri': []
        }

        for member in family.members.all():
            member_data = {
                'nome': member.user.get_full_name(),
                'email': member.user.email,
                'ruolo': member.get_role_display(),
                'data_adesione': member.joined_at.isoformat()
            }
            family_data['membri'].append(member_data)

        with open(os.path.join(temp_dir, 'famiglia.json'), 'w', encoding='utf-8') as f:
            json.dump(family_data, f, indent=2, ensure_ascii=False)

        # 2. FIGLI
        children_data = []
        for child in family.children.all():
            child_data = {
                'nome': child.name,
                'data_nascita': child.birth_date.isoformat() if child.birth_date else None,
                'note': child.notes,
                'note_mediche': child.medical_notes
            }
            children_data.append(child_data)

        with open(os.path.join(temp_dir, 'figli.json'), 'w', encoding='utf-8') as f:
            json.dump(children_data, f, indent=2, ensure_ascii=False)

        # 3. SPESE
        expenses_data = []
        for expense in family.expenses.all():
            expense_data = {
                'descrizione': expense.description,
                'importo': str(expense.amount),
                'data': expense.date.isoformat(),
                'categoria': expense.category.name if expense.category else None,
                'pagata_da': expense.paid_by.user.get_full_name() if expense.paid_by else None,
                'stato': expense.get_status_display(),
                'tipo': 'ordinaria' if expense.is_ordinary else 'straordinaria'
            }
            expenses_data.append(expense_data)

        with open(os.path.join(temp_dir, 'spese.json'), 'w', encoding='utf-8') as f:
            json.dump(expenses_data, f, indent=2, ensure_ascii=False)

        # 4. EVENTI CALENDARIO
        events_data = []
        for event in family.calendar_events.all():
            event_data = {
                'titolo': event.title,
                'descrizione': event.description,
                'data_inizio': event.start_date.isoformat(),
                'data_fine': event.end_date.isoformat() if event.end_date else None,
                'tipo': event.get_event_type_display(),
                'creatoda': event.created_by.user.get_full_name() if event.created_by else None
            }
            events_data.append(event_data)

        with open(os.path.join(temp_dir, 'calendario.json'), 'w', encoding='utf-8') as f:
            json.dump(events_data, f, indent=2, ensure_ascii=False)

        # 5. DOCUMENTI
        docs_folder = os.path.join(temp_dir, 'documenti')
        os.makedirs(docs_folder, exist_ok=True)

        documents_data = []
        for doc in family.documents.all():
            doc_data = {
                'titolo': doc.title,
                'categoria': doc.get_category_display(),
                'data_caricamento': doc.uploaded_at.isoformat(),
                'caricato_da': doc.uploaded_by.user.get_full_name() if doc.uploaded_by else None,
                'file': doc.file.name if doc.file else None
            }
            documents_data.append(doc_data)

            # Copia file fisico
            if doc.file and os.path.exists(doc.file.path):
                import shutil
                shutil.copy(doc.file.path, docs_folder)

        with open(os.path.join(temp_dir, 'documenti.json'), 'w', encoding='utf-8') as f:
            json.dump(documents_data, f, indent=2, ensure_ascii=False)

        # 6. MESSAGGI CHAT
        messages_data = []
        for msg in family.messages.all():
            msg_data = {
                'mittente': msg.sender.user.get_full_name() if msg.sender else None,
                'contenuto': msg.content,
                'data': msg.created_at.isoformat(),
                'tipo_thread': msg.get_thread_type_display()
            }
            messages_data.append(msg_data)

        with open(os.path.join(temp_dir, 'chat.json'), 'w', encoding='utf-8') as f:
            json.dump(messages_data, f, indent=2, ensure_ascii=False)

        # 7. CREA ZIP
        zip_filename = f"{family.name.replace(' ', '_')}_{timestamp}.zip"
        zip_path = os.path.join(settings.MEDIA_ROOT, 'exports', zip_filename)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)

        # 8. PULIZIA
        import shutil
        shutil.rmtree(temp_dir)

        return zip_filename

    except Exception as e:
        # Cleanup in caso di errore
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e