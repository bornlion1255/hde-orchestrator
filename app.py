import streamlit as st
import pandas as pd
import requests
import re
import time
import io
from datetime import datetime

# ==============================================================================
# 🔐 БЛОК АВТОРИЗАЦИИ (ЗАЩИТА ПАРОЛЕМ)
# ==============================================================================
def check_password():
    """Возвращает True, если пользователь ввел правильный пароль."""
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
# ⚙️ НАСТРОЙКИ СТРАНИЦЫ
# ==============================================================================
st.set_page_config(page_title="HDE Orchestrator", page_icon="📢", layout="wide")

if not check_password():
    st.stop()

# ==============================================================================
# 🔐 БЛОК КОНФИГУРАЦИИ API
# ==============================================================================
try:
    HDE_API_KEY = st.secrets["HDE_API_KEY"]
    HDE_EMAIL = st.secrets["HDE_EMAIL"]
    WA_TOKEN = st.secrets["WA_TOKEN"]
    WA_INSTANCE_ID = st.secrets["WA_INSTANCE_ID"]
except:
    st.error("⚠️ API ключи не найдены! Настрой secrets.toml в настройках Streamlit.")
    st.stop()

HDE_URL = "https://qlean.helpdeskeddy.com/api/v2"
WA_API_URL = f"https://api.1msg.io/{WA_INSTANCE_ID}/sendTemplate?token={WA_TOKEN}"
hde_auth = (HDE_EMAIL, HDE_API_KEY)

# HDE Fields (ID полей)
HDE_FIELD_TYPE_ID = 33                  
HDE_FIELD_INITIATED_ID = 43 

# WA Константы
WA_NAMESPACE = "49276b64_15e7_414d_8f35_6ab04bcaa5b1"
WA_LANG_CODE = "ru"

# ==============================================================================
# 🎛️ БОКОВАЯ ПАНЕЛЬ НАСТРОЕК
# ==============================================================================
with st.sidebar:
    st.header("⚙️ Настройки рассылки")
    
    # 1. Выбор режима
    send_mode = st.radio(
        "Режим отправки:",
        ("Авто (ТГ, если нет -> WA)", "Только Telegram", "Только WhatsApp")
    )
    
    st.markdown("---")
    
    # 2. Настройки Telegram / HDE
    st.subheader("🔵 Telegram / HDE")
    
    # --- НОВОЕ: ТЕМА РАССЫЛКИ ---
    ticket_subject_suffix = st.text_input(
        "Тема рассылки (после 'Рассылка: '):",
        value="Забытые вещи"
    )
    # Автоматически склеиваем префикс и то, что ввел пользователь
    full_ticket_type_value = f"Рассылка: {ticket_subject_suffix}"
    st.caption(f"📝 В поле 'Тип обращения' запишется: **{full_ticket_type_value}**")

    tg_text_input = st.text_area(
        "Текст сообщения:", 
        value="Заказ ждёт в пункте выдачи. При длительном хранении невостребованные вещи могут быть утилизированы.",
        height=100
    )
    
    tg_tags_input = st.text_input(
        "Теги (через запятую):",
        value="рассылка"
    )
    tg_tags_list = [tag.strip() for tag in tg_tags_input.split(",") if tag.strip()]

    st.markdown("---")

    # 3. Настройки WhatsApp
    st.subheader("🟢 WhatsApp")
    wa_template_input = st.text_input(
        "Имя шаблона (Template Name):",
        value="poteri"
    )

# ==============================================================================
# 🛠 ФУНКЦИИ
# ==============================================================================

def normalize_phone_wa(phone):
    d = re.sub(r'\D', '', str(phone))
    if len(d) == 10: return "7" + d
    if len(d) == 11 and d.startswith('8'): return "7" + d[1:]
    return d

def get_clean_core(phone):
    d = re.sub(r'\D', '', str(phone))
    if len(d) == 11 and d[0] in ['7', '8']: return d[1:]
    if len(d) == 10: return d
    return d

def get_all_candidate_users(raw_phone):
    core = get_clean_core(raw_phone)
    found_users_map = {}
    if len(core) != 10:
        variants = [str(raw_phone)]
    else:
        variants = [f"7{core}", f"8{core}", f"+7{core}"]
    
    for v in variants:
        try:
            r = requests.get(f"{HDE_URL}/users/", params={"search": v}, auth=hde_auth)
            if r.status_code == 200:
                data = r.json().get('data', [])
                for u in data:
                    found_users_map[u['id']] = u
        except Exception: pass
        time.sleep(0.1) 
    
    return list(found_users_map.values())

def find_telegram_ticket_for_user(user_id):
    try:
        params = {"user_list": user_id, "order_by": "date_updated", "order_asc": "desc"}
        r = requests.get(f"{HDE_URL}/tickets/", params=params, auth=hde_auth)
        if r.status_code == 200:
            tickets = r.json().get('data', {})
            tickets = list(tickets.values()) if isinstance(tickets, dict) else tickets
            for t in tickets:
                src = t.get('source', '').lower()
                if 'tlgrm' in src or 'telegram' in src:
                    return t['id']
    except: pass
    return None

