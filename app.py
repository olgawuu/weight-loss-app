import streamlit as st
import pandas as pd
from PIL import Image
import plotly.express as px
import bcrypt
import json
import os
import re
from datetime import datetime, date
import gspread
from google.oauth2.service_account import Credentials

# 設定頁面標題與寬度
st.set_page_config(page_title="AI 減重飲食助手", page_icon="🥗", layout="wide")

# ==================== Google Sheets 安全連線處理 ====================
def get_gsheets_client():
    creds_dict = dict(st.secrets["connections"]["gsheets"])

    if "private_key" in creds_dict:
        pk = creds_dict["private_key"]
        pk = pk.replace("\\n", "\n")

        if not pk.startswith("-----BEGIN PRIVATE KEY-----"):
            pk = "-----BEGIN PRIVATE KEY-----\n" + pk
        if not pk.endswith("-----END PRIVATE KEY-----"):
            pk = pk + "\n-----END PRIVATE KEY-----"

        creds_dict["private_key"] = pk

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def get_worksheet(worksheet_name):
    client = get_gsheets_client()
    spreadsheet_url = st.secrets["connections"]["gsheets"].get("spreadsheet")
    if spreadsheet_url:
        spreadsheet = client.open_by_url(spreadsheet_url)
    else:
        spreadsheet = client.open("飲食紀錄")

    try:
        return spreadsheet.worksheet(worksheet_name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=worksheet_name, rows="100", cols="20")
        return ws

# ── 使用者驗證與管理 ──
def load_users_from_gsheets():
    try:
        ws = get_worksheet("users")
        rows = ws.get_all_values()
        if not rows or len(rows) <= 1:
            return pd.DataFrame(columns=["username", "password", "name", "weight", "target_weight", "height", "body_fat", "activity_level"])
        headers = [str(h).strip() for h in rows[0]]
        data = rows[1:]
        df = pd.DataFrame(data, columns=headers)
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame(columns=["username", "password", "name", "weight", "target_weight", "height", "body_fat", "activity_level"])

def register_user(username, password, name):
    df_users = load_users_from_gsheets()

    if not df_users.empty and username in df_users['username'].astype(str).values:
        return False, "這個帳號（暱稱）已經有人使用過囉！"

    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    try:
        ws = get_worksheet("users")
        existing_data = ws.get_all_values()
        if not existing_data:
            headers = ["username", "password", "name", "weight", "target_weight", "height", "body_fat", "activity_level"]
            ws.append_row(headers)

        new_row = [
            username, hashed_pw, name,
            60.0, 50.0, 160.0, 25.0,
            "久坐少動 (辦公室工作、幾乎不運動)"
        ]
        ws.append_row(new_row)
        return True, "註冊成功！請切換至登入頁面登入。"
    except Exception as e:
        return False, f"註冊失敗：{e}"

def verify_user(username, password):
    df_users = load_users_from_gsheets()
    if df_users.empty:
        return False, "帳號不存在，請先註冊！"

    user_row = df_users[df_users['username'].astype(str) == str(username)]

    if user_row.empty:
        return False, "帳號不存在，請先註冊！"

    stored_pw = str(user_row.iloc[0]['password'])
    name = user_row.iloc[0]['name']

    if bcrypt.checkpw(password.encode('utf-8'), stored_pw.encode('utf-8')):
        return True, name
    else:
        return False, "密碼不正確！"

def update_user_profile(username, weight, target_weight, height, body_fat, activity_level):
    try:
        ws = get_worksheet("users")
        rows = ws.get_all_values()
        if not rows:
            headers = ["username", "password", "name", "weight", "target_weight", "height", "body_fat", "activity_level"]
            df_users = pd.DataFrame(columns=headers)
        else:
            df_users = pd.DataFrame(rows[1:], columns=[str(h).strip() for h in rows[0]])

        idx = df_users[df_users['username'].astype(str) == str(username)].index

        if not idx.empty:
            df_users.loc[idx[0], 'weight'] = weight
            df_users.loc[idx[0], 'target_weight'] = target_weight
            df_users.loc[idx[0], 'height'] = height
            df_users.loc[idx[0], 'body_fat'] = body_fat
            df_users.loc[idx[0], 'activity_level'] = activity_level

            ws.clear()
            ws.append_row(["username", "password", "name", "weight", "target_weight", "height", "body_fat", "activity_level"])
            for _, row in df_users.iterrows():
                ws.append_row(row.tolist())

            st.toast("個人身體數據已成功更新！", icon="✅")
    except Exception as e:
        st.error(f"更新數據失敗：{e}")

