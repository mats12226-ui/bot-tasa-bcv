import sqlite3

DB_NAME = "bot_bcv.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            es_usuario_vip INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def registrar_o_actualizar_usuario(user_id, username, first_name):
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

def activar_premium(user_id, es_vip=1):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE usuarios SET es_usuario_vip = ? WHERE user_id = ?', (es_vip, user_id))
    conn.commit()
    conn.close()

def es_usuario_vip(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT es_usuario_vip FROM usuarios WHERE user_id = ?', (user_id,))
    resultado = cursor.fetchone()
    conn.close()
    return bool(resultado and resultado[0] == 1)

def obtener_usuarios_vip():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM usuarios WHERE es_usuario_vip = 1')
    filas = cursor.fetchall()
    conn.close()
    return [f[0] for f in filas]

def obtener_estadisticas():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM usuarios')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM usuarios WHERE es_usuario_vip = 1')
    vips = cursor.fetchone()[0]
    conn.close()
    return total, vips