import streamlit as st
import pandas as pd
import requests
import re
import time
import io
import json
from datetime import datetime

# ==============================================================================
# 🔐 БЛОК АВТОРИЗАЦИИ
# ==============================================================================
def check_password():
    if "APP_PASSWORD" not in st.secrets:
        return True
    
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
        
    if not st.session_state["password_correct"]:
        st.text_input(
            "🔑 Введите пароль доступа", 
            type="password", 
            on_change=password_entered, 
            key="password_input"
        )
        return False
    return True

def password_entered():
    if st.session_state["password_input"] == st.secrets["APP_PASSWORD"]:
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]
    else:
        st.session_state["password_correct"] = False
        st.error("⛔ Неверный пароль")

# ==============================================================================
# ⚙️ НАСТРОЙКИ СТРАНИЦЫ И API
# ==============================================================================
st.set_page_config(page_title="Qlean Orchestrator v2", page_icon="📢", layout="wide")

if not check_password():
    st.stop()

try:
    HDE_API_KEY = st.secrets["HDE_API_KEY"]
    HDE_EMAIL = st.secrets["HDE_EMAIL"]
    WA_TOKEN = st.secrets["WA_TOKEN"]
    WA_INSTANCE_ID = st.secrets["WA_INSTANCE_ID"]
    YANDEX_CASCADE_URL = st.secrets["YANDEX_CASCADE_URL"]
    YANDEX_SINGLE_URL = st.secrets["YANDEX_SINGLE_URL"]
except Exception as e:
    st.error(f"⚠️ Ошибка в secrets.toml: {e}")
    st.stop()

HDE_URL = "https://qlean.helpdeskeddy.com/api/v2"
WA_API_URL = f"https://api.1msg.io/{WA_INSTANCE_ID}/sendTemplate?token={WA_TOKEN}"
WA_NAMESPACE = "49276b64_15e7_414d_8f35_6ab04bcaa5b1"

### URL для Клининга (Chat2Desk) ###
CHAT2DESK_URL = "https://ror.chat2desk.com/webhooks/smart_script/6ECJJp6"

# ==============================================================================
# 🎛️ БОКОВАЯ ПАНЕЛЬ
# ==============================================================================
with st.sidebar:
    st.header("🎯 Направление рассылки")
    
    ### Главный переключатель логики ###
    business_unit = st.radio(
        "Выберите отдел:",
        ["Химчистка (Yandex/HDE)", "Клининг (Chat2Desk)"]
    )
    
    st.markdown("---")
    st.header("⚙️ Настройки")

    # ---------------------------------------------------------
    # ЛОГИКА ДЛЯ ХИМЧИСТКИ
    # ---------------------------------------------------------
    if business_unit == "Химчистка (Yandex/HDE)":
        send_strategy = st.selectbox(
            "Стратегия отправки:",
            ["Каскад (Автоматический выбор)", "Конкретный мессенджер", "WhatsApp (Direct Template)"]
        )
        
        ticket_subject_suffix = st.text_input("Тема рассылки:", value="Забытые вещи")
        full_type_value = f"Рассылка: {ticket_subject_suffix}"
        msg_text = st.text_area("Текст сообщения:", value="Ваш заказ готов...", height=150)
        tags_input = st.text_input("Теги (через запятую):", value="рассылка")
        tags_list = [tag.strip() for tag in tags_input.split(",") if tag.strip()]

        if send_strategy == "Каскад (Автоматический выбор)":
            st.subheader("Настройка каскада")
            cascade_order = st.multiselect(
                "Порядок каналов:",
                options=["max", "tlgrm", "chat"],
                default=["chat", "tlgrm", "max"]
            )
        elif send_strategy == "Конкретный мессенджер":
            st.subheader("Выбор канала")
            target_source = st.selectbox(
                "Источник:",
                options=["chat", "tlgrm", "max"],
                format_func=lambda x: {"chat": "In-App Chat", "tlgrm": "Telegram", "max": "MAX"}[x]
            )
        elif send_strategy == "WhatsApp (Direct Template)":
            st.subheader("Настройки WA")
            wa_template = st.text_input("Имя шаблона (Template Name):", value="poteri")

    # ---------------------------------------------------------
    # ЛОГИКА ДЛЯ КЛИНИНГА
    # ---------------------------------------------------------
    else:
        cleaning_audience = st.radio("Аудитория:", ["Клиент", "Клинер"])
        
        # Выбор транспорта
        c2d_transport = st.selectbox(
            "Транспорт:", 
            ["telegram", "wa_gupshup"],
            format_func=lambda x: "Telegram" if x == "telegram" else "WhatsApp (wa_gupshup)"
        ) 
        
        # Динамическая смена поля ввода в зависимости от транспорта
        if c2d_transport == "wa_gupshup":
            st.info("💡 Учтите, для WA всегда используется канал 106265 независимо от аудитории.")
            msg_text = st.text_area(
                "HSM Шаблон (взять у Льва Оганезова):", 
                value="@HSM@\nclaims_13|ru", 
                height=150
            )
        else:
            msg_text = st.text_area("Текст сообщения:", value="Уведомление по клинингу...", height=150)


