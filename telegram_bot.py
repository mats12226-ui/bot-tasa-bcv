import os
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import schedule
import urllib3
from flask import Flask
from database import es_administrador

import database as db

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

bot = telebot.TeleBot(TOKEN)
app = Flask('')

ULTIMA_TASA_GUARDADA = None

@app.route('/')
def home():
    return "Bot BCV activo."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def obtener_tasas_bcv_directo():
    url = "https://www.bcv.org.ve/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        usd_container = soup.find("div", id="dolar")
        tasa_usd = usd_container.find("strong").text.strip().replace(',', '.') if usd_container else None
        eur_container = soup.find("div", id="euro")
        tasa_eur = eur_container.find("strong").text.strip().replace(',', '.') if eur_container else None
        
        if tasa_usd and tasa_eur:
            return float(tasa_usd), float(tasa_eur)
        return None, None
    except Exception:
        return None, None

def verificar_tasa_bcv_tarea():
    global ULTIMA_TASA_GUARDADA
    try:
        tasa_usd_actual, tasa_eur_actual = obtener_tasas_bcv_directo()
        if not tasa_usd_actual:
            return

        if ULTIMA_TASA_GUARDADA is None:
            ULTIMA_TASA_GUARDADA = tasa_usd_actual
            return

        if tasa_usd_actual != ULTIMA_TASA_GUARDADA:
            ULTIMA_TASA_GUARDADA = tasa_usd_actual
            mensaje_alerta = (
                "🔔 *[ALERTA AUTOMÁTICA BCV]*\n\n"
                "El Banco Central de Venezuela actualizó sus tasas:\n\n"
                f"💵 *USD:* `{tasa_usd_actual:,.2f}` Bs.\n"
                f"💶 *EUR:* `{tasa_eur_actual:,.2f}` Bs.\n\n"
                "✨ _Notificación exclusiva para miembros VIP._"
            )
            vips = db.obtener_usuarios_vip()
            for vip_id in vips:
                try:
                    bot.send_message(int(vip_id), mensaje_alerta, parse_mode="Markdown")
                    time.sleep(0.05)
                except Exception:
                    pass
    except Exception:
        pass

def bucle_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

schedule.every(10).minutes.do(verificar_tasa_bcv_tarea)

