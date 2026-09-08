import os
from bs4 import BeautifulSoup
import json
import urllib.request
import telebot
from dotenv import load_dotenv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
from database import init_db, registrar_o_actualizar_usuario, obtener_estadisticas

init_db()

MI_TELEGRAM_ID = 8884313811

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot activo 24/7")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

def run_http_server():
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
        server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()


load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN)

if TOKEN:
    print("✅ TOKEN cargado correctamente.")
else:
    raise ValueError("⚠️ No se encontró TELEGRAM_TOKEN en las variables de entorno.")

if not TOKEN:
    raise ValueError("⚠️ No se encontró TELEGRAM_TOKEN en el archivo .env")

def obtener_tasas_bcv_directo():
    """Consulta directamente la página oficial del BCV ignorando validación SSL."""
    url = "https://www.bcv.org.ve/"
    try:
        # Ignorar errores de certificado SSL de la pagina del BCV
        contexto_ssl = ssl.create_default_context()
        contexto_ssl.check_hostname = False
        contexto_ssl.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        html = urllib.request.urlopen(req, context=contexto_ssl, timeout=8).read()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extraer Dólar
        div_dolar = soup.find('div', id='dolar')
        tasa_usd = float(div_dolar.find('strong').text.strip().replace(',', '.'))
        
        # Extraer Euro
        div_euro = soup.find('div', id='euro')
        tasa_eur = float(div_euro.find('strong').text.strip().replace(',', '.'))
        
        return tasa_usd, tasa_eur
    except Exception as e:
        print(f"Error extrayendo datos directos del BCV: {e}")
        return None, None

def obtener_tasas():
    """Intenta obtener las tasas de la API y si falla o se retrasa, consulta el BCV."""
    url = "https://ve.dolarapi.com/v1/dolares/oficial"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            tasa_usd = float(data.get("promedio", 0))
            
            _, tasa_eur = obtener_tasas_bcv_directo()
            if tasa_usd > 0 and tasa_eur:
                return tasa_usd, tasa_eur
    except Exception as e:
        print(f"Error con dolarapi: {e}. Intentando lectura directa del BCV...")
    
    return obtener_tasas_bcv_directo()

@bot.message_handler(commands=['start', 'help'])
def enviar_bienvenida(message):
    registrar_o_actualizar_usuario(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    texto = (
        "🇻🇪 *¡Bienvenido al Bot de Tasas BCV!*\n\n"
        "• Escribe *tasa* para consultar el Dólar y Euro oficial.\n\n"
        "📌 *Ejemplos de conversión:*\n"
        "• `50 usd` ➔ Convierte 50 Dólares a Bolívares.\n"
        "• `50 eur` ➔ Convierte 50 Euros a Bolívares.\n"
        "• `2000 bs` ➔ Convierte 2000 Bolívares a USD y EUR.\n"
        "• `50` (número solo) ➔ Muestra la conversión rápida en ambas monedas."
    )
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def ver_estadisticas(message):
    if message.from_user.id == MI_TELEGRAM_ID:
        total, premium = obtener_estadisticas()

        texto_stats = (
            "📊 *Estadísticas de Tasa Universal Diario*\n\n"
            f"👥 *Usuarios totales:* `{total}`\n"
            f"⭐ *Usuarios VIP/Premium:* `{premium}`"
        )
        bot.reply_to(message, texto_stats, parse_mode="Markdown")
    else:
        bot.reply_to(message, "⚠️ No tienes permiso para ver esta información.")

@bot.message_handler(func=lambda message: True)
def responder_usuario(message):
    registrar_o_actualizar_usuario(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    texto_usuario = message.text.strip().lower()
    tasa_usd, tasa_eur = obtener_tasas_bcv_directo()

    if not tasa_usd or not tasa_eur:
        bot.reply_to(message, "⚠️ No se pudieron obtener las tasas del BCV en este momento.")
        return

    if texto_usuario == "tasa":
        respuesta = (
            f"🇻🇪 *Tasas Oficiales BCV*\n\n"
            f"💵 *Dólar (USD):* `{tasa_usd:,.2f} Bs.`\n"
            f"💶 *Euro (EUR):* `{tasa_eur:,.2f} Bs.`\n\n"
            "💡 *Prueba escribiendo:*\n"
            "• `100 usd` o `100 eur`\n"
            "• `5000 bs` (o `5000 ves`)"
        )
        bot.reply_to(message, respuesta, parse_mode="Markdown")

    elif "usd" in texto_usuario or "$" in texto_usuario:
        try:
            monto_limpio = texto_usuario.replace("usd", "").replace("$", "").strip()
            monto = float(monto_limpio.replace(",", "."))
            total_bs = monto * tasa_usd
            respuesta = f"💵 *{monto:,.2f} USD* equivalen a:\n🔥 *{total_bs:,.2f} Bs.* _(Tasa BCV: {tasa_usd:,.2f} Bs.)_"
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ Formato no válido. Ejemplo: `50 usd`")

    elif "eur" in texto_usuario or "euro" in texto_usuario or "€" in texto_usuario:
        try:
            monto_limpio = texto_usuario.replace("eur", "").replace("euro", "").replace("euros", "").replace("€", "").strip()
            monto = float(monto_limpio.replace(",", "."))
            total_bs = monto * tasa_eur
            respuesta = f"💶 *{monto:,.2f} EUR* equivalen a:\n🔥 *{total_bs:,.2f} Bs.* _(Tasa BCV: {tasa_eur:,.2f} Bs.)_"
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ Formato no válido. Ejemplo: `50 eur`")

    elif "bs" in texto_usuario or "ves" in texto_usuario or "bolivares" in texto_usuario:
        try:
            monto_limpio = texto_usuario.replace("bs", "").replace("ves", "").replace("bolivares", "").strip()
            monto_bs = float(monto_limpio.replace(",", "."))
            dolares = monto_bs / tasa_usd
            euros = monto_bs / tasa_eur
            
            respuesta = (
                f"🇻🇪 *{monto_bs:,.2f} Bs.* equivalen a:\n\n"
                f"💵 *{dolares:,.2f} USD*\n"
                f"💶 *{euros:,.2f} EUR*"
            )
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ Formato no válido. Ejemplo: `2500 bs`")

    else:
        try:
            monto = float(texto_usuario.replace(",", "."))
            total_usd = monto * tasa_usd
            total_eur = monto * tasa_eur
            respuesta = (
                f"💰 *Conversión general para {monto:,.2f}:*\n\n"
                f"💵 *{monto:,.2f} USD* = *{total_usd:,.2f} Bs.*\n"
                f"💶 *{monto:,.2f} EUR* = *{total_eur:,.2f} Bs.*"
            )
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "Escribe *tasa*, un número (ej: `50`), o especifica la moneda (ej: `50 usd`, `20 eur`, `1000 bs`).")


print("🚀 Bot de Telegram en ejecución...")
bot.infinity_polling(skip_pending=True)