# ==============================================================================
# 🛠 ФУНКЦИИ ОТПРАВКИ
# ==============================================================================

def normalize_phone(phone):
    d = re.sub(r'\D', '', str(phone))
    if len(d) == 10: return "7" + d
    if len(d) == 11 and d.startswith('8'): return "7" + d[1:]
    return d

def send_cascade(phone, message, type_value, tags, order):
    payload = {
        "phone": normalize_phone(phone),
        "message": message,
        "type_value": type_value,
        "tags": tags,
        "target_sources": order,
        "deal_id": ""
    }
    try:
        r = requests.post(YANDEX_CASCADE_URL, json=payload, timeout=10)
        return r.status_code == 200, r.text
    except Exception as e:
        return False, str(e)

def send_single_source(phone, message, type_value, tags, source):
    payload = {
        "phone": normalize_phone(phone),
        "message": message,
        "type_value": type_value,
        "tags": tags,
        "target_source": source
    }
    try:
        r = requests.post(YANDEX_SINGLE_URL, json=payload, timeout=10)
        return r.status_code == 200, r.text
    except Exception as e:
        return False, str(e)

def send_wa_direct(phone, template):
    payload = {
        "template": template,
        "language": {"policy": "deterministic", "code": "ru"},
        "namespace": WA_NAMESPACE,
        "phone": normalize_phone(phone)
    }
    try:
        r = requests.post(WA_API_URL, json=payload, timeout=10)
        if r.status_code == 200:
            resp = r.json()
            if resp.get('sent'): return True, "WA Sent"
        return False, r.text
    except Exception as e:
        return False, str(e)

def send_chat2desk(phone, message, audience, transport):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json"
    }
    
    # Распределение ID в зависимости от аудитории
    if audience == "Клиент":
        tag_id = "434556"
        channel_id = "106265"
    else: # Клинер
        tag_id = "411631"
        channel_id = "123634"
        
    # НОВОЕ: Переопределение channel_id, если это WhatsApp
    if transport == "wa_gupshup":
        channel_id = "106265"
        
    payload = {
        "mobilePhone": normalize_phone(phone),
        "transport": transport,
        "tag_id": tag_id,
        "channel_id": channel_id,
        "text": message,
        "hookType": "MbMessengersSend",
        "params": {
            "type": "autoreply"
        }
    }
    
    try:
        r = requests.post(CHAT2DESK_URL, json=payload, headers=headers, timeout=10)
        # Chat2Desk обычно возвращает 200 при успешном принятии вебхука
        return r.status_code == 200, r.text
    except Exception as e:
        return False, str(e)

# ==============================================================================
# 🖥️ ИНТЕРФЕЙС И ЛОГИКА
# ==============================================================================
st.title("📢 Оркестратор рассылок Qlean")

uploaded_file = st.file_uploader("Загрузите Excel-файл с номерами телефонов", type=["xlsx"])

