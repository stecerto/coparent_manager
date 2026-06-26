"""
Script per criptare i dati esistenti della chat professionisti.
Esegui con: python manage.py shell < scripts/encrypt_existing_professional_data.py
"""
from chat.models import ProfessionalMessage
from core.encryption import encrypt_text
from django.db import connection


def encrypt_existing_messages():
    """Cripta tutti i messaggi esistenti"""
    messages = ProfessionalMessage.objects.all()

    print(f"Trovati {messages.count()} messaggi da processare")

    for msg in messages:
        # Leggi il valore grezzo dal DB (bypassando il field)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT content FROM chat_professionalmessage WHERE id = %s",
                [msg.id]
            )
            row = cursor.fetchone()
            raw_content = row[0] if row else None

        # Se è vuoto o già criptato, salta
        if not raw_content or raw_content.startswith('gAAAAA'):
            print(f"⏭️  Messaggio ID {msg.id} già criptato o vuoto")
            continue

        # ✅ Cripta e aggiorna direttamente nel DB
        encrypted = encrypt_text(raw_content)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_professionalmessage SET content = %s WHERE id = %s",
                [encrypted, msg.id]
            )
        print(f"✅ Criptato messaggio ID {msg.id}")

    print("\n✅ Completato!")


if __name__ == '__main__':
    encrypt_existing_messages()