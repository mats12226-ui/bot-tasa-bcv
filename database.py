import sqlite3

DB_NAME = "bot_data.db"

def init_db():
    """Crea la tabla de usuarios si no existe."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            es_premium INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def registrar_o_actualizar_usuario(user_id, username, first_name):
    """Registra un nuevo usuario o actualiza sus datos si ya existe."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO usuarios (user_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def obtener_estadisticas():
    """Devuelve el total de usuarios y cuántos son premium."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total_usuarios = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE es_premium = 1")
    total_premium = cursor.fetchone()[0]
    
    conn.close()
    return total_usuarios, total_premium