@bot.message_handler(content_types=['photo'])
def recibir_comprobante(message):
    user_id = message.from_user.id
    username = message.from_user.username or "Sin Username"
    first_name = message.from_user.first_name or "Usuario"

    db.registrar_o_actualizar_usuario(user_id, username, first_name)

    markup = InlineKeyboardMarkup()
    btn_aceptar = InlineKeyboardButton("✅ Aceptar VIP", callback_data=f"vip_aceptar_{user_id}")
    btn_rechazar = InlineKeyboardButton("❌ Rechazar", callback_data=f"vip_rechazar_{user_id}")
    markup.add(btn_aceptar, btn_rechazar)

    caption_admin = (
        "📩 *[NUEVO COMPROBANTE DE PAGO]*\n\n"
        f"👤 *Usuario:* {first_name}\n"
        f"🏷️ *Username:* @{username}\n"
        f"🆔 *ID Telegram:* `{user_id}`\n\n"
        "¿Deseas activar la membresía VIP para este usuario?"
    )

    foto_id = message.photo[-1].file_id

    try:
        bot.send_photo(
            ADMIN_ID, 
            photo=foto_id, 
            caption=caption_admin, 
            parse_mode="Markdown", 
            reply_markup=markup
        )
        bot.reply_to(
            message, 
            "📥 *Comprobante recibido con éxito.*\n\n"
            "Un administrador revisará tu pago en breve. Te notificaremos por aquí cuando tu acceso VIP sea activado.",
            parse_mode="Markdown"
        )
    except Exception:
        bot.reply_to(message, "❌ Hubo un inconveniente al enviar tu comprobante. Inténtalo más tarde.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('vip_'))
def procesar_respuesta_vip(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⚠️ No tienes permiso para realizar esta acción.", show_alert=True)
        return

    partes = call.data.split("_")
    accion = partes[1]
    cliente_id = int(partes[2])

    if accion == "aceptar":
        db.activar_premium(cliente_id, 1)
        texto_editado = call.message.caption + "\n\nSTATUS: ✅ **Aceptado y VIP Activado**"
        bot.edit_message_caption(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            caption=texto_editado, 
            parse_mode="Markdown",
            reply_markup=None
        )
        try:
            bot.send_message(
                cliente_id, 
                "🎉 *¡Felicidades! Tu pago ha sido verificado.*\n\n"
                "🌟 Ahora eres usuario **VIP Permamente**. Puedes utilizar la calculadora avanzada con recargos (`+igtf`, `+iva`, `+X%`) y recibirás alertas automáticas de tasas.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "✅ VIP activado con éxito.")

    elif accion == "rechazar":
        texto_editado = call.message.caption + "\n\nSTATUS: ❌ **Rechazado**"
        bot.edit_message_caption(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            caption=texto_editado, 
            parse_mode="Markdown",
            reply_markup=None
        )
        try:
            bot.send_message(
                cliente_id, 
                "⚠️ *Hubo un problema con la verificación de tu pago.*\n\n"
                "Tu comprobante fue rechazado. Por favor, verifica que la captura sea legible, los datos sean correctos o intenta realizar el proceso nuevamente.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "❌ Solicitud rechazada.")

@bot.message_handler(commands=['start'])
def cmd_start(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    bot.reply_to(
        message,
        "👋 ¡Hola! Bienvenido al bot de tasas del BCV.\n\n"
        "• Usa /tasa para ver los valores actuales.\n"
        "• Escribe montos para convertir (`50 usd`, `100 eur`).\n"
        "• Envía una captura/foto de tu pago para solicitar acceso **VIP**.\n"
        "• Usa /planes para ver los beneficios VIP y datos de pago.\n"
        "• Usa /vip para verificar tu membresía.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['tasa'])
def cmd_tasa(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    usd, eur = obtener_tasas_bcv_directo()
    if usd and eur:
        msg = f"🏛️ *Tasas Oficiales del BCV*\n\n💵 *USD:* `{usd:,.2f}` Bs.\n💶 *EUR:* `{eur:,.2f}` Bs."
    else:
        msg = "❌ No se pudo consultar la tasa en este momento."
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['dar_vip'])
def cmd_dar_vip(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⚠️ No tienes permiso para usar este comando.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Uso correcto: `/dar_vip <ID_o_Username>`", parse_mode="Markdown")
        return

    param = args[1].strip()
    target_id = int(param) if param.isdigit() else db.obtener_id_por_username(param)

    if target_id:
        db.activar_premium(target_id, 1)
        bot.reply_to(message, f"✅ Estatus **VIP** asignado con éxito a `{param}`.", parse_mode="Markdown")
        
        try:
            bot.send_message(
                target_id, 
                "🎉 *¡Felicidades! Tu cuenta ha sido actualizada a VIP Permamente.*\n\n"
                "🌟 Ya tienes acceso a la calculadora avanzada (`+igtf`, `+iva`, `+X%`) y a las alertas automáticas de tasa.",
                parse_mode="Markdown"
            )
        except Exception:
            bot.send_message(
                message.chat.id, 
                f"⚠️ Se activó el VIP a `{param}`, pero no se le pudo enviar el mensaje por privado.",
                parse_mode="Markdown"
            )
    else:
        bot.reply_to(message, f"❌ No se encontró al usuario `{param}` en la base de datos.", parse_mode="Markdown")

@bot.message_handler(commands=['quitar_vip'])
def cmd_quitar_vip(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "⚠️ No tienes permiso para usar este comando.")
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Uso correcto: `/quitar_vip <ID_o_Username>`", parse_mode="Markdown")
        return

    param = args[1].strip()
    target_id = int(param) if param.isdigit() else db.obtener_id_por_username(param)

    if target_id:
        db.activar_premium(target_id, 0)
        bot.reply_to(message, f"❌ Acceso **VIP** retirado a `{param}`.", parse_mode="Markdown")
        
        try:
            bot.send_message(
                target_id,
                "ℹ️ *Tu suscripción VIP ha finalizado.*\n\n"
                "Tu estado ha vuelto a usuario estándar. Si deseas renovar tu acceso, puedes consultar las opciones con /planes.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    else:
        bot.reply_to(message, f"❌ No se encontró al usuario `{param}` en la base de datos.", parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    total, vips, hoy, trimestre = db.obtener_estadisticas()

    msg = (
        "📊 *Estadísticas de Uso del Bot*\n\n"
        f"📅 *Conectados hoy (24h):* `{hoy}`\n"
        f"🗓️ *Conectados este trimestre (90d):* `{trimestre}`\n"
        f"⭐ *Usuarios VIP activos:* `{vips}`\n"
        f"👥 *Total registrado en BD:* `{total}`"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['planes'])
def cmd_planes(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    tasa_usd, _ = obtener_tasas_bcv_directo()
    
    if tasa_usd:
        monto_bs = 4.0 * tasa_usd
        precio_texto = f"💵 *4.00 USD* / 🇻🇪 *{monto_bs:,.2f} Bs.* (a Tasa BCV)"
    else:
        precio_texto = "💵 *4.00 USD* (o en Bs. a Tasa Oficial BCV del día)"

    msg = (
        "⭐ *MEMBRESÍA VIP PERMANENTE* ⭐\n\n"
        "🔓 *Pago único y acceso de por vida.*\n"
        f"💰 *Precio:* {precio_texto}\n\n"
        "✨ *BENEFICIOS EXCLUSIVOS:*\n"
        "• Alertas automáticas en tiempo real al actualizarse la tasa oficial.\n"
        "• Uso ilimitado de la Calculadora Avanzada (`+igtf`, `+iva`, `+X%`).\n\n"
        "💳 *MÉTODOS DE PAGO:*\n\n"
        "📲 *Pago Móvil:*\n"
        "• Banco: `Venezolano de Crédito`\n"
        "• Cédula/RIF: `34.564.906`\n"
        "• Teléfono: `0414-622-4858`\n\n"
        "🟡 *Binance Pay / USDC o USDT:*\n"
        "• Binance ID / Email: `gus12226@gmail.com`\n\n"
        "📩 *Envía la captura del pago por este chat* y un administrador activará tu acceso."
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['vip'])
def cmd_vip(message):
    db.registrar_o_actualizar_usuario(message.from_user.id, message.from_user.username, message.from_user.first_name)
    if db.es_usuario_vip(message.from_user.id):
        bot.reply_to(message, "🌟 *Estado: VIP Permanente Activo*\nTienes acceso a la Calculadora Avanzada y a Alertas Automáticas.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "ℹ️ *Estado: Usuario Estándar*\nUsa /planes para adquirir tu acceso VIP.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def procesar_calculadora(message):
    if not message.text:
        return

    user_id = message.from_user.id
    db.registrar_o_actualizar_usuario(user_id, message.from_user.username, message.from_user.first_name)

    texto = message.text.lower().strip()

    match = re.search(r'(\d+(?:[.,]\d+)?)', texto)
    if not match:
        return

    try:
        monto_base = float(match.group(1).replace(',', '.'))
    except ValueError:
        return

    tiene_igtf = '+igtf' in texto or 'igtf' in texto
    tiene_iva = '+iva' in texto or 'iva' in texto
    match_pct = re.search(r'\+\s*(\d+(?:[.,]\d+)?)\s*%', texto)
    porcentaje_extra = float(match_pct.group(1).replace(',', '.')) if match_pct else 0.0

    es_calculo_vip = tiene_igtf or tiene_iva or (porcentaje_extra > 0)

    if es_calculo_vip and not db.es_usuario_vip(user_id):
        bot.reply_to(
            message,
            "🔒 *Función Exclusiva VIP*\n\n"
            "La calculadora con recargos (`+igtf`, `+iva`, `+X%`) es solo para usuarios VIP.\n"
            "Usa /planes para ver los métodos de pago.",
            parse_mode="Markdown"
        )
        return

    tasa_usd, tasa_eur = obtener_tasas_bcv_directo()
    if not tasa_usd or not tasa_eur:
        bot.reply_to(message, "❌ No se pudo consultar la tasa oficial en este momento.")
        return

    es_euro = any(k in texto for k in ['eur', 'euro', 'euros', '€'])
    es_bolivar = any(k in texto for k in ['bs', 'bolivar', 'bolivares', 'ves'])

    if es_calculo_vip:
        monto_acumulado = monto_base
        desglose = [f"🔹 Monto Base: `{monto_base:,.2f}`"]

        if tiene_iva:
            monto_iva = monto_base * 0.16
            monto_acumulado += monto_iva
            desglose.append(f"🔹 IVA (16%): `{monto_iva:,.2f}`")

        if tiene_igtf:
            monto_igtf = monto_acumulado * 0.03
            monto_acumulado += monto_igtf
            desglose.append(f"🔹 IGTF (3%): `{monto_igtf:,.2f}`")

        if porcentaje_extra > 0:
            monto_extra = monto_base * (porcentaje_extra / 100.0)
            monto_acumulado += monto_extra
            desglose.append(f"🔹 Recargo Extra ({porcentaje_extra}%): `{monto_extra:,.2f}`")

        if es_euro:
            total_bs = monto_acumulado * tasa_eur
            moneda = "EUR"
            tasa_ref = f"📊 Tasa EUR BCV: `{tasa_eur:,.2f}` Bs."
            equivalencia = f"\n💵 *TOTAL EN BS:* `{total_bs:,.2f}` Bs."
        elif es_bolivar:
            total_usd = monto_acumulado / tasa_usd
            moneda = "Bs."
            tasa_ref = f"📊 Tasa USD BCV: `{tasa_usd:,.2f}` Bs."
            equivalencia = f"\n💵 *TOTAL EN USD:* `{total_usd:,.2f}` USD"
        else:
            total_bs = monto_acumulado * tasa_usd
            moneda = "USD"
            tasa_ref = f"📊 Tasa USD BCV: `{tasa_usd:,.2f}` Bs."
            equivalencia = f"\n💵 *TOTAL EN BS:* `{total_bs:,.2f}` Bs."

        desglose_texto = "\n".join(desglose)
        respuesta = (
            f"🧮 *Calculadora VIP ({moneda})*\n\n"
            f"{desglose_texto}\n"
            f"-----------------------------------\n"
            f"🏁 *TOTAL FINAL:* `{monto_acumulado:,.2f}` {moneda}"
            f"{equivalencia}\n\n"
            f"{tasa_ref}"
        )
    else:
        if es_euro:
            total_bs = monto_base * tasa_eur
            respuesta = f"💶 *Conversión EUR ➡️ Bs. (BCV)*\n\n🔹 `{monto_base:,.2f}` EUR = `{total_bs:,.2f}` Bs.\n📊 Tasa EUR: `{tasa_eur:,.2f}` Bs."
        elif es_bolivar:
            total_usd = monto_base / tasa_usd
            respuesta = f"🇻🇪 *Conversión Bs. ➡️ USD (BCV)*\n\n🔹 `{monto_base:,.2f}` Bs. = `{total_usd:,.2f}` USD\n📊 Tasa USD: `{tasa_usd:,.2f}` Bs."
        else:
            total_bs = monto_base * tasa_usd
            respuesta = f"💵 *Conversión USD ➡️ Bs. (BCV)*\n\n🔹 `{monto_base:,.2f}` USD = `{total_bs:,.2f}` Bs.\n📊 Tasa USD: `{tasa_usd:,.2f}` Bs."

    bot.reply_to(message, respuesta, parse_mode="Markdown")

if __name__ == "__main__":
    db.init_db()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    threading.Thread(target=run_flask, daemon=True).start()

    hilo_scheduler = threading.Thread(target=bucle_scheduler, daemon=True)
    hilo_scheduler.start()

    bot.infinity_polling(skip_pending=True)