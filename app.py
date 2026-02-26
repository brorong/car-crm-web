import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
import json

# ================= 網頁基本設定 =================
st.set_page_config(page_title="露營易拉罐--客服系統", page_icon="📋", layout="wide")

# ================= 1. 登入狀態初始化 =================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False


# ================= 2. 登入頁面 UI =================
def login_page():
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.write("")
        st.write("")
        st.write("")
        st.markdown("<h2 style='text-align: center;'>🔐 系統登入</h2>", unsafe_allow_html=True)

        with st.form("login_form"):
            username = st.text_input("帳號", placeholder="請輸入帳號 (admin)")
            password = st.text_input("密碼", type="password", placeholder="請輸入密碼")
            submit = st.form_submit_button("登入", use_container_width=True)

            if submit:
                if username == 'admin' and password == '123qwe':
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

    st.title("📋 車隊效期管理後台")
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
            # 這裡新增了 '回訪內容' 作為防呆預設欄位
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

        date_mask = (df_copy[date_col_name].dt.date >= today_date) & (df_copy[date_col_name].dt.date <= target_date)
        contacted_mask = (df_log['聯絡項目'] == item_name)
        contacted_plates = df_log[contacted_mask]['車牌'].unique()
        not_contacted_mask = ~df_copy['車牌'].isin(contacted_plates)

        result_df = df_copy[date_mask & not_contacted_mask].copy()

        if not result_df.empty:
            result_df = result_df.sort_values(by=date_col_name)
            result_df['倒數天數'] = (result_df[date_col_name].dt.date - today_date).apply(lambda x: x.days)
            result_df[date_col_name] = result_df[date_col_name].dt.strftime('%Y-%m-%d')

            # 在資料表最前面插入「勾選已聯絡」與「回訪內容」兩個欄位
            result_df.insert(0, '勾選已聯絡', False)
            result_df.insert(1, '回訪內容', '')  # 預設為空白字串

        return result_df

    df_ins = get_expiring_data(df_main, df_log, '保險到期日', '保險')
    df_commercial = get_expiring_data(df_main, df_log, '商業險到期日', '商業險')
    df_inspect = get_expiring_data(df_main, df_log, '驗車到期日', '驗車')

    # ================= UI 介面：分頁設計 =================
    tab1, tab2, tab3 = st.tabs(["🛡️ 保險到期", "💼 商業險到期", "🔍 驗車到期"])

    def render_tab(df_show, item_name, date_col):
        if df_show.empty:
            st.success(f"🎉 近期內無即將到期的「{item_name}」，或已全數聯絡完畢！")
            return

        st.write(f"以下為未來 60 天內到期，且尚未聯絡的名單（共 {len(df_show)} 筆）：")
        st.info("💡 提示：您可以勾選最左側的方塊，並在『回訪內容』欄位輸入文字後，一併儲存。")

        display_columns = ['勾選已聯絡', '回訪內容', date_col, '倒數天數', '車牌', '客戶姓名', '電話']
        display_columns = [col for col in display_columns if col in df_show.columns]

        # 顯示可編輯的表格
        edited_df = st.data_editor(
            df_show[display_columns],
            hide_index=True,
            use_container_width=True,
            # 開放「勾選已聯絡」與「回訪內容」可以編輯，其他鎖定
            disabled=[col for col in display_columns if col not in ['勾選已聯絡', '回訪內容']]
        )

        # 抓取有被勾選的資料列
        selected_mask = edited_df['勾選已聯絡'] == True
        selected_data = edited_df[selected_mask][['車牌', '回訪內容']].to_dict('records')

        if selected_data:
            if st.button(f"💾 儲存已聯絡名單 ({len(selected_data)} 筆)", key=f"btn_{item_name}"):
                with st.spinner("正在寫入 Google 試算表..."):
                    rows_to_append = []
                    # 將每一筆勾選的資料轉換成要寫入的格式
                    for row in selected_data:
                        car = row['車牌']
                        note = str(row['回訪內容']).strip()  # 抓取使用者填寫的內容
                        # 對應試算表欄位：車牌, 聯絡日期, 聯絡項目, 回訪內容
                        rows_to_append.append([car, today_str, item_name, note])

                    worksheet_log.append_rows(rows_to_append)

                st.success("✅ 儲存成功！資料已回寫至紀錄表。")
                st.cache_data.clear()
                st.rerun()

    with tab1:
        render_tab(df_ins, "保險", "保險到期日")
    with tab2:
        render_tab(df_commercial, "商業險", "商業險到期日")
    with tab3:
        render_tab(df_inspect, "驗車", "驗車到期日")


# ================= 4. 路由控制 =================
if st.session_state['logged_in']:
    main_app()
else:

    login_page()
