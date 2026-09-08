import os
import json
import ssl
import time
import re
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeChat
import re

from database import (
    init_db, 
    registrar_o_actualizar_usuario, 
    obtener_estadisticas, 
    activar_premium, 
    es_usuario_vip, 
    obtener_usuarios_vip,
    obtener_id_por_username
)

init_db()

ADMIN_ID_RAW = os.getenv("TELEGRAM_ADMIN_ID")
MI_TELEGRAM_ID = int(ADMIN_ID_RAW) if ADMIN_ID_RAW else None
TASA_ULTIMA_USD = None
TASA_ULTIMA_EUR = None

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

if not TOKEN:
    raise ValueError("⚠️ No se encontró TELEGRAM_TOKEN en las variables de entorno.")

bot = telebot.TeleBot(TOKEN)
print("✅ TOKEN cargado correctamente.")

def registrar_comandos_sugeridos():
    comandos_generales = [
        BotCommand("start", "Iniciar el bot y ver el menú principal"),
        BotCommand("tasa", "Consultar la tasa del Dólar y Euro oficial BCV"),
        BotCommand("planes", "Ver beneficios y suscribirte a la versión VIP"),
        BotCommand("vip", "Ver beneficios o estado de tu suscripción VIP"),
        BotCommand("help", "Instrucciones de uso y comandos disponibles")
    ]
    bot.set_my_commands(comandos_generales)

    comandos_admin = comandos_generales + [
        BotCommand("stats", "👑 [Admin] Ver estadísticas generales de usuarios y VIP")
    ]
    try:
        bot.set_my_commands(comandos_admin, scope=BotCommandScopeChat(chat_id=MI_TELEGRAM_ID))
    except Exception as e:
        print(f"No se pudo establecer menú de admin: {e}")

@bot.message_handler(commands=['darvip', 'quitarvip'])
def cmd_gestionar_vip(message):
    # Verificar que solo el administrador use el comando
    if message.from_user.id != MI_TELEGRAM_ID:
        bot.reply_to(message, "⚠️ No tienes autorización para ejecutar este comando.")
        return

    partes = message.text.split(maxsplit=1)
    if len(partes) < 2:
        bot.reply_to(message, "⚠️ *Formato incorrecto.*\nUso: `/darvip @username` o `/darvip 12345678`", parse_mode="Markdown")
        return

    target = partes[1].strip()
    accion = message.text.split()[0].replace("/", "")
    es_vip = 1 if accion == "darvip" else 0

    # Si se ingresó un ID numérico directo
    if target.isdigit():
        target_id = int(target)
    else:
        # Buscar por Username en SQLite
        target_id = obtener_id_por_username(target)
        if not target_id:
            bot.reply_to(
                message, 
                f"❌ No se encontró al usuario `{target}` en la base de datos.\n\n"
                "📌 *Causas posibles:*\n"
                "1. El usuario nunca ha iniciado el bot con `/start`.\n"
                "2. El usuario no tiene un `@username` público en Telegram.", 
                parse_mode="Markdown"
            )
            return

    activar_premium(target_id, es_vip=es_vip)

    estado = "activado" if es_vip == 1 else "desactivado"
    bot.reply_to(message, f"✅ Acceso VIP *{estado}* para el usuario (ID: `{target_id}`).", parse_mode="Markdown")
    
    try:
        msg = "🎉 *¡Tu suscripción VIP ha sido activada!*" if es_vip == 1 else "🔴 Tu acceso VIP ha finalizado."
        bot.send_message(target_id, msg, parse_mode="Markdown")
    except Exception as e:
        print(f"No se pudo notificar al usuario {target_id}: {e}")

def obtener_tasas_bcv_directo():
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
            return None, None

    except Exception as e:
        print(f"Error extrayendo datos directos del BCV: {e}")
        return None, None