# ── 歷史紀錄與常用食物讀寫 ──
def load_history_from_gsheets(current_user, current_display_name=""):
    """彈性搜尋使用者歷史紀錄（同時比對 username 與暱稱）"""
    try:
        ws = get_worksheet("history")
        rows = ws.get_all_values()

        if not rows or len(rows) <= 1:
            return []

        headers = [str(h).strip() for h in rows[0]]
        df = pd.DataFrame(rows[1:], columns=headers)

        if 'username' in df.columns:
            u_str = str(current_user).strip().lower()
            n_str = str(current_display_name).strip().lower()

            df['clean_user'] = df['username'].astype(str).str.strip().str.lower()

            df_filtered = df[(df['clean_user'] == u_str) | (df['clean_user'] == n_str)]

            if df_filtered.empty and len(df['clean_user'].unique()) == 1:
                df_filtered = df

            return df_filtered.to_dict('records')
        return []
    except Exception as e:
        st.error(f"⚠️ 讀取歷史紀錄發生錯誤：{e}")
        return []

def save_history_to_gsheets(history_list):
    try:
        ws = get_worksheet("history")
        existing_data = ws.get_all_values()

        if not existing_data or len(existing_data) == 0 or existing_data[0] == ['']:
            headers = ["username", "time", "meal", "food", "calories", "protein", "fat", "carbs"]
            ws.clear()
            ws.append_row(headers)

        for record in history_list:
            row = [
                str(record.get("username", "")),
                str(record.get("time", "")),
                str(record.get("meal", "")),
                str(record.get("food", "")),
                str(record.get("calories", 0)),
                str(record.get("protein", 0)),
                str(record.get("fat", 0)),
                str(record.get("carbs", 0))
            ]
            ws.append_row(row)
    except Exception as e:
        st.error(f"寫入雲端失敗：{e}")

def delete_history_item(username, record_time):
    try:
        ws = get_worksheet("history")
        rows = ws.get_all_values()
        if not rows or len(rows) <= 1:
            return

        headers = [str(h).strip() for h in rows[0]]
        df = pd.DataFrame(rows[1:], columns=headers)

        if not df.empty and 'time' in df.columns:
            df_updated = df[~(df['time'].astype(str) == str(record_time))]

            ws.clear()
            ws.append_row(headers)
            for _, row in df_updated.iterrows():
                ws.append_row(row.tolist())
    except Exception as e:
        st.error(f"刪除失敗：{e}")

def load_common_foods_from_gsheets():
    try:
        ws = get_worksheet("common_foods")
        rows = ws.get_all_values()
        if not rows or len(rows) <= 1:
            return ["水煮蛋沙拉", "無糖豆漿 + 茶葉蛋", "雞胸肉糙米飯便當"]

        headers = [str(h).strip() for h in rows[0]]
        df = pd.DataFrame(rows[1:], columns=headers)
        if 'food' in df.columns:
            foods = df['food'].dropna().tolist()
            return foods if foods else ["水煮蛋沙拉", "無糖豆漿 + 茶葉蛋", "雞胸肉糙米飯便當"]
        return ["水煮蛋沙拉", "無糖豆漿 + 茶葉蛋", "雞胸肉糙米飯便當"]
    except Exception:
        return ["水煮蛋沙拉", "無糖豆漿 + 茶葉蛋", "雞胸肉糙米飯便當"]

def save_common_foods_to_gsheets(foods_list):
    try:
        ws = get_worksheet("common_foods")
        ws.clear()
        ws.append_row(["food"])
        for food in foods_list:
            ws.append_row([food])
    except Exception as e:
        st.error(f"寫入常用食物失敗：{e}")

# ==================== 登入 / 註冊 邏輯控制 ====================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'user_name' not in st.session_state:
    st.session_state['user_name'] = ""

