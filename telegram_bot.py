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
MI_TELEGRAM_ID = 123456789

bot = telebot.TeleBot(TOKEN)
ULTIMA_TASA_GUARDADA = None

app = Flask('')

@app.route('/')
def home():
    return "Bot de Telegram BCV activo."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def obtener_tasas_bcv_directo():
    url = "https://www.bcv.org.ve/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        usd_container = soup.find("div", id="dolar")
        tasa_usd = usd_container.find("strong").text.strip().replace(',', '.') if usd_container else None
        
        eur_container = soup.find("div", id="euro")
        tasa_eur = eur_container.find("strong").text.strip().replace(',', '.') if eur_container else None
        
        return tasa_usd, tasa_eur
    except Exception as e:
        print(f"❌ Error al consultar la web del BCV: {e}")
        return None, None

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
                "🔔 [ALERTA AUTOMÁTICA BCV]\n\n"
                "El Banco Central de Venezuela acaba de actualizar sus tasas:\n\n"
                f"💵 USD: {tasa_usd_actual} Bs.\n"
                f"💶 EUR: {tasa_eur_actual} Bs.\n\n"
                "✨ Recibes esta notificación por ser usuario VIP."
            )

            vips = cargar_vips()
            for vip_id in vips.keys():
                try:
                    bot.send_message(int(vip_id), mensaje_alerta)
                    time.sleep(0.05)
                except Exception as e:
                    print(f"❌ Error enviando alerta a {vip_id}: {e}")

    except Exception as e:
        print(f"❌ [Scheduler] Error en la ejecución: {e}")

def bucle_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

schedule.every(15).minutes.do(verificar_tasa_bcv_tarea)

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.reply_to(
        message, 
        "👋 ¡Hola! Bienvenido al bot de tasas oficiales del BCV.\n\n"
        "Usa /tasa para consultar la tasa actual o /vip para ver tu estado.\n\n"
        "💡 Puedes escribir montos directamente como:\n"
        "• 50 usd\n"
        "• 50 eur\n"
        "• 200 bs"
    )

@bot.message_handler(commands=['tasa'])
def cmd_tasa(message):
    usd, eur = obtener_tasas_bcv_directo()
    if usd:
        msg = (
            "🏛️ Tasas Oficiales del BCV\n\n"
            f"💵 USD: {usd} Bs.\n"
            f"💶 EUR: {eur} Bs."
        )
    else:
        msg = "❌ No se pudo obtener la tasa oficial en este momento. Intenta más tarde."
    bot.reply_to(message, msg)

@bot.message_handler(commands=['vip'])
def cmd_vip(message):
    user_id = message.from_user.id
    if es_vip(user_id):
        bot.reply_to(message, "🌟 ¡Eres un miembro VIP Vitalicio! Tienes acceso a alertas automáticas de cambio de tasa.")
    else:
        bot.reply_to(message, "ℹ️ No tienes una suscripción VIP activa. Contacta al administrador para obtener acceso.")

@bot.message_handler(commands=['probar_alertas'])
def cmd_probar_alertas(message):
    user_id = message.from_user.id
    
    if user_id != MI_TELEGRAM_ID:
        bot.reply_to(message, "⛔ Este comando solo puede ser ejecutado por el administrador.")
        return

    vips = cargar_vips()
    total = len(vips)

    if total == 0:
        bot.reply_to(message, "⚠️ No hay usuarios en vips.json para probar.")
        return

    usd, eur = obtener_tasas_bcv_directo()
    if not usd:
        bot.reply_to(message, "❌ Error al obtener tasas para la prueba.")
        return

    bot.reply_to(message, f"🔄 Enviando prueba de alerta a {total} usuario(s) VIP...")

    mensaje_prueba = (
        "🔔 [PRUEBA DE ALERTA VIP]\n\n"
        "Simulación de actualización de tasa BCV:\n\n"
        f"💵 USD: {usd} Bs.\n"
        f"💶 EUR: {eur} Bs.\n\n"
        "✨ Pase VIP Vitalicio Activo."
    )

    exitos, fallos = 0, 0
    for vip_id in vips.keys():
        try:
            bot.send_message(int(vip_id), mensaje_prueba)
            exitos += 1
            time.sleep(0.05)
        except Exception as e:
            print(f"❌ Error en prueba para {vip_id}: {e}")
            fallos += 1

    bot.send_message(
        MI_TELEGRAM_ID, 
        f"✅ Prueba finalizada\n\nExitosos: {exitos}\nFallidos: {fallos}"
    )

@bot.message_handler(func=lambda message: True)
def responder_texto_general(message):
    if not message.text:
        return

    texto = message.text.lower().strip()
    
    usd_str, eur_str = obtener_tasas_bcv_directo()
    
    if not usd_str or not eur_str:
        bot.reply_to(message, "❌ No se pudo obtener la tasa en este momento. Intenta más tarde con /tasa.")
        return

    try:
        tasa_usd = float(usd_str)
        tasa_eur = float(eur_str)
    except Exception:
        bot.reply_to(message, "❌ Error al procesar las tasas del BCV.")
        return

    match = re.search(r'(\d+(?:[.,]\d+)?)', texto)
    
    if match:
        try:
            monto = float(match.group(1).replace(',', '.'))
            
            if 'eur' in texto or 'euro' in texto or 'euros' in texto:
                total_bs = monto * tasa_eur
                respuesta = (
                    "💶 Conversión EUR ➡️ Bs. (BCV)\n\n"
                    f"🔹 {monto:,.2f} EUR = {total_bs:,.2f} Bs.\n"
                    f"📊 Tasa Euro: {tasa_eur} Bs."
                )
            elif 'bs' in texto or 'bolivar' in texto or 'bolivares' in texto or 'ves' in texto:
                total_usd = monto / tasa_usd
                total_eur = monto / tasa_eur
                respuesta = (
                    "🇻🇪 Conversión Bs. ➡️ Divisas (BCV)\n\n"
                    f"🔹 {monto:,.2f} Bs. = {total_usd:,.2f} USD\n"
                    f"🔹 {monto:,.2f} Bs. = {total_eur:,.2f} EUR\n\n"
                    f"📊 Tasa USD: {tasa_usd} Bs. | EUR: {tasa_eur} Bs."
                )
            else:
                total_bs = monto * tasa_usd
                respuesta = (
                    "💵 Conversión USD ➡️ Bs. (BCV)\n\n"
                    f"🔹 {monto:,.2f} USD = {total_bs:,.2f} Bs.\n"
                    f"📊 Tasa Dólar: {tasa_usd} Bs."
                )
                
            bot.reply_to(message, respuesta)
        except Exception as e:
            print(f"Error en calculo: {e}")
            bot.reply_to(message, "❌ Ocurrió un error al hacer el cálculo.")
    else:
        msg = (
            "🏛️ Tasas Oficiales BCV\n\n"
            f"💵 USD: {tasa_usd} Bs.\n"
            f"💶 EUR: {tasa_eur} Bs.\n\n"
            "💡 Escribe un monto para calcular:\n"
            "• 50 usd\n"
            "• 50 eur\n"
            "• 200 bs"
        )
        bot.reply_to(message, msg)

if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    threading.Thread(target=run_flask, daemon=True).start()

    hilo_scheduler = threading.Thread(target=bucle_scheduler, daemon=True)
    hilo_scheduler.start()
    print("🚀 Scheduler iniciado en segundo plano.")

    print("🤖 Bot iniciado y escuchando mensajes...")
    bot.infinity_polling(skip_pending=True)