#!/bin/bash
# ==========================================
# SCRIPT DI BACKUP CRITTOGRAFATO CoParent
# ==========================================

# 1. CONFIGURAZIONE
DB_NAME="<nome_database>"
DB_USER="<utente_db>"
BACKUP_DIR="/opt/backups"
MEDIA_DIR="/percorso/del/tuo/progetto/media"  # Es: /home/stecerto/PycharmProjects/coparent_manager/media
ENCRYPTION_PASSWORD="<una_password_segreta_molto_lunga>"
DATE=$(date +"%Y%m%d_%H%M")
RETENTION_DAYS=30

# 2. BACKUP DATABASE (PostgreSQL)
echo "📦 Backup database in corso..."
pg_dump -U $DB_USER -d $DB_NAME -F c -f "$BACKUP_DIR/db_$DATE.dump"

# 3. BACKUP FILE MEDIA
echo "📁 Backup file media in corso..."
tar -czf "$BACKUP_DIR/media_$DATE.tar.gz" -C "$MEDIA_DIR" .

# 4. CRITTOGRAFIA DEI BACKUP (AES-256)
echo "🔒 Crittografia in corso..."
openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$ENCRYPTION_PASSWORD" -in "$BACKUP_DIR/db_$DATE.dump" -out "$BACKUP_DIR/db_$DATE.dump.enc"
openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$ENCRYPTION_PASSWORD" -in "$BACKUP_DIR/media_$DATE.tar.gz" -out "$BACKUP_DIR/media_$DATE.tar.gz.enc"

# 5. PULIZIA FILE NON CRITTOGRAFATI
rm "$BACKUP_DIR/db_$DATE.dump"
rm "$BACKUP_DIR/media_$DATE.tar.gz"

# 6. ELIMINAZIONE BACKUP VECCHI (> 30 giorni)
echo "🧹 Pulizia backup vecchi..."
find "$BACKUP_DIR" -name "*.enc" -type f -mtime +$RETENTION_DAYS -delete

# 7. (OPZIONALE) INVIO SU SERVER REMOTO O CLOUD (es. con rsync o rclone)
# rsync -avz -e "ssh -i /path/to/key" "$BACKUP_DIR/" user@remote-server:/remote/backups/

echo "✅ Backup completato con successo!"