if not st.session_state['logged_in']:
    st.title("🥗 AI 減重飲食助手")
    st.caption("拍張照，AI 幫你算熱量；每天記錄，離目標更近一步。")
    tab1, tab2 = st.tabs(["🔑 登入帳號", "📝 註冊新帳號"])

    with tab1:
        st.subheader("使用者登入")
        with st.form("login_form", clear_on_submit=False):
            login_user = st.text_input("帳號 (Username)", key="login_user")
            login_pwd = st.text_input("密碼 (Password)", type="password", key="login_pwd")
            submit_login = st.form_submit_button("登入", type="primary", use_container_width=True)

        if submit_login:
            user_clean = login_user.strip() if login_user else ""
            pwd_clean = login_pwd.strip() if login_pwd else ""

            if user_clean and pwd_clean:
                with st.spinner("驗證中..."):
                    success, result = verify_user(user_clean, pwd_clean)
                if success:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = user_clean
                    st.session_state['user_name'] = result
                    st.success(f"歡迎回來，{result}！")
                    st.rerun()
                else:
                    st.error(result)
            else:
                st.warning("請填寫帳號與密碼！")
    with tab2:
        st.subheader("建立新帳號")
        reg_user = st.text_input("設定帳號 (英文/數字佳)", key="reg_user")
        reg_name = st.text_input("你的暱稱 (顯示於 App 內)", key="reg_name")
        reg_pwd = st.text_input("設定密碼", type="password", key="reg_pwd")
        if st.button("完成註冊", type="primary", use_container_width=True):
            if reg_user and reg_pwd and reg_name:
                ok, msg = register_user(reg_user, reg_pwd, reg_name)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
            else:
                st.warning("所有欄位皆為必填！")

    st.stop()


# ==================== 主介面（登入成功後） ====================
df_users = load_users_from_gsheets()
user_row = df_users[df_users['username'].astype(str) == str(st.session_state['username'])]

if not user_row.empty:
    user_info = user_row.iloc[0].to_dict()
else:
    user_info = {
        'weight': 60.0, 'target_weight': 50.0, 'height': 160.0,
        'body_fat': 25.0, 'activity_level': "久坐少動 (辦公室工作、幾乎不運動)"
    }

st.sidebar.markdown(f"### 👋 哈囉，{st.session_state['user_name']}！")
if st.sidebar.button("🔒 登出帳號", use_container_width=True):
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.session_state['user_name'] = ""
    st.rerun()

st.sidebar.divider()

with st.sidebar.expander("⚙️ 個人與身體數據設定", expanded=True):
    current_weight = st.number_input("目前體重 (kg)", value=float(user_info.get('weight', 60.0)), step=0.1)
    target_weight = st.number_input("目標體重 (kg)", value=float(user_info.get('target_weight', 50.0)), step=0.1)
    height = st.number_input("身高 (cm)", value=float(user_info.get('height', 160.0)), step=0.5)
    body_fat = st.number_input("體脂率 % (選填)", value=float(user_info.get('body_fat', 25.0)), step=0.1)

    activity_options = [
        "久坐少動 (辦公室工作、幾乎不運動)",
        "輕度活動 (每週運動 1-3 天)",
        "中度活動 (每週運動 3-5 天)",
        "高度活動 (每週運動 6-7 天)",
        "極高活動 (長時間勞動或運動員)"
    ]
    # 各活動量對應的熱量係數（原本只判斷「久坐」與否，其餘等級無效，這裡修正為完整對照）
    activity_multipliers = {
        "久坐少動 (辦公室工作、幾乎不運動)": 1.2,
        "輕度活動 (每週運動 1-3 天)": 1.375,
        "中度活動 (每週運動 3-5 天)": 1.55,
        "高度活動 (每週運動 6-7 天)": 1.725,
        "極高活動 (長時間勞動或運動員)": 1.9,
    }
    saved_activity = str(user_info.get('activity_level', activity_options[0]))
    activity_index = activity_options.index(saved_activity) if saved_activity in activity_options else 0

    activity_level = st.selectbox("日常活動量", options=activity_options, index=activity_index)

    if st.button("💾 儲存個人設定", use_container_width=True, type="primary"):
        update_user_profile(
            st.session_state['username'],
            current_weight,
            target_weight,
            height,
            body_fat,
            activity_level
        )

multiplier = activity_multipliers.get(activity_level, 1.2)
target_daily_calories = int(current_weight * 22 * multiplier - 300)

