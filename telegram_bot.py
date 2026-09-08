import os
from bs4 import BeautifulSoup
import json
import urllib.request
import telebot
from dotenv import load_dotenv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
from database import init_db, registrar_o_actualizar_usuario, obtener_estadisticas, activar_premium
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
        contexto_ssl = ssl.create_default_context()
        contexto_ssl.check_hostname = False
        contexto_ssl.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        html = urllib.request.urlopen(req, context=contexto_ssl, timeout=8).read()
        soup = BeautifulSoup(html, 'html.parser')
        
        div_dolar = soup.find('div', id='dolar')
        div_euro = soup.find('div', id='euro')
        
        if div_dolar and div_euro:
            tasa_usd = float(div_dolar.find('strong').text.strip().replace(',', '.'))
            tasa_eur = float(div_euro.find('strong').text.strip().replace(',', '.'))
            return tasa_usd, tasa_eur
        else:
            print("⚠️ No se encontraron las etiquetas 'dolar' o 'euro' en el HTML del BCV.")
            return None, None

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
            "📊 *Estadísticas de BCV Diario*\n\n"
            f"👥 *Usuarios totales:* `{total}`\n"
            f"⭐ *Usuarios VIP/Premium:* `{premium}`"
        )
        bot.reply_to(message, texto_stats, parse_mode="Markdown")
    else:
        bot.reply_to(message, "⚠️ No tienes permiso para ver esta información.")

tasa_actual, _ = obtener_tasas_bcv_directo()  # La función que ya usas para consultar el BCV
precio_usd = 2.0

@bot.message_handler(commands=['planes', 'vip', 'premium'])
def mostrar_planes(message):
    registrar_o_actualizar_usuario(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    texto_plan = (
        "⭐ *BENEFICIOS DE LA SUSCRIPCIÓN PREMIUM* ⭐\n\n"
        "Lleva el control total de tus finanzas al instante:\n\n"
        "⚡ *Alertas Instantáneas:* Recibe la tasa del día al momento exacto de su publicación.\n"
        "🧮 *Calculadora Avanzada:* Convierte montos rápidamente calculando márgenes y comisiones.\n"
        "📈 *Historial y Gráficos:* Analiza la tendencia y variación de la moneda.\n"
        "🚫 *Sin Anuncios:* Consultas ilimitadas y respuestas directas sin interrupciones.\n\n"
        "💵 *Precio:* $2 USD / mes (al cambio BCV)\n\n"
        "💳 *Datos de Pago Móvil (Ubii):*\n"
        "• *Banco:* Ubii Payments (0178) / Banco Venezolano de Crédito\n"
        "• *Teléfono:* `0414-622-4858`\n"  
        "• *Cédula:* `V-34.564.906`\n\n"   
        "📸 *¿Ya pagaste?*\n"
        "Envía la captura de pantalla o foto del comprobante directamente a este chat para activar tu cuenta."
    )
    bot.reply_to(message, texto_plan, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def recibir_comprobante(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username or "Sin Username"
    
    bot.reply_to(message, "📩 *Comprobante recibido.* Estamos validando tu pago. Te notificaremos al ser verificado.", parse_mode="Markdown")
    
    # Crear botones de aprobación para el Admin
    markup = InlineKeyboardMarkup()
    btn_aprobar = InlineKeyboardButton("✅ Aprobar VIP", callback_data=f"aprobar_{user_id}")
    btn_rechazar = InlineKeyboardButton("❌ Rechazar", callback_data=f"rechazar_{user_id}")
    markup.add(btn_aprobar, btn_rechazar)
    
    info_pago = (
        f"👤 *NUEVO SOLICITUD DE PAGO VIP*\n\n"
        f"• *Usuario:* {first_name} (@{username})\n"
        f"• *ID:* `{user_id}`"
    )
    
    # Enviar foto al admin
    foto_id = message.photo[-1].file_id
    bot.send_photo(MI_TELEGRAM_ID, foto_id, caption=info_pago, reply_markup=markup, parse_mode="Markdown")


# 3. Manejo de botones interactivos (Aprobar / Rechazar)
@bot.callback_query_handler(func=lambda call: call.data.startswith(('aprobar_', 'rechazar_')))
def procesar_aprobacion(call):
    if call.from_user.id != MI_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "⚠️ No tienes permiso.", show_alert=True)
        return

    accion, cliente_id = call.data.split('_')
    cliente_id = int(cliente_id)
    
    if accion == "aprobar":
        activar_premium(cliente_id, es_premium=1)
        
        bot.send_message(
            cliente_id, 
            "🎉 *¡Felicidades! Tu acceso VIP ha sido activado.* Ya disfrutas de todos los beneficios.", 
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id, "✅ Usuario activado como VIP")
        bot.edit_message_caption(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            caption=call.message.caption + "\n\n🟢 *ESTADO: APROBADO*"
        )
        
    elif accion == "rechazar":
        bot.send_message(
            cliente_id, 
            "⚠️ *Pago no verificado.* No pudimos validar tu comprobante. Por favor, verifica e inténtalo de nuevo.", 
            parse_mode="Markdown"
        )
        
        bot.answer_callback_query(call.id, "❌ Pago rechazado")
        bot.edit_message_caption(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            caption=call.message.caption + "\n\n🔴 *ESTADO: RECHAZADO*"
        )
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