def send_hde_telegram_message(ticket_id, message_text):
    try:
        r = requests.post(f"{HDE_URL}/tickets/{ticket_id}/posts/", json={"text": message_text}, auth=hde_auth)
        return r.status_code in [200, 201], r.text
    except Exception as e: return False, str(e)

def update_hde_ticket_properties(ticket_id, tags_list, type_value):
    payload = {
        "tags": tags_list, 
        "custom_fields": {
            str(HDE_FIELD_TYPE_ID): type_value,  # Подставляем собранное значение
            str(HDE_FIELD_INITIATED_ID): 1                
        }
    }
    try:
        requests.put(f"{HDE_URL}/tickets/{ticket_id}/", json=payload, auth=hde_auth)
    except: pass

def send_whatsapp_direct(phone, template_name):
    payload = {
        "template": template_name,
        "language": { "policy": "deterministic", "code": WA_LANG_CODE },
        "namespace": WA_NAMESPACE,
        "phone": normalize_phone_wa(phone)
    }
    try:
        r = requests.post(WA_API_URL, json=payload)
        if r.status_code == 200:
            resp = r.json()
            if resp.get('sent') == True:
                return True, f"WA ID: {resp.get('id')}"
            return False, f"Not Sent: {r.text}"
        return False, f"Err {r.status_code}"
    except Exception as e: return False, str(e)

# ==============================================================================
# 🖥️ ОСНОВНОЙ ИНТЕРФЕЙС
# ==============================================================================

st.title("📢 Оркестратор рассылок")
st.markdown("Настрой параметры слева, загрузи файл и запусти.")

uploaded_file = st.file_uploader("Выберите файл .xlsx", type=["xlsx"])

if uploaded_file:
    try:
        df_input = pd.read_excel(uploaded_file, header=None)
        phones = df_input.iloc[:, 0].dropna().astype(str).tolist()
        phones = [p for p in phones if re.search(r'\d', p)]
        
        st.info(f"Найдено номеров: {len(phones)}")
        
        with st.expander("Проверьте параметры перед запуском"):
            st.write(f"**Режим:** {send_mode}")
            st.write(f"**Тип обращения:** {full_ticket_type_value}")
            st.write(f"**Текст ТГ:** {tg_text_input}")
            st.write(f"**Теги:** {tg_tags_list}")
            st.write(f"**Шаблон WA:** {wa_template_input}")

        if st.button("🚀 ЗАПУСТИТЬ РАССЫЛКУ"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            
            log_container = st.container()
            log_container.write("--- Лог выполнения ---")

            for i, phone in enumerate(phones):
                progress = (i + 1) / len(phones)
                progress_bar.progress(progress)
                status_text.text(f"Обработка: {phone} ({i+1}/{len(phones)})")
                
                res_uid, res_tg, res_wa, res_stat, res_info = "-", "-", "-", "ОШИБКА", ""
                
                candidates = get_all_candidate_users(phone)
                
                should_try_tg = send_mode in ["Авто (ТГ, если нет -> WA)", "Только Telegram"]
                should_try_wa = send_mode == "Только WhatsApp"
                
                tg_sent = False
                
                # --- ЛОГИКА TELEGRAM ---
                if should_try_tg:
                    target_ticket = None
                    if candidates:
                        for user in candidates:
                            tid = find_telegram_ticket_for_user(user['id'])
                            if tid:
                                target_ticket = tid
                                res_uid = str(user['id'])
                                break
                    
                    if target_ticket:
                        ok, txt = send_hde_telegram_message(target_ticket, tg_text_input)
                        if ok:
                            res_tg = "Отправлено"
                            res_stat = "УСПЕХ"
                            res_info = f"Ticket #{target_ticket}"
                            tg_sent = True
                            # Обновляем тип обращения и теги
                            update_hde_ticket_properties(target_ticket, tg_tags_list, full_ticket_type_value)
                        else:
                            res_tg = "Сбой"
                            res_info = txt
                    elif candidates:
                        res_tg = "Нет диалога"
                        res_uid = str([u['id'] for u in candidates])
                    else:
                        res_uid = "Не найден"

                # --- ЛОГИКА WHATSAPP ---
                if send_mode == "Авто (ТГ, если нет -> WA)" and not tg_sent:
                    should_try_wa = True
                
                if should_try_wa:
                    ok, txt = send_whatsapp_direct(phone, wa_template_input)
                    if ok:
                        res_wa = "Отправлено"
                        res_stat = "УСПЕХ"
                        res_info += f" | {txt}"
                    else:
                        res_wa = "Сбой"
                        res_info += f" | WA Err: {txt}"

                if send_mode == "Только Telegram" and not tg_sent and res_tg == "Сбой":
                     res_stat = "ОШИБКА"
                
                results.append([phone, res_uid, res_tg, res_wa, res_stat, res_info])
                time.sleep(0.5)

            st.success("✅ Рассылка завершена!")
            
            df_res = pd.DataFrame(results, columns=["Телефон", "HDE ID", "Telegram", "WhatsApp", "Статус", "Инфо"])
            st.dataframe(df_res)
            
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
        st.error(f"Ошибка: {e}")

    except Exception as e:
        st.error(f"Ошибка: {e}")