# 側邊欄額外顯示 BMI 與熱量目標，讓使用者一眼掌握狀態
bmi = current_weight / ((height / 100) ** 2) if height else 0
st.sidebar.divider()
st.sidebar.markdown("### 📊 快速數據")
c1, c2 = st.sidebar.columns(2)
c1.metric("BMI", f"{bmi:.1f}")
c2.metric("每日目標熱量", f"{target_daily_calories} kcal")

st.title(f"🥗 {st.session_state['user_name']} 的 AI 減重飲食日誌")

# ── 今日總覽儀表板 ──
_history_for_dashboard = load_history_from_gsheets(
    st.session_state.get('username', ''), st.session_state.get('user_name', '')
)
today_str = date.today().strftime("%Y-%m-%d")
today_calories = 0
if _history_for_dashboard:
    _df_dash = pd.DataFrame(_history_for_dashboard)
    if 'time' in _df_dash.columns and 'calories' in _df_dash.columns:
        _df_dash['date_only'] = _df_dash['time'].astype(str).str[:10]
        _df_dash['calories_num'] = pd.to_numeric(_df_dash['calories'], errors='coerce').fillna(0)
        today_calories = _df_dash.loc[_df_dash['date_only'] == today_str, 'calories_num'].sum()

remaining_calories = target_daily_calories - today_calories

st.markdown("#### 📅 今日總覽")
m1, m2, m3 = st.columns(3)
m1.metric("今日已攝取", f"{int(today_calories)} kcal")
m2.metric("每日目標", f"{target_daily_calories} kcal")
m3.metric("剩餘額度", f"{int(remaining_calories)} kcal", delta=None)

progress_ratio = 0.0
if target_daily_calories > 0:
    progress_ratio = min(today_calories / target_daily_calories, 1.0)
st.progress(progress_ratio)
if remaining_calories < 0:
    st.warning(f"⚠️ 今天已超過目標熱量 {abs(int(remaining_calories))} kcal，晚餐可以吃清淡一點喔！")

st.divider()

# ── 頁籤切換：新增飲食與歷史紀錄 ──
tab_log, tab_history = st.tabs(["📸 新增飲食分析", "📜 歷史飲食紀錄"])

