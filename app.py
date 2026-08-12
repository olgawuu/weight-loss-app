import streamlit as st
import pandas as pd
import google.generativeai as genai
from PIL import Image
import plotly.express as px
from streamlit_gsheets import GSheetsConnection
import bcrypt
import json
from datetime import datetime

# 設定頁面標題與寬度
st.set_page_config(page_title="AI 減重飲食助手", page_icon="🥗", layout="wide")

# ==================== Google Sheets 資料庫串接 ====================
conn = st.connection("gsheets", type=GSheetsConnection)

# ── 使用者驗證與管理 ──
def load_users_from_gsheets():
    try:
        df = conn.read(worksheet="users", ttl="0s")
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame(columns=[
            "username", "password", "name", 
            "weight", "target_weight", "height", "body_fat", "activity_level"
        ])

def register_user(username, password, name):
    df_users = load_users_from_gsheets()
    
    if not df_users.empty and username in df_users['username'].astype(str).values:
        return False, "這個帳號（暱稱）已經有人使用過囉！"
    
    # 密碼 Hash 加密
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    new_user = pd.DataFrame([{
        "username": username,
        "password": hashed_pw,
        "name": name,
        "weight": 60.0,
        "target_weight": 50.0,
        "height": 160.0,
        "body_fat": 25.0,
        "activity_level": "久坐少動 (辦公室工作、幾乎不運動)"
    }])
    
    updated_df = pd.concat([df_users, new_user], ignore_index=True)
    try:
        conn.update(worksheet="users", data=updated_df)
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
    
    # 比對密碼
    if bcrypt.checkpw(password.encode('utf-8'), stored_pw.encode('utf-8')):
        return True, name
    else:
        return False, "密碼不正確！"

def update_user_profile(username, weight, target_weight, height, body_fat, activity_level):
    try:
        df_users = load_users_from_gsheets()
        idx = df_users[df_users['username'].astype(str) == str(username)].index
        if not idx.empty:
            df_users.loc[idx, 'weight'] = weight
            df_users.loc[idx, 'target_weight'] = target_weight
            df_users.loc[idx, 'height'] = height
            df_users.loc[idx, 'body_fat'] = body_fat
            df_users.loc[idx, 'activity_level'] = activity_level
            
            conn.update(worksheet="users", data=df_users)
            st.toast("個人身體數據已成功更新！", icon="✅")
    except Exception as e:
        st.error(f"更新數據失敗：{e}")


# ── 歷史紀錄與常用食物讀寫（含 username 多租戶過濾） ──
def load_history_from_gsheets(current_user):
    try:
        df = conn.read(worksheet="history", ttl="0s").dropna(how="all")
        if 'username' in df.columns:
            df_filtered = df[df['username'].astype(str) == str(current_user)]
            return df_filtered.to_dict('records')
        return []
    except Exception:
        return []

def save_history_to_gsheets(history_list):
    try:
        df_new = pd.DataFrame(history_list)
        try:
            df_existing = conn.read(worksheet="history", ttl="0s").dropna(how="all")
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        except Exception:
            df_combined = df_new

        conn.update(worksheet="history", data=df_combined)
    except Exception as e:
        st.error(f"寫入歷史紀錄失敗：{e}")

def load_common_foods_from_gsheets():
    try:
        df = conn.read(worksheet="common_foods", ttl="0s").dropna(how="all")
        foods = df['food'].dropna().tolist()
        return foods if foods else ["水煮蛋沙拉", "無糖豆漿 + 茶葉蛋", "雞胸肉糙米飯便當"]
    except Exception:
        return ["水煮蛋沙拉", "無糖豆漿 + 茶葉蛋", "雞胸肉糙米飯便當"]

