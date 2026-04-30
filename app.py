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
def check_password()
    if APP_PASSWORD not in st.secrets
        return True
    if password_correct not in st.session_state
        st.session_state[password_correct] = False
    if not st.session_state[password_correct]
        st.text_input(
            "🔑 Введите пароль доступа", 
            type="password", 
            on_change=password_entered, 
            key="password_input"
        )

def password_entered()
    if st.session_state[password_input] == st.secrets[APP_PASSWORD]
        st.session_state[password_correct] = True
        del st.session_state[password_input]
    else
        st.session_state[password_correct] = False
        st.error(⛔ Неверный пароль)

# ==============================================================================
# ⚙️ НАСТРОЙКИ СТРАНИЦЫ И API
# ==============================================================================
st.set_page_config(page_title=Qlean Orchestrator v2, page_icon=📢, layout=wide)

if not check_password()
    st.stop()

try
    HDE_API_KEY = st.secrets[HDE_API_KEY]
    HDE_EMAIL = st.secrets[HDE_EMAIL]
    WA_TOKEN = st.secrets[WA_TOKEN]
    WA_INSTANCE_ID = st.secrets[WA_INSTANCE_ID]
    # Новые секреты для Yandex Functions
    YANDEX_CASCADE_URL = st.secrets[YANDEX_CASCADE_URL]
    YANDEX_SINGLE_URL = st.secrets[YANDEX_SINGLE_URL]
except Exception as e
    st.error(f⚠️ Ошибка в secrets.toml {e})
    st.stop()

HDE_URL = httpsqlean.helpdeskeddy.comapiv2
WA_API_URL = fhttpsapi.1msg.io{WA_INSTANCE_ID}sendTemplatetoken={WA_TOKEN}
WA_NAMESPACE = 49276b64_15e7_414d_8f35_6ab04bcaa5b1

# ==============================================================================
# 🎛️ БОКОВАЯ ПАНЕЛЬ
# ==============================================================================
with st.sidebar
    st.header(⚙️ Настройки рассылки)
    
    send_strategy = st.selectbox(
        Стратегия отправки,
        [Каскад (Автоматический выбор), Конкретный мессенджер, WhatsApp (Direct Template)]
    )

    st.markdown(---)
    
    # Поля, общие для всех режимов
    ticket_subject_suffix = st.text_input(Тема рассылки, value=Забытые вещи)
    full_type_value = fРассылка {ticket_subject_suffix}
    
    msg_text = st.text_area(Текст сообщения, value=Ваш заказ готов..., height=150)
    
    tags_input = st.text_input(Теги (через запятую), value=рассылка)
    tags_list = [tag.strip() for tag in tags_input.split(,) if tag.strip()]

    st.markdown(---)

    # Специфичные настройки для каждого режима
    if send_strategy == Каскад (Автоматический выбор)
        st.subheader(Настройка каскада)
        cascade_order = st.multiselect(
            Порядок каналов (перетащите для сортировки),
            options=[max, tlgrm, chat],
            default=[chat, tlgrm, max],
            help=Первым будет выбран верхний канал в списке
        )
    
    elif send_strategy == Конкретный мессенджер
        st.subheader(Выбор канала)
        target_source = st.selectbox(
            Источник,
            options=[chat, tlgrm, max],
            format_func=lambda x {chat In-App Chat, tlgrm Telegram, max MAX}[x]
        )
        
    elif send_strategy == WhatsApp (Direct Template)
        st.subheader(Настройки WA)
        wa_template = st.text_input(Имя шаблона (Template Name), value=poteri)

# ==============================================================================
# 🛠 ФУНКЦИИ ОТПРАВКИ
# ==============================================================================

def normalize_phone(phone)
    d = re.sub(r'D', '', str(phone))
    if len(d) == 10 return 7 + d
    if len(d) == 11 and d.startswith('8') return 7 + d[1]
    return d

def send_cascade(phone, message, type_value, tags, order)
    payload = {
        phone normalize_phone(phone),
        message message,
        type_value type_value,
        tags tags,
        target_sources order,
        deal_id 
    }
    try
        r = requests.post(YANDEX_CASCADE_URL, json=payload, timeout=10)
        return r.status_code == 200, r.text
    except Exception as e
        return False, str(e)

def send_single_source(phone, message, type_value, tags, source)
    payload = {
        phone normalize_phone(phone),
        message message,
        type_value type_value,
        tags tags,
        target_source source
    }
    try
        r = requests.post(YANDEX_SINGLE_URL, json=payload, timeout=10)
        return r.status_code == 200, r.text
    except Exception as e
        return False, str(e)

def send_wa_direct(phone, template)
    payload = {
        template template,
        language {policy deterministic, code ru},
        namespace WA_NAMESPACE,
        phone normalize_phone(phone)
    }
    try
        r = requests.post(WA_API_URL, json=payload, timeout=10)
        if r.status_code == 200
            resp = r.json()
            if resp.get('sent') return True, WA Sent
        return False, r.text
    except Exception as e
        return False, str(e)

# ==============================================================================
# 🖥️ ИНТЕРФЕЙС И ЛОГИКА
# ==============================================================================
st.title(📢 Оркестратор рассылок Qlean)

uploaded_file = st.file_uploader(Загрузите Excel-файл с номерами телефонов, type=[xlsx])

if uploaded_file
    try
        df_input = pd.read_excel(uploaded_file, header=None)
        phones = df_input.iloc[, 0].dropna().astype(str).tolist()
        phones = [p for p in phones if re.search(r'd', p)]
        
        st.success(f📦 Загружено номеров {len(phones)})
        
        if st.button(🚀 ЗАПУСТИТЬ РАССЫЛКУ)
            progress_bar = st.progress(0)
            results = []
            
            for i, phone in enumerate(phones)
                progress = (i + 1)  len(phones)
                progress_bar.progress(progress)
                
                status_ok, info = False, 
                
                # ЛОГИКА ВЫБОРА СТРАТЕГИИ
                if send_strategy == Каскад (Автоматический выбор)
                    status_ok, info = send_cascade(phone, msg_text, full_type_value, tags_list, cascade_order)
                
                elif send_strategy == Конкретный мессенджер
                    status_ok, info = send_single_source(phone, msg_text, full_type_value, tags_list, target_source)
                
                elif send_strategy == WhatsApp (Direct Template)
                    status_ok, info = send_wa_direct(phone, wa_template)
                
                results.append({
                    Телефон phone,
                    Статус ✅ УСПЕХ if status_ok else ❌ ОШИБКА,
                    Детали info
                })
                
                time.sleep(0.2) # Небольшая пауза, чтобы не спамить API

            # Результаты
            st.divider()
            df_res = pd.DataFrame(results)
            st.dataframe(df_res, use_container_width=True)
            
            # Скачивание отчета
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer
                df_res.to_excel(writer, index=False, sheet_name='Report')
            
            st.download_button(
                label=📥 Скачать отчет .xlsx,
                data=buffer.getvalue(),
                file_name=freport_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx,
                mime=applicationvnd.ms-excel
            )

    except Exception as e
        st.error(fКритическая ошибка {e})