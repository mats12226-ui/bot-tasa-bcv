import json
import os

VIP_FILE = "vips.json"

def cargar_vips():
    """Carga los IDs VIP guardados desde el archivo JSON."""
    if not os.path.exists(VIP_FILE):
        return []
    try:
        with open(VIP_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def guardar_vips(vips_list):
    """Guarda la lista de IDs VIP en el archivo JSON."""
    try:
        with open(VIP_FILE, "w") as f:
            json.dump(vips_list, f)
    except Exception as e:
        print(f"Error guardando VIPs: {e}")

def es_vip(user_id, admin_id):
    """Verifica si un usuario es VIP (incluyendo al Administrador)."""
    if str(user_id) == str(admin_id):
        return True
    
    vips = cargar_vips()
    return int(user_id) in vips

def agregar_vip(user_id):
    """Agrega un nuevo cliente a la lista VIP sin peligro de borrado."""
    vips = cargar_vips()
    user_id = int(user_id)
    if user_id not in vips:
        vips.append(user_id)
        guardar_vips(vips)
    return True

def remover_vip(user_id):
    """Remueve a un usuario de la lista VIP."""
    vips = cargar_vips()
    user_id = int(user_id)
    if user_id in vips:
        vips.remove(user_id)
        guardar_vips(vips)
    return True