def save_common_foods_to_gsheets(foods_list):
    try:
        df = pd.DataFrame({'food': foods_list})
        conn.update(worksheet="common_foods", data=df)
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
    tab1, tab2 = st.tabs(["🔑 登入帳號", "📝 註冊新帳號"])

    with tab1:
        st.subheader("使用者登入")
        login_user = st.text_input("帳號 (Username)", key="login_user")
        login_pwd = st.text_input("密碼 (Password)", type="password", key="login_pwd")
        if st.button("登入", type="primary"):
            if login_user and login_pwd:
                success, result = verify_user(login_user, login_pwd)
                if success:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = login_user
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
        if st.button("列車完成註冊"):
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

# 1. 撈取登入使用者的數據與個人化側邊欄
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
if st.sidebar.button("🔒 登出帳號"):
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.session_state['user_name'] = ""
    st.rerun()

st.sidebar.divider()
st.sidebar.markdown("### ⚙️ 個人與身體數據設定")

current_weight = st.sidebar.number_input("目前體重 (kg)", value=float(user_info.get('weight', 60.0)), step=0.1)
target_weight = st.sidebar.number_input("目標體重 (kg)", value=float(user_info.get('target_weight', 50.0)), step=0.1)
height = st.sidebar.number_input("身高 (cm)", value=float(user_info.get('height', 160.0)), step=0.5)
body_fat = st.sidebar.number_input("體脂率 % (選填)", value=float(user_info.get('body_fat', 25.0)), step=0.1)

activity_options = [
    "久坐少動 (辦公室工作、幾乎不運動)",
    "輕度活動 (每週運動 1-3 天)",
    "中度活動 (每週運動 3-5 天)",
    "高度活動 (每週運動 6-7 天)",
    "極高活動 (長時間勞動或運動員)"
]
saved_activity = str(user_info.get('activity_level', activity_options[0]))
activity_index = activity_options.index(saved_activity) if saved_activity in activity_options else 0

activity_level = st.sidebar.selectbox("日常活動量", options=activity_options, index=activity_index)

if st.sidebar.button("💾 儲存個人設定"):
    update_user_profile(
        st.session_state['username'], 
        current_weight, 
        target_weight, 
        height, 
        body_fat, 
        activity_level
    )

# 計算基礎對應估算熱量（估計值）
target_daily_calories = int(current_weight * 22 * (1.2 if "久坐" in activity_level else 1.375) - 300)

# 主頁面內容
st.title(f"🥗 {st.session_state['user_name']} 的 AI 減重飲食日誌")

# ── AI API 設定 ──
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("未找到 Gemini API Key，請檢查 Secrets 設定！")

# ── 頁籤：飲食估算與歷史紀錄 ──
tab_log, tab_history = st.tabs(["📸 新增飲食分析", "📜 歷史飲食紀錄"])

with tab_log:
    st.subheader("記錄今天的餐點")
    input_method = st.radio("選擇輸入方式：", ["上傳照片辨識", "文字描述餐點", "常用食物快速選擇"])

    meal_type = st.selectbox("餐別：", ["早餐", "午餐", "晚餐", "點心/宵夜"])
    
    image = None
    text_prompt = ""
    
    if input_method == "上傳照片辨識":
        uploaded_file = st.file_uploader("上傳食物照片", type=["jpg", "jpeg", "png"])
        if uploaded_file:
            image = Image.open(uploaded_file)
            st.image(image, caption="已上傳的照片", width=300)
            
    elif input_method == "文字描述餐點":
        text_prompt = st.text_input("輸入吃了什麼（例：半碗糙米飯 + 烤雞腿 + 燙青菜）")
        
    elif input_method == "常用食物快速選擇":
        common_foods = load_common_foods_from_gsheets()
        selected_food = st.selectbox("選擇常用食物：", common_foods)
        text_prompt = selected_food

    if st.button("🔍 開始 AI 估算營養", type="primary"):
        with st.spinner("AI 教練正在精算中..."):
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                
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

                if image:
                    response = model.generate_content([prompt, image])
                else:
                    response = model.generate_content([prompt, f"餐點內容：{text_prompt}"])

                # 清理與解析 JSON
                clean_res = response.text.replace("```json", "").replace("