import sqlite3

DB_NAME = "bot_bcv.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Crear tabla de usuarios si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            es_usuario_vip INTEGER DEFAULT 0,
            ultima_conexion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def es_administrador(user_id, admin_id):
    """Verifica si el ID de Telegram coincide con el ID del Administrador."""
    return int(user_id) == int(admin_id)

def registrar_o_actualizar_usuario(user_id, username, first_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO usuarios (user_id, username, first_name, ultima_conexion)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            ultima_conexion = datetime('now')
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def activar_premium(user_id, es_vip):
    """Guarda o actualiza el estado VIP en la base de datos de forma permanente."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE usuarios 
        SET es_usuario_vip = ? 
        WHERE user_id = ?
    ''', (es_vip, user_id))
    conn.commit()
    conn.close()

def es_usuario_vip(user_id):
    """Consulta si el usuario tiene la suscripción VIP activa en la BD."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT es_usuario_vip FROM usuarios WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else False

def obtener_usuarios_vip():
    """Obtiene la lista de IDs de todos los usuarios VIP registrados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM usuarios WHERE es_usuario_vip = 1')
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def obtener_id_por_username(username):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    clean_username = username.replace("@", "").strip()
    cursor.execute('SELECT user_id FROM usuarios WHERE LOWER(username) = LOWER(?)', (clean_username,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def obtener_estadisticas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM usuarios')
    total = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM usuarios WHERE es_usuario_vip = 1')
    vips = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE datetime(ultima_conexion) >= datetime('now', '-1 day')")
    hoy = cursor.fetchone()[0]
    
    conn.close()
    return total, vips, hoy