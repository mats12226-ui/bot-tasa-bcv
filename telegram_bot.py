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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=12, verify=False)
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
        "• Usa /tasa para consultar la tasa oficial actual.\n"
        "• Escribe un monto para convertir (ej: '50 usd', '100 eur', '500 bs').\n"
        "• Usa /planes para ver los beneficios de la membresía VIP ($5 USD Vitalicio).\n"
        "• Usa /vip para consultar el estado de tu suscripción."
    )

@bot.message_handler(commands=['tasa'])
def cmd_tasa(message):
    usd, eur = obtener_tasas_bcv_directo()
    if usd and eur:
        msg = (
            "🏛️ Tasas Oficiales del BCV\n\n"
            f"💵 USD: {usd} Bs.\n"
            f"💶 EUR: {eur} Bs."
        )
    else:
        msg = "❌ No se pudo obtener la tasa oficial en este momento. Intenta más tarde."
    bot.reply_to(message, msg)

@bot.message_handler(commands=['planes'])
def cmd_planes(message):
    msg = (
        "⭐ PASE VIP VITALICIO ($5 USD) ⭐\n\n"
        "Obtén acceso a los cálculos avanzados e impuestos:\n\n"
        "🧮 Calculadora de Impuestos (Cálculo directo de IGTF 3% e IVA 16%).\n"
        "🔔 Alertas Automáticas en tiempo real al actualizar la tasa del BCV.\n"
        "⚡ Atención prioritaria y sin interrupciones.\n\n"
        "💳 Métodos de Pago: Pago Móvil, Binance, Zelle.\n"
        "📩 Para activar tu pase VIP, escribe al administrador."
    )
    bot.reply_to(message, msg)

@bot.message_handler(commands=['vip'])
def cmd_vip(message):
    user_id = message.from_user.id
    if es_vip(user_id):
        bot.reply_to(message, "🌟 ¡Eres un miembro VIP Vitalicio! Tienes acceso a alertas automáticas y cálculo de impuestos.")
    else:
        bot.reply_to(message, "ℹ️ No tienes una suscripción VIP activa. Usa /planes para más información.")