def monitorear_tasas_bcv():
    global TASA_ULTIMA_USD, TASA_ULTIMA_EUR
    while True:
        try:
            usd, eur = obtener_tasas_bcv_directo()
            if usd and eur:
                if TASA_ULTIMA_USD is not None and TASA_ULTIMA_EUR is not None:
                    if usd != TASA_ULTIMA_USD or eur != TASA_ULTIMA_EUR:
                        TASA_ULTIMA_USD = usd
                        TASA_ULTIMA_EUR = eur
                        notificar_usuarios_vip(usd, eur)
                else:
                    TASA_ULTIMA_USD = usd
                    TASA_ULTIMA_EUR = eur
        except Exception as e:
            print(f"Error en hilo de monitoreo: {e}")
        time.sleep(900)

def notificar_usuarios_vip(tasa_usd, tasa_eur):
    lista_vips = obtener_usuarios_vip()
    mensaje_alerta = (
        "🚨 *¡ALERTA BCV: TASA ACTUALIZADA!* 🚨\n\n"
        f"💵 *Dólar (USD):* `{tasa_usd:,.2f} Bs.`\n"
        f"💶 *Euro (EUR):* `{tasa_eur:,.2f} Bs.`\n\n"
        "⚡ _Notificación automática exclusiva para miembros VIP._"
    )
    for user_id in lista_vips:
        try:
            bot.send_message(user_id, mensaje_alerta, parse_mode="Markdown")
        except Exception as e:
            print(f"No se pudo enviar alerta VIP a {user_id}: {e}")

threading.Thread(target=monitorear_tasas_bcv, daemon=True).start()

def procesar_calculadora(texto, tasa_bcv_usd, tasa_bcv_eur):
    texto = texto.lower().strip()

    incluye_igtf = "+igtf" in texto or "igtf" in texto
    incluye_iva = "+iva" in texto or "iva" in texto

    patron = r'(\d+(?:[\.,]\d+)?)\s*(usd|bs|bolivares|eur|euro|euros)?'
    coincidencia = re.search(patron, texto)

    if not coincidencia:
        return "⚠️ Formato no reconocido. Ejemplo: `50 usd`, `2500 bs +igtf`, `40 eur`."

    monto = float(coincidencia.group(1).replace(',', '.'))
    moneda = coincidencia.group(2) if coincidencia.group(2) else "usd"

    monto_con_impuestos = monto
    if incluye_igtf:
        monto_con_impuestos *= 1.03
    if incluye_iva:
        monto_con_impuestos *= 1.16

    # Calcular conversiones según la moneda ingresada
    if moneda in ["usd"]:
        monto_bs = monto_con_impuestos * tasa_bcv_usd
        respuesta = (
            f"💵 *Monto:* `${monto:.2f} USD`\n"
            f"{'➕ *Con IGTF (3%):* `$' + f'{monto_con_impuestos:.2f} USD`\n' if incluye_igtf else ''}"
            f"🇻🇪 *Total en Bs (Tasa BCV):* `{monto_bs:,.2f} Bs`"
        )

    elif moneda in ["bs", "bolivares"]:
        monto_usd = monto_con_impuestos / tasa_bcv_usd
        respuesta = (
            f"🇻🇪 *Monto:* `{monto:,.2f} Bs`\n"
            f"💵 *Total en USD (Tasa BCV):* `${monto_usd:.2f} USD`"
        )

    elif moneda in ["eur", "euro", "euros"]:
        monto_bs = monto_con_impuestos * tasa_bcv_eur
        respuesta = (
            f"💶 *Monto:* `€{monto:.2f} EUR`\n"
            f"🇻🇪 *Total en Bs (Tasa BCV Euro):* `{monto_bs:,.2f} Bs`"
        )

    return respuesta

