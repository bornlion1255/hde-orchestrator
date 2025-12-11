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
        return True  # Если пароль не задан в секретах, пускаем всех (или можно st.stop())

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
    """Проверка введенного пароля."""
    if st.session_state["password_input"] == st.secrets["APP_PASSWORD"]:
        st.session_state["password_correct"] = True
        del st.session_state["password_input"]  # Удаляем пароль из памяти
    else:
        st.session_state["password_correct"] = False
        st.error("⛔ Неверный пароль")

if not check_password():
    st.stop()  # 🛑 ОСТАНОВИТЬ выполнение, если пароль не введен

# ==============================================================================
# 🔐 БЛОК КОНФИГУРАЦИИ (Берем из st.secrets для безопасности)
# ==============================================================================
# Для локального запуска создай папку .streamlit и файл secrets.toml в ней
# Либо пока тестируешь, можешь временно вписать сюда, но не публикуй!

try:
    HDE_API_KEY = st.secrets["HDE_API_KEY"]
    HDE_EMAIL = st.secrets["HDE_EMAIL"]
    WA_TOKEN = st.secrets["WA_TOKEN"]
    WA_INSTANCE_ID = st.secrets["WA_INSTANCE_ID"]
except:
    # Заглушки, если секреты не настроены
    st.error("⚠️ API ключи не найдены! Настрой secrets.toml")
    st.stop()

HDE_URL = "https://qlean.helpdeskeddy.com/api/v2"
WA_API_URL = f"https://api.1msg.io/{WA_INSTANCE_ID}/sendTemplate?token={WA_TOKEN}"
hde_auth = (HDE_EMAIL, HDE_API_KEY)

# ==============================================================================
# ⚙️ НАСТРОЙКИ СООБЩЕНИЙ
# ==============================================================================
TG_MESSAGE_TEXT = """Заказ ждёт в пункте выдачи. При длительном хранении невостребованные вещи могут быть утилизированы."""
WA_TEMPLATE_NAME = "poteri"
WA_NAMESPACE = "49276b64_15e7_414d_8f35_6ab04bcaa5b1"
WA_LANG_CODE = "ru"

# HDE Fields
HDE_FIELD_TYPE_ID = 33                  
HDE_FIELD_TYPE_VALUE = "Рассылка: Забытые вещи" 
HDE_FIELD_INITIATED_ID = 43 
HDE_TAGS_LIST = ["рассылка"]

# ==============================================================================
# 🛠 ФУНКЦИИ (Твоя логика)
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

def get_all_candidate_users(raw_phone, log_container):
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
        time.sleep(0.1) # Чуть быстрее для веба
    
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

def send_hde_telegram_message(ticket_id):
    try:
        r = requests.post(f"{HDE_URL}/tickets/{ticket_id}/posts/", json={"text": TG_MESSAGE_TEXT}, auth=hde_auth)
        return r.status_code in [200, 201], r.text
    except Exception as e: return False, str(e)

def update_hde_ticket_properties(ticket_id):
    payload = {
        "tags": HDE_TAGS_LIST, 
        "custom_fields": {
            str(HDE_FIELD_TYPE_ID): HDE_FIELD_TYPE_VALUE, 
            str(HDE_FIELD_INITIATED_ID): 1                
        }
    }
    try:
        requests.put(f"{HDE_URL}/tickets/{ticket_id}/", json=payload, auth=hde_auth)
    except: pass

def send_whatsapp_direct(phone):
    payload = {
        "template": WA_TEMPLATE_NAME,
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
# 🖥️ ИНТЕРФЕЙС STREAMLIT
# ==============================================================================

st.set_page_config(page_title="HDE Orchestrator", page_icon="📢")

st.title("📢 Оркестратор рассылок")
st.markdown("Загрузи Excel файл с номерами (колонка А), скрипт проверит HDE на наличие Telegram, иначе отправит в WhatsApp.")

uploaded_file = st.file_uploader("Выберите файл .xlsx", type=["xlsx"])

if uploaded_file:
    # Чтение файла
    try:
        df_input = pd.read_excel(uploaded_file, header=None)
        phones = df_input.iloc[:, 0].dropna().astype(str).tolist()
        # Чистка от заголовков
        phones = [p for p in phones if re.search(r'\d', p)]
        
        st.info(f"Найдено номеров: {len(phones)}")
        
        if st.button("🚀 ЗАПУСТИТЬ РАССЫЛКУ"):
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []
            
            # Контейнер для логов
            log_container = st.container()
            log_container.write("--- Лог выполнения ---")

            for i, phone in enumerate(phones):
                # Обновление UI
                progress = (i + 1) / len(phones)
                progress_bar.progress(progress)
                status_text.text(f"Обработка: {phone} ({i+1}/{len(phones)})")
                
                # Логика
                res_uid, res_tg, res_wa, res_stat, res_info = "-", "-", "-", "ОШИБКА", ""
                
                candidates = get_all_candidate_users(phone, log_container)
                tg_sent = False
                
                # Поиск ТГ
                target_ticket = None
                if candidates:
                    for user in candidates:
                        tid = find_telegram_ticket_for_user(user['id'])
                        if tid:
                            target_ticket = tid
                            res_uid = str(user['id'])
                            break
                
                # Отправка ТГ
                if target_ticket:
                    ok, txt = send_hde_telegram_message(target_ticket)
                    if ok:
                        res_tg = "Отправлено"
                        res_stat = "УСПЕХ"
                        res_info = f"Ticket #{target_ticket}"
                        tg_sent = True
                        update_hde_ticket_properties(target_ticket)
                        # log_container.success(f"{phone}: ✅ Telegram")
                    else:
                        res_tg = "Сбой"
                        res_info = txt
                elif candidates:
                     res_tg = "Нет диалога"
                else:
                     res_uid = "Не найден"

                # Отправка WA
                if not tg_sent:
                    ok, txt = send_whatsapp_direct(phone)
                    if ok:
                        res_wa = "Отправлено"
                        res_stat = "УСПЕХ"
                        res_info += f" | {txt}"
                        # log_container.warning(f"{phone}: ✅ WhatsApp")
                    else:
                        res_wa = "Сбой"
                        res_info += f" | WA Err: {txt}"
                        # log_container.error(f"{phone}: ❌ Fail")

                results.append([phone, res_uid, res_tg, res_wa, res_stat, res_info])
                time.sleep(0.5) # Пауза, чтобы API не забанил

            st.success("✅ Рассылка завершена!")
            
            # Создание отчета для скачивания
            df_res = pd.DataFrame(results, columns=["Телефон", "HDE ID", "Telegram", "WhatsApp", "Статус", "Инфо"])
            st.dataframe(df_res)
            
            # Конвертация в Excel в памяти
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_res.to_excel(writer, index=False, sheet_name='Report')
                # Здесь можно добавить раскраску ячеек, как у тебя было, через writer.sheets['Report']
            
            st.download_button(
                label="📥 Скачать отчет .xlsx",
                data=buffer.getvalue(),
                file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.ms-excel"
            )

    except Exception as e:
        st.error(f"Ошибка при чтении файла: {e}")
