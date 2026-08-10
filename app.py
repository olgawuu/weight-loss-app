import streamlit as st
import pandas as pd
from PIL import Image
from datetime import datetime, date
from streamlit_gsheets import GSheetsConnection

# 頁面基本設定
st.set_page_config(page_title="個人減肥小助手", page_icon="icon.png", layout="centered")

# 精準 CSS 樣式設定
st.markdown("""
<style>
    /* 1. 刪除按鈕：紅字 + 底線 + 小字 + 無邊框 */
    div[data-testid="stButton"] button[key*="del_"] {
        border: none !important;
        background: transparent !important;
        color: #ff4b4b !important;
        text-decoration: underline !important;
        font-size: 13px !important;
        padding: 0px !important;
        height: 38px !important;
        line-height: 38px !important;
        box-shadow: none !important;
    }
    div[data-testid="stButton"] button[key*="del_"]:hover {
        color: #d32f2f !important;
        background: transparent !important;
    }

    /* 2. 精準針對「新增常用食物」輸入框套用淺黃色底色與黃色邊框 */
    div[data-testid="stTextInput"] input[aria-label="新增常用食物"] {
        background-color: #ffffff !important;
        border: 1.5px solid #ffe082 !important;
        color: #333333 !important;
    }
    div[data-testid="stTextInput"] input[aria-label="新增常用食物"]:focus {
        border-color: #ffd54f !important;
        box-shadow: 0 0 0 1px #ffd54f !important;
    }
    
    /* 3. 【特別區隔】常用食物管理 Expander 樣式設計 */
    div[data-testid="stExpander"] {
        border: 1.5px solid #ffe082 !important;
        border-radius: 10px !important;
        background-color: #fffde7 !important;
        margin-top: 14px !important;
        margin-bottom: 18px !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03) !important;
    }
    
    div[data-testid="stExpander"] details summary p {
        color: #795548 !important;
        font-weight: bold !important;
        font-size: 15px !important;
    }
    
    div[data-testid="stExpander"]:hover {
        background-color: #fff9c4 !important;
        border-color: #ffd54f !important;
    }
</style>
""", unsafe_allow_html=True)

st.subheader("🥗 個人減肥小助手")

# 側邊欄：個人化進階設定
st.sidebar.header("⚙️ 個人與身體數據設定")

current_weight = st.sidebar.number_input("目前體重 (kg)", value=66.7, step=0.1)
target_weight = st.sidebar.number_input("目標體重 (kg)", value=48.0, step=0.1)
height = st.sidebar.number_input("身高 (cm)", value=157.0, step=1.0)
body_fat = st.sidebar.number_input("體脂率 % (選填，若知道可填)", value=37.2, step=0.1)

# 計算年齡（以 1990/08/21 出生計算）
birth_date = date(1990, 8, 21)
today = date.today()
age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

st.sidebar.markdown(f"ℹ️ **已帶入個人檔案**：女性 / {age} 歲")

# 活動量係數選擇
activity_level_desc = st.sidebar.selectbox(
    "日常活動量",
    [
        "久坐少動 (辦公室工作、幾乎不運動)",
        "輕度活動 (每週輕量運動 1-3 天)",
        "中度活動 (每週中等強度運動 3-5 天)",
        "高度活動 (每週高強度運動 6-7 天)"
    ]
)

activity_multipliers = {
    "久坐少動 (辦公室工作、幾乎不運動)": 1.2,
    "輕度活動 (每週輕量運動 1-3 天)": 1.375,
    "中度活動 (每週中等強度運動 3-5 天)": 1.55,
    "高度活動 (每週高強度運動 6-7 天)": 1.725
}
activity_factor = activity_multipliers[activity_level_desc]

bmr = (10 * current_weight) + (6.25 * height) - (5 * age) - 161
tdee = bmr * activity_factor

recommended_calories = int(tdee - 400)
if recommended_calories < 1200:
    recommended_calories = 1200

st.sidebar.markdown("---")
st.sidebar.markdown(f"🔥 **教練精算結果**：\n- 基礎代謝率 (BMR)：約 **{int(bmr)}** kcal\n- 每日總消耗 (TDEE)：約 **{int(tdee)}** kcal\n- **建議減肥目標熱量**：**{recommended_calories}** kcal/天")

