import os
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
import telebot
import schedule
import urllib3
from flask import Flask

from vip_manager import cargar_vips, es_vip

TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_AQUI")
bot = telebot.TeleBot(TOKEN)

ULTIMA_TASA_GUARDADA = None

app = Flask('')

@app.route('/')
def home():
    return "Bot de Telegram BCV activo."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# -----------------------------------------------------------------------------
# OBTENCIÓN DE TASAS BCV
# -----------------------------------------------------------------------------
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
    except Exception as e:
        print(f"❌ Error al consultar la web del BCV: {e}")
        return None, None

# -----------------------------------------------------------------------------
# NOTIFICADOR AUTOMÁTICO VIP
# -----------------------------------------------------------------------------
def verificar_tasa_bcv_tarea():
    global ULTIMA_TASA_GUARDADA

    try:
        tasa_usd_actual, tasa_eur_actual = obtener_tasas_bcv_directo()

        if not tasa_usd_actual:
            print("⚠️ [Scheduler] No se pudo obtener la tasa en esta revisión.")
            return

        if ULTIMA_TASA_GUARDADA is None:
            ULTIMA_TASA_GUARDADA = tasa_usd_actual
            print(f"ℹ️ [Scheduler] Tasa inicial registrada: {ULTIMA_TASA_GUARDADA} Bs.")
            return

        if tasa_usd_actual != ULTIMA_TASA_GUARDADA:
            print(f"🔔 [Scheduler] ¡CAMBIO DETECTADO! Anterior: {ULTIMA_TASA_GUARDADA} | Nueva: {tasa_usd_actual}")
            
            ULTIMA_TASA_GUARDADA = tasa_usd_actual

            mensaje_alerta = (
                "🔔 *[ALERTA AUTOMÁTICA BCV]*\n\n"
                "El Banco Central de Venezuela acaba de actualizar sus tasas:\n\n"
                f"💵 *USD:* `{tasa_usd_actual:,.2f}` Bs.\n"
                f"💶 *EUR:* `{tasa_eur_actual:,.2f}` Bs.\n\n"
                "✨ _Notificación exclusiva VIP._"
            )

            vips = cargar_vips()
            for vip_id in vips.keys():
                try:
                    bot.send_message(int(vip_id), mensaje_alerta, parse_mode="Markdown")
                    time.sleep(0.05)
                except Exception as e:
                    print(f"❌ Error enviando alerta al VIP {vip_id}: {e}")

    except Exception as e:
        print(f"❌ [Scheduler] Error en el proceso: {e}")

def bucle_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(30)

schedule.every(10).minutes.do(verificar_tasa_bcv_tarea)

# -----------------------------------------------------------------------------
# COMANDOS
# -----------------------------------------------------------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.reply_to(
        message, 
        "👋 ¡Hola! Bienvenido al bot de tasas oficiales del BCV.\n\n"
        "• Usa /tasa para consultar la tasa oficial actual.\n"
        "• Escribe un monto para convertir (ej: `50 usd`, `100 eur`, `200 bs`).\n"
        "• Usa /planes para ver los datos de pago y membresía VIP ($5 USD Vitalicio).\n"
        "• Usa /vip para consultar el estado de tu suscripción.",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['tasa'])