@bot.message_handler(func=lambda message: True)
def responder_texto_general(message):
    if not message.text:
        return

    user_id = message.from_user.id
    texto = message.text.lower().strip()

    # Buscar cualquier número en el mensaje
    match = re.search(r'(\d+(?:[.,]\d+)?)', texto)
    
    if match:
        es_calculo_avanzado = 'igtf' in texto or 'iva' in texto

        # Si intenta usar IVA o IGTF y no es VIP, se bloquea la función avanzada
        if es_calculo_avanzado and not es_vip(user_id):
            msg_bloqueo = (
                "🔒 El cálculo automático de IVA (16%) e IGTF (3%) es una función VIP.\n\n"
                "⭐ Con el Pase VIP Vitalicio ($5 USD) obtienes:\n"
                "• Cálculo automático de IVA e IGTF en texto directo.\n"
                "• Alertas de cambio de tasa en tiempo real.\n\n"
                "Usa /planes para más información."
            )
            bot.reply_to(message, msg_bloqueo)
            return

        usd_str, eur_str = obtener_tasas_bcv_directo()
        
        if not usd_str or not eur_str:
            bot.reply_to(message, "❌ No se pudo conectar con el BCV para realizar el cálculo. Intenta nuevamente en un momento.")
            return

        try:
            tasa_usd = float(usd_str)
            tasa_eur = float(eur_str)
            monto = float(match.group(1).replace(',', '.'))

            # 1. Cálculo de IGTF (Función VIP)
            if 'igtf' in texto:
                if 'eur' in texto:
                    monto_bs = monto * tasa_eur
                    monto_igtf_bs = monto_bs * 0.03
                    monto_igtf_eur = monto * 0.03
                    total_bs = monto_bs + monto_igtf_bs
                    respuesta = (
                        "🏦 Cálculo IGTF (3%) - EUR\n\n"
                        f"🔹 Monto Base: {monto:,.2f} EUR ({monto_bs:,.2f} Bs.)\n"
                        f"🔹 IGTF (3%): {monto_igtf_eur:,.2f} EUR ({monto_igtf_bs:,.2f} Bs.)\n"
                        f"🔹 TOTAL A PAGAR: {monto + monto_igtf_eur:,.2f} EUR ({total_bs:,.2f} Bs.)\n\n"
                        f"📊 Tasa Euro BCV: {tasa_eur} Bs."
                    )
                else:
                    monto_bs = monto * tasa_usd if 'bs' not in texto else monto
                    monto_usd = monto if 'bs' not in texto else monto / tasa_usd
                    monto_igtf_bs = monto_bs * 0.03
                    monto_igtf_usd = monto_usd * 0.03
                    total_bs = monto_bs + monto_igtf_bs
                    total_usd = monto_usd + monto_igtf_usd
                    respuesta = (
                        "🏦 Cálculo IGTF (3%) - USD\n\n"
                        f"🔹 Monto Base: {monto_usd:,.2f} USD ({monto_bs:,.2f} Bs.)\n"
                        f"🔹 IGTF (3%): {monto_igtf_usd:,.2f} USD ({monto_igtf_bs:,.2f} Bs.)\n"
                        f"🔹 TOTAL A PAGAR: {total_usd:,.2f} USD ({total_bs:,.2f} Bs.)\n\n"
                        f"📊 Tasa Dólar BCV: {tasa_usd} Bs."
                    )

            # 2. Cálculo de IVA (Función VIP)
            elif 'iva' in texto:
                iva_monto = monto * 0.16
                total_con_iva = monto + iva_monto
                
                if 'eur' in texto:
                    total_bs = total_con_iva * tasa_eur
                    respuesta = (
                        "🧾 Cálculo IVA (16%) - EUR\n\n"
                        f"🔹 Subtotal: {monto:,.2f} EUR\n"
                        f"🔹 IVA (16%): {iva_monto:,.2f} EUR\n"
                        f"🔹 TOTAL CON IVA: {total_con_iva:,.2f} EUR ({total_bs:,.2f} Bs.)\n\n"
                        f"📊 Tasa Euro BCV: {tasa_eur} Bs."
                    )
                elif 'bs' in texto or 'bolivar' in texto or 'bolivares' in texto:
                    total_usd = total_con_iva / tasa_usd
                    respuesta = (
                        "🧾 Cálculo IVA (16%) - Bs.\n\n"
                        f"🔹 Subtotal: {monto:,.2f} Bs.\n"
                        f"🔹 IVA (16%): {iva_monto:,.2f} Bs.\n"
                        f"🔹 TOTAL CON IVA: {total_con_iva:,.2f} Bs. ({total_usd:,.2f} USD)\n\n"
                        f"📊 Tasa Dólar BCV: {tasa_usd} Bs."
                    )
                else:
                    total_bs = total_con_iva * tasa_usd
                    respuesta = (
                        "🧾 Cálculo IVA (16%) - USD\n\n"
                        f"🔹 Subtotal: {monto:,.2f} USD\n"
                        f"🔹 IVA (16%): {iva_monto:,.2f} USD\n"
                        f"🔹 TOTAL CON IVA: {total_con_iva:,.2f} USD ({total_bs:,.2f} Bs.)\n\n"
                        f"📊 Tasa Dólar BCV: {tasa_usd} Bs."
                    )

            # 3. Conversiones Normales (Disponibles para todos los usuarios)
            elif 'eur' in texto or 'euro' in texto or 'euros' in texto:
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
            print(f"Error en cálculo: {e}")
            bot.reply_to(message, "❌ Ocurrió un error al procesar el monto. Asegúrate de ingresar un número válido.")
    else:
        usd_str, eur_str = obtener_tasas_bcv_directo()
        if usd_str and eur_str:
            msg = (
                "🏛️ Tasas Oficiales BCV\n\n"
                f"💵 USD: {usd_str} Bs.\n"
                f"💶 EUR: {eur_str} Bs.\n\n"
                "💡 Para convertir montos escribe por ejemplo: '50 usd', '20 euro' o '100 bs'."
            )
        else:
            msg = "❌ No se pudo conectar con la página del BCV en este momento."
        bot.reply_to(message, msg)

if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    threading.Thread(target=run_flask, daemon=True).start()

    hilo_scheduler = threading.Thread(target=bucle_scheduler, daemon=True)
    hilo_scheduler.start()
    print("🚀 Scheduler iniciado en segundo plano.")

    print("🤖 Bot iniciado y escuchando mensajes...")
    bot.infinity_polling(skip_pending=True)