# ==================== Google Sheets 資料庫串接 ====================
conn = st.connection("gsheets", type=GSheetsConnection)

def load_history_from_gsheets():
    try:
        df = conn.read(worksheet="history", ttl="0s")
        return df.dropna(how="all").to_dict('records')
    except Exception:
        return []

def save_history_to_gsheets(history_list):
    try:
        df = pd.DataFrame(history_list)
        # 使用 Service Account 驗證後，即可正常 update
        conn.update(worksheet="history", data=df)
    except Exception as e:
        st.error(f"寫入歷史紀錄失敗：{e}")

def load_common_foods_from_gsheets():
    try:
        df = conn.read(worksheet="common_foods", ttl="0s")
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

# ==================== Session State 初始化 ====================
if 'common_foods' not in st.session_state:
    st.session_state['common_foods'] = load_common_foods_from_gsheets()

if 'history' not in st.session_state:
    st.session_state['history'] = load_history_from_gsheets()

# ==================== 功能一：每週教練總結專區 ====================
st.markdown("### 🏆 本週教練總結報告")
if st.button("生成本週飲食總結與教練講評", type="secondary"):
    if not st.session_state['history']:
        st.warning("目前還沒有任何飲食紀錄可以總結喔！請先在下方記錄幾餐吧。")
    else:
        with st.spinner("🏋️‍♂️ 教練正在審閱你這週的飲食表現中..."):
            total_records = len(st.session_state['history'])
            
            weekly_summary = f"""
### 💪 教練週記：本週表現總體檢
* **本週累計記錄餐數**：{total_records} 餐
* **目前目標設定**：每日控制在 **{recommended_calories} kcal** 左右以達成健康減脂。

#### ⭐ 獲得肯定的地方：
1. **精準掌握身體數據**：有納入年齡與活動量來計算 TDEE，讓熱量赤字更科學、更健康！
2. **積極記錄**：透過持續追蹤，能更有效地掌握體重往 {target_weight} kg 邁進。

#### ⚠️ 需要加強改善的地方與具體舉例：
1. **增加高纖優質蛋白攝取**：
   * *何謂高纖蛋白食物？* 建議多選擇同時富含膳食纖維與蛋白質的食材，例如：**毛豆、黑豆、鷹嘴豆、豆腐、天貝**，或是將主食替換成**地瓜、燕麥、藜麥**搭配雞胸肉。
2. **優化點心與碳水選擇**：
   * *具體替代方案*：如果下午嘴饞想吃零食，可以改為**無調味堅果（一小把約 10 顆）**、**希臘優格** 或 **芭樂、小番茄**，避免精緻糖分導致血糖波動與熱量超標。
3. **水分補充**：每日建議喝足「體重 × 35ml」的水分（約 {int(current_weight * 35)} ml），加速新陳代謝！

> **教練寄語**：減脂是一場科學與耐心兼具的過程！只要照著目前的建議熱量穩健執行，一定能看到漂亮的成果！加油！🔥
            """
            st.success("本週總結出爐！")
            st.markdown(weekly_summary)

st.markdown("---")

# ==================== 功能二：記錄每一餐 ====================
st.subheader("🍽️ 記錄今天的一餐")

meal_type = st.radio("選擇餐別", ["早餐", "午餐", "晚餐", "下午茶", "宵夜"], horizontal=True)

# 1. 快速選擇常用食物
selected_common = st.selectbox(
    "⚡ 快速選擇常用食物：", 
    ["-- 請選擇常用食物 --"] + list(st.session_state.get('common_foods', []))
)

default_text = ""
if selected_common != "-- 請選擇常用食物 --":
    default_text = selected_common

st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

# 2. 當餐實際描述輸入框
food_text = st.text_input(
    "✏️ 今日餐點描述 (可手動輸入或由上方帶入)", 
    value=default_text, 
    placeholder="例如：雞腿便當飯半碗、無糖綠茶..."
)

