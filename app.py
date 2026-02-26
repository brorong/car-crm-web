import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
import json

# ================= 網頁基本設定 =================
st.set_page_config(page_title="CRM管理後台", page_icon="📋", layout="wide")

# ================= 資安防護：隱藏下載 CSV 按鈕 =================
st.markdown(
    """
    <style>
    /* 隱藏表格右上角的工具列 (防止使用者一鍵下載 CSV) */
    [data-testid="stElementToolbar"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ================= 1. 登入狀態初始化 =================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# ================= 2. 登入頁面 UI (安全升級版) =================
def login_page():
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.write("")
        st.write("")
        st.write("")
        st.markdown("<h2 style='text-align: center;'>🔐 系統登入</h2>", unsafe_allow_html=True)
        
        # 從 Secrets 讀取正確密碼，並加入防呆機制
        try:
            correct_password = st.secrets["ADMIN_PASSWORD"]
        except KeyError:
            st.error("❌ 系統尚未設定管理員密碼，請至後台 Secrets 設定 ADMIN_PASSWORD。")
            st.stop()
        
        with st.form("login_form"):
            username = st.text_input("帳號", placeholder="請輸入帳號 (admin)")
            password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
            submit = st.form_submit_button("登入", use_container_width=True)
            
            if submit:
                # 將輸入的密碼與 Secrets 裡的密碼進行比對
                if username == 'admin' and password == correct_password:
                    st.session_state['logged_in'] = True
                    st.success("登入成功！正在載入系統...")
                    st.rerun()
                else:
                    st.error("❌ 帳號或密碼錯誤，請重新輸入。")

# ================= 3. 主系統程式 =================
def main_app():
    with st.sidebar:
        st.success("👤 管理員 (admin) 已登入")
        if st.button("🚪 登出系統", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

    st.title("📋 CRM管理後台")
    st.markdown("自動比對未來 **60天內** 即將到期的項目。勾選並填寫回訪內容後，點擊儲存即可回寫至雲端。")

    # ================= 讀取機密變數 =================
    try:
        SHEET_CSV_URL = st.secrets["SHEET_CSV_URL"]
        CONTACT_SHEET_URL = st.secrets["CONTACT_SHEET_URL"]
        GCP_CREDS_JSON = st.secrets["GCP_CREDENTIALS"]
    except KeyError:
        st.error("❌ 找不到環境變數，請確認 .streamlit/secrets.toml 設定。")
        st.stop()

    # ================= 連線 Google Sheets =================
    @st.cache_resource
    def init_gspread():
        creds_dict = json.loads(GCP_CREDS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open_by_url(CONTACT_SHEET_URL)
        return sh.sheet1 

    worksheet_log = init_gspread()

    # ================= 資料載入與防呆處理 =================
    @st.cache_data(ttl=60) 
    def load_and_process_data():
        df_main = pd.read_csv(SHEET_CSV_URL)
        log_data = worksheet_log.get_all_records()
        
        if not log_data:
            df_log = pd.DataFrame(columns=['車牌', '聯絡日期', '聯絡項目', '回訪內容'])
        else:
            df_log = pd.DataFrame(log_data)
        
        for col in ['車牌', '聯絡日期', '聯絡項目', '回訪內容']:
            if col not in df_log.columns:
                df_log[col] = ''
        
        df_main['車牌'] = df_main['車牌'].astype(str).str.strip()
        df_log['車牌'] = df_log['車牌'].astype(str).str.strip()

        return df_main, df_log

    with st.spinner('正在同步 Google 試算表資料...'):
        df_main, df_log = load_and_process_data()

    today_date = datetime.now().date()
    target_date = today_date + timedelta(days=60)
    today_str = today_date.strftime('%Y/%m/%d')

    # ================= 核心篩選邏輯 =================
    def get_expiring_data(df, df_log, date_col_name, item_name):
        if date_col_name not in df.columns:
            return pd.DataFrame()

        df_copy = df.copy()
        df_copy[date_col_name] = pd.to_datetime(df_copy[date_col_name], errors='coerce')
        
        date