if uploaded_file:
    try:
        df_input = pd.read_excel(uploaded_file, header=None)
        phones = df_input.iloc[:, 0].dropna().astype(str).tolist()
        phones = [p for p in phones if re.search(r'\d', p)]
        
        st.success(f"📦 Загружено номеров: {len(phones)} | Направление: **{business_unit}**")
        
        if st.button("🚀 ЗАПУСТИТЬ РАССЫЛКУ"):
            progress_bar = st.progress(0)
            results = []
            
            for i, phone in enumerate(phones):
                progress = (i + 1) / len(phones)
                progress_bar.progress(progress)
                
                status_ok, info = False, ""
                
                # --- ЛОГИКА МАРШРУТИЗАЦИИ ЗАПРОСОВ ---
                if business_unit == "Химчистка (Yandex/HDE)":
                    if send_strategy == "Каскад (Автоматический выбор)":
                        status_ok, info = send_cascade(phone, msg_text, full_type_value, tags_list, cascade_order)
                    elif send_strategy == "Конкретный мессенджер":
                        status_ok, info = send_single_source(phone, msg_text, full_type_value, tags_list, target_source)
                    elif send_strategy == "WhatsApp (Direct Template)":
                        status_ok, info = send_wa_direct(phone, wa_template)
                
                else:
                    # Логика для Клининга (Chat2Desk)
                    status_ok, info = send_chat2desk(phone, msg_text, cleaning_audience, c2d_transport)

                # --- ЛОГИКА ОПРЕДЕЛЕНИЯ ДОСТАВКИ ---
                is_delivered = "Нет"
                error_reason = "-"

                if status_ok:
                    if business_unit == "Клининг (Chat2Desk)":
                        # Chat2Desk: 200 OK обычно значит, что вебхук принят успешно
                        is_delivered = "Да"
                    else:
                        # Химчистка: Парсим ответ Яндекса
                        try:
                            parsed_info = json.loads(info)
                            if parsed_info.get("status") == "success":
                                is_delivered = "Да"
                            else:
                                is_delivered = "Нет"
                                error_reason = parsed_info.get("detail", "Неизвестная причина")
                        except:
                            if "WA Sent" in str(info):
                                is_delivered = "Да"
                            else:
                                error_reason = "Неизвестный ответ сервера"
                else:
                    error_reason = str(info)

                results.append({
                    "Телефон": phone,
                    "Статус API": "✅ 200 OK" if status_ok else "❌ ОШИБКА",
                    "Доставлено": is_delivered,
                    "Причина (если нет)": error_reason,
                    "Детали (Сырой лог)": info
                })
                
                time.sleep(0.2) # Небольшая пауза

            # Результаты и Аналитика
            st.divider()
            df_res = pd.DataFrame(results)
            
            st.subheader("📊 Аналитика рассылки")
            
            total_count = len(df_res)
            delivered_count = len(df_res[df_res["Доставлено"] == "Да"])
            not_delivered_count = total_count - delivered_count
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Всего номеров обработано", total_count)
            success_percent = (delivered_count / total_count * 100) if total_count > 0 else 0
            col2.metric("✅ Доставлено", delivered_count, f"{success_percent:.1f}%")
            fail_percent = (not_delivered_count / total_count * 100) if total_count > 0 else 0
            col3.metric("❌ Не доставлено", not_delivered_count, f"-{fail_percent:.1f}%")

            st.write("") 
            
            col_chart, col_errors = st.columns([1, 1])
            
            with col_chart:
                st.markdown("**Распределение статусов доставки**")
                st.bar_chart(df_res["Доставлено"].value_counts())
                
            with col_errors:
                st.markdown("**Топ причин недоставки**")
                errors_df = df_res[df_res["Причина (если нет)"] != "-"]
                if not errors_df.empty:
                    error_stats = errors_df["Причина (если нет)"].value_counts().reset_index()
                    error_stats.columns = ["Причина", "Количество"]
                    st.dataframe(error_stats, use_container_width=True)
                else:
                    st.success("Ошибок не обнаружено!")
            
            st.markdown("---")
            st.markdown("**Детальный отчет по каждому номеру:**")

            st.dataframe(df_res, use_container_width=True)
            
            # Скачивание отчета
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_res.to_excel(writer, index=False, sheet_name='Report')
            
            st.download_button(
                label="📥 Скачать отчет .xlsx",
                data=buffer.getvalue(),
                file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.ms-excel"
            )

    except Exception as e:
        st.error(f"Критическая ошибка: {e}")