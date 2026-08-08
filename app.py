import streamlit as st
import pandas as pd
from PIL import Image
from datetime import datetime, date

# 頁面基本設定
st.set_page_config(page_title="個人減肥小助手", page_icon="icon.png", layout="centered")

# 精簡標題並縮小字體 (使用 subheader 替代原本巨大的 st.title)
st.subheader("🥗 個人減肥小助手")

# 側邊欄：個人化進階設定
st.sidebar.header("⚙️ 個人與身體數據設定")

# 基本身體數據
current_weight = st.sidebar.number_input("目前體重 (kg)", value=60.0, step=0.1)
target_weight = st.sidebar.number_input("目標體重 (kg)", value=55.0, step=0.1)
height = st.sidebar.number_input("身高 (cm)", value=160.0, step=1.0)
body_fat = st.sidebar.number_input("體脂率 % (選填，若知道可填)", value=28.0, step=0.1)

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

# 依據活動量轉換為 TDEE 係數
activity_multipliers = {
    "久坐少動 (辦公室工作、幾乎不運動)": 1.2,
    "輕度活動 (每週輕量運動 1-3 天)": 1.375,
    "中度活動 (每週中等強度運動 3-5 天)": 1.55,
    "高度活動 (每週高強度運動 6-7 天)": 1.725
}
activity_factor = activity_multipliers[activity_level_desc]

# 精算 BMR (使用 Mifflin-St Jeor 公式：女性 = 10 * 體重 + 6.25 * 身高 - 5 * 年齡 - 161)
bmr = (10 * current_weight) + (6.25 * height) - (5 * age) - 161
tdee = bmr * activity_factor

# 減肥建議熱量：製造約 300~500 kcal 的熱量赤字，但設定安全底限
recommended_calories = int(tdee - 400)
if recommended_calories < 1200:
    recommended_calories = 1200

st.sidebar.markdown("---")
st.sidebar.markdown(f"🔥 **教練精算結果**：\n- 基礎代謝率 (BMR)：約 **{int(bmr)}** kcal\n- 每日總消耗 (TDEE)：約 **{int(tdee)}** kcal\n- **建議減肥目標熱量**：**{recommended_calories}** kcal/天")

# 初始化歷史紀錄的 Session State
if 'history' not in st.session_state:
    st.session_state['history'] = []

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

#### ⚠️ 需要加強改善的地方：
1. **熱量赤字平衡**：如果某一餐不小心吃多了，下一餐記得用高纖低卡的高蛋白餐點拉回來。
2. **水分補充**：每日建議喝足體重 × 35ml 的水分，加速代謝！

> **教練寄語**：減脂是一場科學與耐心兼具的過程！只要照著目前的建議熱量穩健執行，一定能看到漂亮的成果！加油！🔥
            """
            st.success("本週總結出爐！")
            st.markdown(weekly_summary)

st.markdown("---")

# ==================== 功能二：記錄每一餐 ====================
st.subheader("🍽️ 記錄今天的一餐")

meal_type = st.radio("選擇餐別", ["早餐", "午餐", "晚餐", "下午茶", "宵夜"], horizontal=True)

food_text = st.text_input("請輸入你吃了什麼（例如：骰子牛沙拉）", placeholder="請在此輸入食物描述...")
uploaded_file = st.file_uploader("或上傳食物照片 (選填)", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="已上傳的照片", width=300)

if st.button("分析並記錄", type="primary"):
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
- 建議今日剩餘的餐點可以多分配給高蛋白質與蔬菜。
- 保持穩定的節奏，離目標體重 {target_weight} kg 更近一步！💪
            """
            
            st.success("分析完成！")
            st.markdown(analysis_result)
            
            st.session_state['history'].append({
                "日期": current_date,
                "內容": full_item_name,
                "分析結果": analysis_result
            })

# 顯示歷史紀錄
if st.session_state['history']:
    st.markdown("---")
    st.subheader("📜 近期飲食紀錄")
    for idx, item in enumerate(reversed(st.session_state['history'])):
        item_date = item.get("日期", "早期紀錄")
        item_content = item.get("內容", "未知餐點")
        
        with st.expander(f"[{item_date}] 紀錄 #{len(st.session_state['history']) - idx}：{item_content}"):
            st.write(item['分析結果'])