def cmd_tasa(message):
    usd, eur = obtener_tasas_bcv_directo()
    if usd and eur:
        msg = (
            "🏛️ *Tasas Oficiales del BCV*\n\n"
            f"💵 *USD:* `{usd:,.2f}` Bs.\n"
            f"💶 *EUR:* `{eur:,.2f}` Bs."
        )
    else:
        msg = "❌ No se pudo obtener la tasa oficial en este momento. Intenta nuevamente."
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['planes'])
def cmd_planes(message):
    msg = (
        "⭐ *PASE VIP VITALICIO ($5 USD)* ⭐\n\n"
        "Accede a las herramientas avanzadas para comercios y finanzas:\n"
        "🧮 *Calculadora Avanzada:* Cálculo directo de IVA (16%) e IGTF (3%) (ejemplos: 50 usd igtf, 50 usd iva, 50 usd 16%).\n"
        "🔔 *Alertas Automáticas:* Notificación inmediata al actualizar la tasa del BCV.\n\n"
        "💳 *MÉTODOS DE PAGO: Pago Móvil / Binance Pay*\n\n"
        "📲 *Pago Móvil:*\n"
        "• Banco: `Venezolano de Crédito`\n"
        "• Cédula/RIF: `34.564.906`\n"
        "• Teléfono: `0414'622'4858`\n\n"
        "🟡 *Binance Pay / USDT o USDC:*\n"
        "• Binance ID: `218810386`\n\n"
        "📩 Al realizar el pago, envía el comprobante al administrador para activar tu acceso."
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['vip'])
def cmd_vip(message):
    user_id = message.from_user.id
    if es_vip(user_id):
        bot.reply_to(message, "🌟 *Estado: VIP Vitalicio Activo*\nTienes acceso a la Calculadora Avanzada (IVA/IGTF) y Alertas Automáticas.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "ℹ️ *Estado: Usuario Estándar*\nUsa /planes para ver los datos de pago y activar VIP.", parse_mode="Markdown")

# -----------------------------------------------------------------------------
# CALCULADORA CORREGIDA (AVANZADA + NORMAL)
# -----------------------------------------------------------------------------
@bot.message_handler(func=lambda message: True)
def responder_texto_general(message):
    if not message.text:
        return

    user_id = message.from_user.id
    texto = message.text.lower().strip()

    # Extraer el primer número (soporta 100, 100.50, 100,50)
    match = re.search(r'(\d+(?:[.,]\d+)?)', texto)
    
    if match:
        monto_str = match.group(1).replace(',', '.')
        
        # Detectar si solicitó cálculo avanzado
        es_igtf = 'igtf' in texto or '3%' in texto
        es_iva = 'iva' in texto or '16%' in texto
        es_avanzado = es_igtf or es_iva

        # 1. Bloqueo para NO VIP
        if es_avanzado and not es_vip(user_id):
            msg_bloqueo = (
                "🔒 *Función Exclusiva VIP*\n\n"
                "El cálculo de *IVA (16%)* e *IGTF (3%)* requiere suscripción VIP.\n\n"
                "👉 Consulta /planes para ver los datos de Pago Móvil o Binance."
            )
            bot.reply_to(message, msg_bloqueo, parse_mode="Markdown")
            return

        tasa_usd, tasa_eur = obtener_tasas_bcv_directo()
        if not tasa_usd or not tasa_eur:
            bot.reply_to(message, "❌ No fue posible consultar la tasa del BCV en este momento.")
            return

        try:
            monto = float(monto_str)

            # Identificar moneda solicitada
            es_euro = any(k in texto for k in ['eur', 'euro', 'euros', '€'])
            es_bolivar = any(k in texto for k in ['bs', 'bolivar', 'bolivares', 'ves'])

            # -----------------------------------------------------------------
            # CASO A: CALCULADORA AVANZADA - IGTF (3%)
            # -----------------------------------------------------------------
            if es_igtf:
                if es_euro:
                    monto_bs = monto * tasa_eur
                    igtf_eur = monto * 0.03
                    igtf_bs = monto_bs * 0.03
                    total_eur = monto + igtf_eur
                    total_bs = monto_bs + igtf_bs
                    respuesta = (
                        "🏦 *Calculadora VIP - IGTF (3%) [EUR]*\n\n"
                        f"🔹 Monto Base: `{monto:,.2f}` EUR (`{monto_bs:,.2f}` Bs.)\n"
                        f"🔹 IGTF (3%): `{igtf_eur:,.2f}` EUR (`{igtf_bs:,.2f}` Bs.)\n"
                        f"🔹 *TOTAL A PAGAR:* `{total_eur:,.2f}` EUR (`{total_bs:,.2f}` Bs.)\n\n"
                        f"📊 Tasa EUR BCV: `{tasa_eur:,.2f}` Bs."
                    )
                elif es_bolivar:
                    monto_usd = monto / tasa_usd
                    igtf_bs = monto * 0.03
                    igtf_usd = monto_usd * 0.03
                    total_bs = monto + igtf_bs
                    total_usd = monto_usd + igtf_usd
                    respuesta = (
                        "🏦 *Calculadora VIP - IGTF (3%) [Bs.]*\n\n"
                        f"🔹 Monto Base: `{monto:,.2f}` Bs. (`{monto_usd:,.2f}` USD)\n"
                        f"🔹 IGTF (3%): `{igtf_bs:,.2f}` Bs. (`{igtf_usd:,.2f}` USD)\n"
                        f"🔹 *TOTAL A PAGAR:* `{total_bs:,.2f}` Bs. (`{total_usd:,.2f}` USD)\n\n"
                        f"📊 Tasa USD BCV: `{tasa_usd:,.2f}` Bs."
                    )
                else: # Por defecto USD ($ / usd / número solo con IGTF)
                    monto_bs = monto * tasa_usd
                    igtf_usd = monto * 0.03
                    igtf_bs = monto_bs * 0.03
                    total_usd = monto + igtf_usd
                    total_bs = monto_bs + igtf_bs
                    respuesta = (
                        "🏦 *Calculadora VIP - IGTF (3%) [USD]*\n\n"
                        f"🔹 Monto Base: `{monto:,.2f}` USD (`{monto_bs:,.2f}` Bs.)\n"
                        f"🔹 IGTF (3%): `{igtf_usd:,.2f}` USD (`{igtf_bs:,.2f}` Bs.)\n"
                        f"🔹 *TOTAL A PAGAR:* `{total_usd:,.2f}` USD (`{total_bs:,.2f}` Bs.)\n\n"
                        f"📊 Tasa USD BCV: `{tasa_usd:,.2f}` Bs."
                    )

            # -----------------------------------------------------------------
            # CASO B: CALCULADORA AVANZADA - IVA (16%)
            # -----------------------------------------------------------------
            elif es_iva:
                iva = monto * 0.16
                total = monto + iva

                if es_euro:
                    total_bs = total * tasa_eur
                    respuesta = (
                        "🧾 *Calculadora VIP - IVA (16%) [EUR]*\n\n"
                        f"🔹 Subtotal: `{monto:,.2f}` EUR\n"
                        f"🔹 IVA (16%): `{iva:,.2f}` EUR\n"
                        f"🔹 *TOTAL:* `{total:,.2f}` EUR (`{total_bs:,.2f}` Bs.)\n\n"
                        f"📊 Tasa EUR BCV: `{tasa_eur:,.2f}` Bs."
                    )
                elif es_bolivar:
                    total_usd = total / tasa_usd
                    respuesta = (
                        "🧾 *Calculadora VIP - IVA (16%) [Bs.]*\n\n"
                        f"🔹 Subtotal: `{monto:,.2f}` Bs.\n"
                        f"🔹 IVA (16%): `{iva:,.2f}` Bs.\n"
                        f"🔹 *TOTAL:* `{total:,.2f}` Bs. (`{total_usd:,.2f}` USD)\n\n"
                        f"📊 Tasa USD BCV: `{tasa_usd:,.2f}` Bs."
                    )
                else: # Por defecto USD
                    total_bs = total * tasa_usd
                    respuesta = (
                        "🧾 *Calculadora VIP - IVA (16%) [USD]*\n\n"
                        f"🔹 Subtotal: `{monto:,.2f}` USD\n"
                        f"🔹 IVA (16%): `{iva:,.2f}` USD\n"
                        f"🔹 *TOTAL:* `{total:,.2f}` USD (`{total_bs:,.2f}` Bs.)\n\n"
                        f"📊 Tasa USD BCV: `{tasa_usd:,.2f}` Bs."
                    )

            # -----------------------------------------------------------------
            # CASO C: CALCULADORA NORMAL (GRATUITA)
            # -----------------------------------------------------------------
            elif es_euro:
                total_bs = monto * tasa_eur
                respuesta = (
                    "💶 *Conversión EUR ➡️ Bs. (BCV)*\n\n"
                    f"🔹 `{monto:,.2f}` EUR = `{total_bs:,.2f}` Bs.\n"
                    f"📊 Tasa EUR: `{tasa_eur:,.2f}` Bs."
                )
            elif es_bolivar:
                total_usd = monto / tasa_usd
                total_eur = monto / tasa_eur
                respuesta = (
                    "🇻🇪 *Conversión Bs. ➡️ Divisas (BCV)*\n\n"
                    f"🔹 `{monto:,.2f}` Bs. = `{total_usd:,.2f}` USD\n"
                    f"🔹 `{monto:,.2f}` Bs. = `{total_eur:,.2f}` EUR\n\n"
                    f"📊 Tasa USD: `{tasa_usd:,.2f}` Bs. | EUR: `{tasa_eur:,.2f}` Bs."
                )
            else: # Por defecto USD ($ / usd / solo números)
                total_bs = monto * tasa_usd
                respuesta = (
                    "💵 *Conversión USD ➡️ Bs. (BCV)*\n\n"
                    f"🔹 `{monto:,.2f}` USD = `{total_bs:,.2f}` Bs.\n"
                    f"📊 Tasa USD: `{tasa_usd:,.2f}` Bs."
                )

            bot.reply_to(message, respuesta, parse_mode="Markdown")

        except Exception as e:
            print(f"❌ Error procesando mensaje: {e}")
            bot.reply_to(message, "❌ Ocurrió un error al procesar la cantidad.")
    else:
        usd_val, eur_val = obtener_tasas_bcv_directo()
        if usd_val and eur_val:
            msg = (
                "🏛️ *Tasas Oficiales BCV*\n\n"
                f"💵 *USD:* `{usd_val:,.2f}` Bs.\n"
                f"💶 *EUR:* `{eur_val:,.2f}` Bs.\n\n"
                "💡 Ejemplos de uso:\n"
                "• Normales: `50 usd`, `20 eur`, `100 bs`\n"
                "• VIP Avanzado: `100 usd iva`, `50 eur igtf`, `200 bs igtf`"
            )
        else:
            msg = "❌ Servidor del BCV inaccesible en este momento."
        bot.reply_to(message, msg, parse_mode="Markdown")

# -----------------------------------------------------------------------------
# INICIO DEL BOT
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    threading.Thread(target=run_flask, daemon=True).start()

    hilo_scheduler = threading.Thread(target=bucle_scheduler, daemon=True)
    hilo_scheduler.start()
    print("🚀 Scheduler de Alertas VIP iniciado.")

    print("🤖 Bot listo y escuchando mensajes...")
    bot.infinity_polling(skip_pending=True)