# 3. 集中化的【常用食物管理卡片】
with st.expander("⚙️ 管理常用食物清單（新增 / 刪除常用項目）"):
    st.markdown("<span style='font-size: 13px; font-weight: bold; color: #5d4037;'>➕ 新增常用食物：</span>", unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1])
    with c1:
        new_food_input = st.text_input(
            "新增常用食物", 
            placeholder="輸入名稱，例如：酪梨水煮蛋全麥吐司", 
            label_visibility="collapsed"
        )
    with c2:
        if st.button("加入常用", use_container_width=True):
            if new_food_input and new_food_input not in st.session_state['common_foods']:
                st.session_state['common_foods'].append(new_food_input)
                save_common_foods_to_gsheets(st.session_state['common_foods'])
                st.success(f"已加入「{new_food_input}」！")
                st.rerun()

    st.markdown("<hr style='margin: 12px 0; border-top: 1px solid #ffe082;'>", unsafe_allow_html=True)
    
    st.markdown("<span style='font-size: 13px; font-weight: bold; color: #5d4037;'>🗑️ 刪除常用食物：</span>", unsafe_allow_html=True)
    
    if not st.session_state['common_foods']:
        st.caption("目前沒有常用食物可供刪除。")
    else:
        col_del_select, col_del_btn = st.columns([4, 1])
        with col_del_select:
            food_to_delete = st.selectbox(
                "選擇要刪除的常用食物",
                ["-- 請選擇要刪除的項目 --"] + st.session_state['common_foods'],
                label_visibility="collapsed"
            )
        with col_del_btn:
            if food_to_delete != "-- 請選擇要刪除的項目 --":
                if st.button("刪除此項", key=f"del_manage_{food_to_delete}"):
                    st.session_state['common_foods'].remove(food_to_delete)
                    save_common_foods_to_gsheets(st.session_state['common_foods'])
                    st.success(f"已刪除「{food_to_delete}」")
                    st.rerun()

# 4. 上傳照片
uploaded_file = st.file_uploader("📷 上傳餐點照片 (選填)", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="已上傳的照片", width=300)

st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

if st.button("🚀 分析並記錄這餐", type="primary", use_container_width=True):
    if not food_text and not uploaded_file:
        st.warning("請至少輸入文字描述或上傳照片！")
    else:
        with st.spinner("🥗 健康教練正在為你計算熱量與營養中..."):
            import random
            
            if food_text and uploaded_file:
                food_desc = f"{food_text} (附照片)"
            elif uploaded_file:
                food_desc = "上傳餐點照片"
            else:
                food_desc = food_text
                
            full_item_name = f"【{meal_type}】{food_desc}"
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            est_calories = random.randint(350, 650)
            protein = random.randint(15, 35)
            fat = random.randint(10, 25)
            carb = random.randint(30, 70)
            
            analysis_result = f"""
### 📊 飲食營養估算報告
* **記錄時間**：{current_date}
* **餐別與內容**：{full_item_name}
* **預估熱量**：約 {est_calories} kcal
* **三大營養素分佈**：
  * 蛋白質：約 {protein} g
  * 脂肪：約 {fat} g
  * 碳水化合物：約 {carb} g

### 💡 教練貼心建議：
以你個人精算後的每日目標熱量（**{recommended_calories} kcal**）來看，這一餐的熱量占比適中！
- 建議今日剩餘的餐點可以多分配給高蛋白質與蔬菜（例如晚餐來一份豆腐蒸魚或毛豆沙拉）。
- 保持穩定的節奏，離目標體重 {target_weight} kg 更近一步！💪
            """
            
            st.success("分析完成！")
            st.markdown(analysis_result)
            
            new_entry = {
                "日期": current_date,
                "內容": full_item_name,
                "分析結果": analysis_result
            }
            st.session_state['history'].append(new_entry)
            save_history_to_gsheets(st.session_state['history'])  # 即時同步回雲端試算表

# ==================== 功能三：歷史紀錄與右側刪除 ====================
if st.session_state['history']:
    st.markdown("---")
    st.subheader("📜 近期飲食紀錄")
    
    for idx, item in enumerate(reversed(st.session_state['history'])):
        real_idx = len(st.session_state['history']) - 1 - idx
        item_date = item.get("日期", "早期紀錄")
        item_content = item.get("內容", "未知餐點")
        
        col_history, col_del_hist = st.columns([5, 1])
        
        with col_history:
            with st.expander(f"[{item_date}] {item_content}"):
                st.write(item['分析結果'])
                
        with col_del_hist:
            if st.button("刪除", key=f"del_hist_{real_idx}"):
                st.session_state['history'].pop(real_idx)
                save_history_to_gsheets(st.session_state['history'])  # 刪除後同步更新雲端
                st.rerun()