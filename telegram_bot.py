import os
import json
import urllib.request
import telebot
from dotenv import load_dotenv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot activo 24/7")

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

def obtener_tasas():
    url_dolares = "https://ve.dolarapi.com/v1/dolares/oficial"
    url_euros = "https://ve.dolarapi.com/v1/euros/oficial"

    headers = {'User-Agent': 'Mozilla/5.0'}

    tasa_usd = None
    tasa_eur = None

    try:
        req_usd = urllib.request.Request(url_dolares, headers=headers)
        with urllib.request.urlopen(req_usd) as res:
            data_usd = json.loads(res.read().decode())
            tasa_usd = data_usd.get('promedio')

        req_eur = urllib.request.Request(url_euros, headers=headers)
        with urllib.request.urlopen(req_eur) as res:
            data_eur = json.loads(res.read().decode())
            tasa_eur = data_eur.get('promedio')

        return tasa_usd, tasa_eur

    except Exception as e:
        print(f"Error al obtener tasas desde la API: {e}")
        return None, None


@bot.message_handler(commands=['start', 'help'])
def enviar_bienvenida(message):
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


@bot.message_handler(func=lambda message: True)
def responder_usuario(message):
    texto_usuario = message.text.strip().lower()
    tasa_usd, tasa_eur = obtener_tasas()

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
bot.infinity_polling()