# ==========================================
# Tab 1: 新增飲食分析
# ==========================================
with tab_log:
    st.subheader("記錄今天的餐點")

    col_date, col_meal = st.columns(2)
    with col_date:
        record_date = st.date_input("📅 紀錄日期", value=date.today(), max_value=date.today())
    with col_meal:
        meal_type = st.selectbox("🍽️ 餐別：", ["早餐", "午餐", "晚餐", "點心/宵夜"])

    input_method = st.radio("選擇輸入方式：", ["上傳照片辨識", "文字描述餐點", "常用食物快速選擇"], horizontal=True)

    image = None
    text_prompt = ""

    if input_method == "上傳照片辨識":
        uploaded_file = st.file_uploader("上傳食物照片", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            image = Image.open(uploaded_file)
            col_img, _ = st.columns([1, 2])
            with col_img:
                st.image(image, caption="已上傳的照片", use_container_width=True)

    elif input_method == "文字描述餐點":
        text_prompt = st.text_input("輸入吃了什麼（例：半碗糙米飯 + 烤雞腿 + 燙青菜）", key="text_food_input")

    elif input_method == "常用食物快速選擇":
        common_foods = load_common_foods_from_gsheets()

        if common_foods:
            selected_food = st.selectbox("選擇常用食物：", common_foods)
            text_prompt = selected_food
        else:
            st.info("目前清單中沒有常用食物，請在下方新增！")
            text_prompt = ""

        with st.expander("⚙️ 管理常用食物清單（新增 / 刪除）"):
            col1, col2 = st.columns([3, 1])
            with col1:
                new_food_input = st.text_input("輸入新食物名稱（例如：地瓜 + 美式咖啡）", key="new_food_input")
            with col2:
                st.write(" ")
                st.write(" ")
                if st.button("➕ 新增", use_container_width=True):
                    if new_food_input and new_food_input not in common_foods:
                        common_foods.append(new_food_input)
                        save_common_foods_to_gsheets(common_foods)
                        st.toast(f"已新增：{new_food_input}", icon="✅")
                        st.rerun()
                    elif new_food_input in common_foods:
                        st.warning("這個食物已經在清單中囉！")

            st.divider()

            if common_foods:
                food_to_delete = st.selectbox("選擇要刪除的常用食物：", common_foods, key="del_food_select")
                if st.button("🗑️ 刪除選取食物", type="secondary"):
                    common_foods.remove(food_to_delete)
                    save_common_foods_to_gsheets(common_foods)
                    st.toast(f"已刪除：{food_to_delete}", icon="🗑️")
                    st.rerun()

    st.write("")
    # ── 按鈕點擊與分析邏輯 ──
    if st.button("🔍 開始 AI 估算營養", type="primary", use_container_width=True):
        if input_method == "上傳照片辨識" and image is None:
            st.warning("請先上傳食物照片喔！")
        elif input_method in ["文字描述餐點", "常用食物快速選擇"] and not text_prompt.strip():
            st.warning("請先輸入或選擇餐點內容喔！")
        else:
            with st.spinner("AI 教練正在精算中..."):
                try:
                    from google import genai

                    api_key = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("connections", {}).get("gsheets", {}).get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
                    if not api_key:
                        raise Exception("尚未設定 API Key，請至 Streamlit Secrets 設定 GEMINI_API_KEY。")

                    client = genai.Client(api_key=str(api_key))

                    prompt = f"""
                    你是一位專業的減重營養師。使用者資訊：
                    - 目前體重：{current_weight} kg
                    - 目標體重：{target_weight} kg
                    - 每日目標熱量：{target_daily_calories} kcal

                    請分析此餐點（{meal_type}）：
                    請以 JSON 格式回應，包含以下 key：
                    - "food_summary": "餐點內容簡述"
                    - "calories": 熱量估算(整數)
                    - "protein": 蛋白質估計克數(整數)
                    - "fat": 脂肪估計克數(整數)
                    - "carbs": 碳水化合物估計克數(整數)
                    - "advice": "給使用者的貼心減重建議（100字內）"
                    回應必須是合法的 JSON 格式，不要加多餘文字。
                    """

                    model_id = "gemini-3.6-flash"

                    if input_method == "上傳照片辨識" and image:
                        response = client.models.generate_content(
                            model=model_id,
                            contents=[prompt, image]
                        )
                    else:
                        response = client.models.generate_content(
                            model=model_id,
                            contents=[prompt, f"餐點內容：{text_prompt}"]
                        )

                    clean_res = re.sub(r'```(?:json)?', '', response.text).strip()
                    result = json.loads(clean_res)

                    st.success("分析完成！")
                    st.markdown("### 📋 飲食營養估算報告")
                    st.markdown(f"* **紀錄日期：** {record_date.strftime('%Y-%m-%d')}")
                    st.markdown(f"* **餐點內容：** 【{meal_type}】{result.get('food_summary', '自訂餐點')}")
                    st.markdown(f"* **預估熱量：** 約 {result.get('calories', 0)} kcal")
                    st.markdown(f"* **三大營養素分布：** 蛋白質 {result.get('protein', 0)}g | 脂肪 {result.get('fat', 0)}g | 碳水化合物 {result.get('carbs', 0)}g")
                    st.info(f"💡 **教練貼心建議：**\n\n{result.get('advice', '')}")

                    # 使用選擇的日期 + 當下時間，組成完整時間戳記
                    now_time_str = datetime.now().strftime("%H:%M")
                    record_datetime_str = f"{record_date.strftime('%Y-%m-%d')} {now_time_str}"

                    new_record = [{
                        "username": st.session_state['username'],
                        "time": record_datetime_str,
                        "meal": meal_type,
                        "food": result.get('food_summary', text_prompt),
                        "calories": result.get('calories', 0),
                        "protein": result.get('protein', 0),
                        "fat": result.get('fat', 0),
                        "carbs": result.get('carbs', 0)
                    }]
                    save_history_to_gsheets(new_record)
                    st.toast("已成功記錄至你的個人雲端日誌！", icon="📝")

                except Exception as e:
                    st.error(f"分析失敗，請重新嘗試：{e}")


# ==========================================
# Tab 2: 歷史飲食紀錄（相容搜尋 + 篩選 + 趨勢圖）
# ==========================================
with tab_history:
    st.subheader("📜 個人歷史飲食日誌")

    current_user_account = st.session_state.get('username', '')
    current_user_display = st.session_state.get('user_name', '')

    history_data = load_history_from_gsheets(current_user_account, current_user_display)

    if not history_data:
        st.info("💡 目前尚無飲食紀錄，或是雲端試算表中尚未寫入任何歷史資料喔！快去「新增飲食分析」試試看吧。")
    else:
        df_hist = pd.DataFrame(history_data)
        df_hist['calories_num'] = pd.to_numeric(df_hist.get('calories', 0), errors='coerce').fillna(0)
        df_hist['date_only'] = df_hist['time'].astype(str).str[:10]
        df_hist['date_parsed'] = pd.to_datetime(df_hist['date_only'], errors='coerce')

        # ── 篩選區 ──
        with st.expander("🔎 篩選條件", expanded=False):
            fc1, fc2, fc3 = st.columns([1.2, 1, 1.5])
            min_date = df_hist['date_parsed'].min()
            max_date = df_hist['date_parsed'].max()
            with fc1:
                if pd.notna(min_date) and pd.notna(max_date):
                    date_range = st.date_input(
                        "日期區間",
                        value=(min_date.date(), max_date.date()),
                        min_value=min_date.date(),
                        max_value=max_date.date(),
                    )
                else:
                    date_range = None
            with fc2:
                meal_filter = st.multiselect("餐別", ["早餐", "午餐", "晚餐", "點心/宵夜"])
            with fc3:
                keyword_filter = st.text_input("搜尋食物關鍵字")

        df_filtered = df_hist.copy()
        if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
            start_d, end_d = date_range
            df_filtered = df_filtered[
                (df_filtered['date_parsed'] >= pd.to_datetime(start_d)) &
                (df_filtered['date_parsed'] <= pd.to_datetime(end_d))
            ]
        if meal_filter:
            df_filtered = df_filtered[df_filtered['meal'].isin(meal_filter)]
        if keyword_filter:
            df_filtered = df_filtered[df_filtered['food'].astype(str).str.contains(keyword_filter, case=False, na=False)]

        st.success(f"共找到 {len(df_filtered)} 筆紀錄（總資料 {len(df_hist)} 筆）")

        # ── 每日熱量趨勢圖 ──
        if not df_filtered.empty:
            daily_sum = df_filtered.groupby('date_only', as_index=False)['calories_num'].sum()
            daily_sum = daily_sum.sort_values('date_only')
            fig = px.bar(
                daily_sum, x='date_only', y='calories_num',
                labels={'date_only': '日期', 'calories_num': '熱量 (kcal)'},
                title="每日攝取熱量趨勢"
            )
            fig.add_hline(
                y=target_daily_calories, line_dash="dash", line_color="red",
                annotation_text="每日目標熱量", annotation_position="top left"
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # 依照時間倒序排列（最新紀錄放在最上面）
        history_records_sorted = df_filtered.sort_values('time', ascending=False).to_dict('records')

        for idx, item in enumerate(history_records_sorted):
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])

                with col1:
                    time_val = item.get('time', '時間未填')
                    meal_val = item.get('meal', '餐別未填')
                    food_val = item.get('food', '餐點內容未填')
                    cal_val = item.get('calories', 0)
                    p_val = item.get('protein', 0)
                    f_val = item.get('fat', 0)
                    c_val = item.get('carbs', 0)

                    st.markdown(f"**⏰ 時間：** {time_val} | **餐別：** {meal_val}")
                    st.markdown(f"**🥗 餐點：** {food_val}")
                    st.markdown(
                        f"🔥 **熱量：** {cal_val} kcal | "
                        f"💪 蛋白質: {p_val}g | "
                        f"🥑 脂肪: {f_val}g | "
                        f"🍞 碳水: {c_val}g"
                    )

                with col2:
                    if st.button("🗑️ 刪除", key=f"del_his_{idx}_{item.get('time','')}"):
                        try:
                            delete_time = item.get('time', '')
                            delete_history_item(current_user_account, delete_time)
                            st.toast("紀錄已順利刪除！", icon="🗑️")
                            st.rerun()
                        except Exception as e:
                            st.error(f"刪除失敗：{e}")