@bot.message_handler(commands=['start', 'help'])
def enviar_bienvenida(message):
    user_id = message.from_user.id
    registrar_o_actualizar_usuario(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    if es_usuario_vip(user_id):
        comandos_vip = [
            BotCommand("start", "Menú principal"),
            BotCommand("tasa", "Consultar la tasa del Dólar y Euro BCV"),
            BotCommand("vip", "Ver estado de tu suscripción VIP"),
            BotCommand("planes", "Ver estado de tu suscripción VIP"),
            BotCommand("help", "Instrucciones de uso")
        ]
        try:
            bot.set_my_commands(comandos_vip, scope=BotCommandScopeChat(chat_id=user_id))
        except Exception as e:
            print(f"Error asignando comandos VIP en start: {e}")

    texto = (
        "🇻🇪 *¡Bienvenido al Bot de Tasas BCV!*\n\n"
        "• Escribe *tasa* para consultar el Dólar y Euro oficial.\n"
        "• Usa /planes o /vip para conocer los beneficios de la *Suscripción VIP*.\n\n"
        "📌 *Ejemplos de conversión rápida:*\n"
        "• `50 usd` ➔ Convierte 50 Dólares a Bolívares.\n"
        "• `50 eur` ➔ Convierte 50 Euros a Bolívares.\n"
        "• `2000 bs` ➔ Convierte 2000 Bolívares a USD y EUR.\n\n"
        "⭐ *Exclusivo VIP:* Agrega impuestos/márgenes como `50 usd +igtf`, `100 usd +16%` o `50 usd +3%`."
    )
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def ver_estadisticas(message):
    if message.from_user.id == MI_TELEGRAM_ID:
        total, vips = obtener_estadisticas()
        texto_stats = (
            "📊 *Estadísticas de BCV Diario*\n\n"
            f"👥 *Usuarios totales:* `{total}`\n"
            f"⭐ *Usuarios VIP:* `{vips}`"
        )
        bot.reply_to(message, texto_stats, parse_mode="Markdown")
    else:
        bot.reply_to(message, "⚠️ No tienes permiso para ver esta información.")

@bot.message_handler(commands=['planes', 'vip', 'premium'])
def mostrar_planes(message):
    user_id = message.from_user.id
    registrar_o_actualizar_usuario(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    
    if es_usuario_vip(user_id):
        texto_vip = (
            "⭐ *ESTADO DE TU SUSCRIPCIÓN VIP*\n\n"
            "🟢 *Estado:* Activo\n\n"
            "✨ *Tus Beneficios Activos:*\n"
            "• 🔔 *Alertas Automáticas:* Recibes la tasa en cuanto el BCV la actualiza.\n"
            "• 🧮 *Calculadora con Impuestos:* Puedes calcular IGTF (+3%), IVA (+16%) o porcentajes personalizados (`50 usd +igtf`, `100 usd +5%`).\n"
            "• ⚡ *Prioridad:* Respuestas inmediatas sin esperas.\n\n"
            "¡Gracias por apoyar el proyecto!"
        )
        bot.reply_to(message, texto_vip, parse_mode="Markdown")
        return

    tasa_usd, _ = obtener_tasas_bcv_directo()
    precio_usd = 2.0
    
    if tasa_usd:
        precio_bs = round(precio_usd * tasa_usd, 2)
        monto_texto = f"💵 *Precio:* $2 USD / mes (al cambio BCV: `{precio_bs:,.2f} Bs.`)\n\n"
    else:
        monto_texto = "💵 *Precio:* $2 USD / mes (calculado al cambio oficial BCV)\n\n"

    texto_plan = (
        "⭐ *BENEFICIOS DE LA SUSCRIPCIÓN VIP* ⭐\n\n"
        "⚡ *Alertas Automáticas Inmediatas:* Sé el primero en enterarte cuando el BCV actualice la tasa sin enviar comandos.\n"
        "🧮 *Calculadora Avanzada con Impuestos:* Calcula conversiones sumando automáticamente IGTF (3%), IVA (16%) o comisiones personalizadas (ej: `50 usd +igtf`, `100 usd +10%`).\n"
        "🚫 *Sin Interrupciones:* Consultas y uso sin límites.\n\n"
        f"{monto_texto}"
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
    
    markup = InlineKeyboardMarkup()
    btn_aprobar = InlineKeyboardButton("✅ Aprobar VIP", callback_data=f"aprobar_{user_id}")
    btn_rechazar = InlineKeyboardButton("❌ Rechazar", callback_data=f"rechazar_{user_id}")
    markup.add(btn_aprobar, btn_rechazar)
    
    info_pago = (
        f"👤 *NUEVA SOLICITUD DE PAGO VIP*\n\n"
        f"• *Usuario:* {first_name} (@{username})\n"
        f"• *ID:* `{user_id}`"
    )
    
    foto_id = message.photo[-1].file_id
    bot.send_photo(MI_TELEGRAM_ID, foto_id, caption=info_pago, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('aprobar_', 'rechazar_')))
def procesar_aprobacion(call):
    if call.from_user.id != MI_TELEGRAM_ID:
        bot.answer_callback_query(call.id, "⚠️ No tienes permiso.", show_alert=True)
        return

    accion, cliente_id = call.data.split('_')
    cliente_id = int(cliente_id)
    
    if accion == "aprobar":
        activar_premium(cliente_id, es_vip=1)
        
        comandos_vip = [
            BotCommand("start", "Menú principal"),
            BotCommand("tasa", "Consultar la tasa del Dólar y Euro BCV"),
            BotCommand("vip", "Ver estado de tu suscripción VIP"),
            BotCommand("planes", "Ver estado de tu suscripción VIP"),
            BotCommand("help", "Instrucciones de uso"),
        ]
        try:
            bot.set_my_commands(comandos_vip, scope=BotCommandScopeChat(chat_id=cliente_id))
        except Exception as e:
            print(f"Error asignando comandos VIP: {e}")
        
        bot.send_message(
            cliente_id, 
            "🎉 *¡Felicidades! Tu acceso VIP ha sido activado.* Ya disfrutas de las alertas automáticas y la calculadora con impuestos.", 
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
    user_id = message.from_user.id
    registrar_o_actualizar_usuario(
        user_id=user_id,
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
            "• `5000 bs`"
        )
        bot.reply_to(message, respuesta, parse_mode="Markdown")

    elif "usd" in texto_usuario or "$" in texto_usuario:
        es_vip = es_usuario_vip(user_id)
        tiene_recargo = "+" in texto_usuario or "igtf" in texto_usuario or "iva" in texto_usuario
        
        if tiene_recargo and not es_vip:
            bot.reply_to(
                message, 
                "⭐ *Función VIP:* El cálculo con IGTF, IVA o porcentajes personalizados es exclusivo de la suscripción VIP.\n\nUsa /planes para activar tu cuenta.", 
                parse_mode="Markdown"
            )
            return

        porcentaje_extra = 0.0
        etiqueta_impuesto = ""
        
        if "igtf" in texto_usuario:
            porcentaje_extra = 0.03
            etiqueta_impuesto = " (incluye +3% IGTF)"
        elif "iva" in texto_usuario:
            porcentaje_extra = 0.16
            etiqueta_impuesto = " (incluye +16% IVA)"
        else:
            match = re.search(r'\+\s*(\d+[\.,]?\d*)\s*%', texto_usuario)
            if match:
                porcentaje_extra = float(match.group(1).replace(",", ".")) / 100.0
                etiqueta_impuesto = f" (incluye +{match.group(1)}%)"

        try:
            monto_limpio = re.sub(r'[^0-9,\.]', '', texto_usuario.split('+')[0])
            monto = float(monto_limpio.replace(",", "."))
            monto_con_impuesto = monto * (1 + porcentaje_extra)
            total_bs = monto_con_impuesto * tasa_usd
            
            respuesta = (
                f"💵 *{monto:,.2f} USD*{etiqueta_impuesto} equivalen a:\n"
                f"🔥 *{total_bs:,.2f} Bs.* _(Tasa BCV: {tasa_usd:,.2f} Bs.)_"
            )
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ Formato no válido. Ejemplo: `50 usd` o `50 usd +igtf`")

    elif "eur" in texto_usuario or "euro" in texto_usuario or "€" in texto_usuario:
        try:
            monto_limpio = re.sub(r'[^0-9,\.]', '', texto_usuario)
            monto = float(monto_limpio.replace(",", "."))
            total_bs = monto * tasa_eur
            respuesta = f"💶 *{monto:,.2f} EUR* equivalen a:\n🔥 *{total_bs:,.2f} Bs.* _(Tasa BCV: {tasa_eur:,.2f} Bs.)_"
            bot.reply_to(message, respuesta, parse_mode="Markdown")
        except ValueError:
            bot.reply_to(message, "⚠️ Formato no válido. Ejemplo: `50 eur`")

    elif "bs" in texto_usuario or "ves" in texto_usuario or "bolivares" in texto_usuario:
        try:
            monto_limpio = re.sub(r'[^0-9,\.]', '', texto_usuario)
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