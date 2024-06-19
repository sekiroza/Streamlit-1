import streamlit as st
import sqlite3
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import io
import spacy
import numpy as np
from datetime import datetime, timedelta
from streamlit_drawable_canvas import st_canvas

# 確保 Spacy 中文和英文模型已安裝
try:
    spacy_zh = spacy.load("zh_core_web_sm")
except IOError:
    from spacy.cli import download
    download("zh_core_web_sm")
    spacy_zh = spacy.load("zh_core_web_sm")

try:
    spacy_en = spacy.load("en_core_web_sm")
except IOError:
    from spacy.cli import download
    download("en_core_web_sm")
    spacy_en = spacy.load("en_core_web_sm")
# 初始化数据库连接
conn = sqlite3.connect('users.db')
c = conn.cursor()

# 检查并添加缺失的数据库列
def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [info[1] for info in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

add_column_if_not_exists(c, 'users', 'membership', 'TEXT')
add_column_if_not_exists(c, 'users', 'role', 'TEXT DEFAULT "user"')
add_column_if_not_exists(c, 'users', 'credits', 'INTEGER DEFAULT 0')
add_column_if_not_exists(c, 'users', 'premium_expiry', 'TEXT')
add_column_if_not_exists(c, 'users', 'free_uses', 'INTEGER DEFAULT 0')

# 设置 Tesseract OCR 的路径
pytesseract.pytesseract.tesseract_cmd = r'Tesseract-OCR\tesseract.exe'

# 主函数
def main():
    st.title("基於Streamlit的PDF圖片提取並進行ocr")

    # 初始化session state
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['username'] = ""
        st.session_state['membership'] = ""
        st.session_state['role'] = ""
        st.session_state['credits'] = 0
        st.session_state['premium_expiry'] = None
        st.session_state['free_uses'] = 0

    # 登录状态判断
    if st.session_state['logged_in']:
        st.write(f"歡迎，{st.session_state['username']}！")
        if st.session_state['role'] == 'admin':
            admin_page()
        else:
            user_page()
    else:
        menu = ["登錄", "註冊"]
        choice = st.sidebar.selectbox("選擇操作", menu)

        if choice == "登錄":
            login()
        elif choice == "註冊":
            signup()

# 登录功能
def login():
    st.subheader("請登入")
    username = st.text_input("使用者名稱")
    password = st.text_input("密碼", type="password")

    if st.button("登入"):
        user = validate_login(username, password)
        if user:
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.session_state['membership'] = user[2]
            st.session_state['role'] = user[3]
            st.session_state['credits'] = user[4] if user[4] is not None else 0
            st.session_state['premium_expiry'] = user[5]
            st.session_state['free_uses'] = user[6] if user[6] is not None else 0
            st.success("登入成功！")
            st.experimental_rerun()
        else:
            st.error("使用者名稱或密碼錯誤")

# 注册功能
def signup():
    st.subheader("註冊新帳戶")
    new_username = st.text_input("新使用者")
    new_password = st.text_input("新密碼", type="password")
    membership_type = st.selectbox("選擇會員類型", ["free"])

    if st.button("註冊"):
        if not validate_signup(new_username):
            create_user(new_username, new_password, membership_type)
            st.success("註冊成功，請登入！")
        else:
            st.error("名字已存在，請選擇其他名字。")

# 验证登录
def validate_login(username, password):
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    return c.fetchone()

# 验证注册
def validate_signup(username):
    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    return c.fetchone()

# 创建用户
def create_user(username, password, membership, role='user'):
    c.execute("INSERT INTO users (username, password, membership, role, credits, free_uses) VALUES (?, ?, ?, ?, ?, ?)", (username, password, membership, role, 0, 0))
    conn.commit()

# 升级会员
def upgrade_membership(username):
    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    c.execute("UPDATE users SET membership = 'premium', premium_expiry = ? WHERE username = ?", (expiry_date, username))
    conn.commit()

# 降级会员
def downgrade_membership(username):
    c.execute("UPDATE users SET membership = 'free', premium_expiry = NULL WHERE username = ?", (username,))
    conn.commit()

# 删除用户
def delete_user(username):
    c.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()

# 更新滑书框使用次数
def update_free_uses(username):
    c.execute("UPDATE users SET free_uses = free_uses + 1 WHERE username = ?", (username,))
    conn.commit()

# 用户界面
def user_page():
    # 检查付费会员到期时间
    if st.session_state['membership'] == 'premium':
        if st.session_state['premium_expiry']:
            expiry_date = datetime.strptime(st.session_state['premium_expiry'], '%Y-%m-%d').date()
            remaining_days = (expiry_date - datetime.now().date()).days
            if remaining_days > 0:
                st.write(f"您的付費會員還剩 {remaining_days} 天")
            else:
                downgrade_membership(st.session_state['username'])
                st.session_state['membership'] = 'free'
                st.session_state['premium_expiry'] = None
                st.warning("您的付費會員已過期。")
                st.experimental_rerun()
        else:
            st.write("這是付費會員專屬的受保護內容")
            protected_content()
    else:
        st.write("這是免費會員內容")
        if st.session_state['free_uses'] < 5:
            protected_content()
        else:
            st.warning("您的免費滑鼠框次數已用完。請儲值以獲得更多次數或升級至付費會員")

        card_number = st.text_input('信用卡號')
        expiry_date = st.text_input('到期日（MM/YY）')
        cvv = st.text_input('CVV', type='password')
        amount = st.number_input('輸入儲值金額', min_value=1, max_value=100)

        if st.button('儲值'):
            if not validate_card_number(card_number):
                st.error('無效的信用卡號，應為十六位數字')
            elif not validate_expiry_date(expiry_date):
                st.error('無效的到期日，格式應為MM/YY')
            elif not validate_cvv(cvv):
                st.error('無效的CVV，應為三位數字')
            else:
                update_credits(st.session_state['username'], amount)
                st.session_state['credits'] += amount
                st.success(f'成功增加 {amount} 點數！')
                st.experimental_rerun()

        if st.session_state['credits'] is not None and st.session_state['credits'] >= 100:
            if st.session_state['premium_expiry'] and datetime.now().date() < datetime.strptime(st.session_state['premium_expiry'], '%Y-%m-%d').date():
                st.write(f"您的會員資格將於 {st.session_state['premium_expiry']} 過期，在此之前無法再購買")
            else:
                if st.button("使用100點數升級到付費會員"):
                    if st.session_state['credits'] >= 100:
                        upgrade_membership(st.session_state['username'])
                        st.session_state['credits'] -= 100
                        st.session_state['membership'] = 'premium'
                        st.session_state['premium_expiry'] = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                        st.success("升級成功！現在您是付費會員，可以存取更多內容")
                        st.experimental_rerun()
                    else:
                        st.error("您的點數不足")

    if st.button("登出"):
        st.session_state['logged_in'] = False
        st.session_state['username'] = ""
        st.session_state['membership'] = ""
        st.session_state['role'] = ""
        st.session_state['credits'] = 0
        st.session_state['premium_expiry'] = None
        st.session_state['free_uses'] = 0
        st.experimental_rerun()

# 管理员界面
def admin_page():
    st.write("這是管理者介面。您可以管理用戶。")

    users = get_all_users()
    for user in users:
        if user[0] != st.session_state['username']:  # 管理者不能删除自己
            st.write(f"使用者名稱: {user[0]}, 會員類型: {user[2]}, 角色: {user[3]}, 點數: {user[4]}, 會員到期時間: {user[5]}, 免費使用次數: {user[6]}")
            if st.button(f"刪除 {user[0]}"):
                delete_user(user[0])
                st.success(f"使用者 {user[0]} 已刪除。")
                st.experimental_rerun()
    
    if st.button("重置所有免費用戶的使用次數"):
        reset_free_uses()
        st.success("所有免費用戶的使用次數已重置。")
        st.experimental_rerun()

    if st.button("登出"):
        st.session_state['logged_in'] = False
        st.session_state['username'] = ""
        st.session_state['membership'] = ""
        st.session_state['role'] = ""
        st.session_state['credits'] = 0
        st.session_state['premium_expiry'] = None
        st.session_state['free_uses'] = 0
        st.experimental_rerun()

# 获取所有用户
def get_all_users():
    c.execute("SELECT * FROM users")
    return c.fetchall()

# 受保护内容
def protected_content():
    st.write("這裡是可以上傳PDF檔案並處理的部分")
    uploaded_file = st.file_uploader("上傳PDF文件", type="pdf")
    if uploaded_file is not None:
        # 進度條初始化
        progress_bar = st.progress(0)
        progress_text = st.empty()
        
        images = read_pdf(uploaded_file, progress_bar, progress_text)
        
        st.write("PDF檔案已成功讀取！")
        for idx, image in enumerate(images):
            # 缩放图像以适应画布
            canvas_width = min(image.width, 700)
            scale_ratio = canvas_width / image.width
            scaled_height = int(image.height * scale_ratio)

            st.image(image.resize((canvas_width, scaled_height)), caption=f"第 {idx + 1} 頁", use_column_width=True)

            # Canvas for drawing
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#e00",
                background_image=image.resize((canvas_width, scaled_height)),
                update_streamlit=True,
                height=scaled_height,
                width=canvas_width,
                drawing_mode="rect",
                key=f"canvas_{idx}"
            )

            if canvas_result.json_data["objects"]:
                st.write("您繪製的區域：")
                for obj in canvas_result.json_data["objects"]:
                    left = obj["left"] / scale_ratio
                    top = obj["top"] / scale_ratio
                    width = obj["width"] / scale_ratio
                    height = obj["height"] / scale_ratio

                    cropped_image = image.crop((left, top, left + width, top + height))
                    st.image(cropped_image, caption="選定區域", use_column_width=True)

                    # Perform OCR on cropped image
                    text = perform_ocr(cropped_image)
                    st.write("辨識文字：", text)

                    # Download cropped image
                    buf = io.BytesIO()
                    cropped_image.save(buf, format="PNG")
                    byte_im = buf.getvalue()
                    st.download_button(
                        label=f"下載框選區域 {idx + 1}",
                        data=byte_im,
                        file_name=f"cropped_image_{idx + 1}.png",
                        mime="image/png"
                    )

                    # 检测是否是句子
                    if is_sentence(text):
                        st.success("該區域包含有效的句子")
                    else:
                        st.error("該區域不包含有效的句子")
        
        # 更新免费会员的使用次数
        if st.session_state['membership'] == 'free':
            update_free_uses(st.session_state['username'])
            st.session_state['free_uses'] += 1

# 读取PDF文件并更新进度条
def read_pdf(file, progress_bar, progress_text):
    pdf_document = fitz.open(stream=file.read(), filetype="pdf")
    images = []
    num_pages = len(pdf_document)
    total_images = sum([len(page.get_images(full=True)) for page in pdf_document])
    processed_images = 0

    for page_num in range(num_pages):
        page = pdf_document.load_page(page_num)
        image_list = page.get_images(full=True)
        for img in image_list:
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image = Image.open(io.BytesIO(image_bytes))
            images.append(image)

            processed_images += 1
            progress = int((processed_images / total_images) * 100)
            progress_bar.progress(progress)
            progress_text.text(f"處理進度: {progress}%")
    
    return images

# 执行OCR识别
def perform_ocr(image):
    im = image.filter(ImageFilter.MedianFilter())
    enhancer = ImageEnhance.Contrast(im)
    im = enhancer.enhance(2)
    im = im.convert('1')
    text = pytesseract.image_to_string(im)
    return text

# 检测是否是句子
def is_sentence(text):
    doc_zh = spacy_zh(text)
    doc_en = spacy_en(text)
    return any([sent for sent in doc_zh.sents]) or any([sent for sent in doc_en.sents])

# 添加初始管理员
def add_initial_admin():
    if not validate_signup("admin"):
        create_user("admin", "adminpass", "premium", "admin")

# 验证信用卡号
def validate_card_number(card_number):
    return card_number.isdigit() and len(card_number) in [13, 16, 19]

# 验证到期日
def validate_expiry_date(expiry_date):
    if len(expiry_date) != 5 or expiry_date[2] != '/':
        return False
    month, year = expiry_date.split('/')
    return month.isdigit() and year.isdigit() and 1 <= int(month) <= 12

# 验证CVV
def validate_cvv(cvv):
    return cvv.isdigit() and len(cvv) == 3

# 更新点数
def update_credits(username, amount):
    c.execute("UPDATE users SET credits = credits + ? WHERE username = ?", (amount, username))
    conn.commit()

# 重置所有免费用户的使用次数
def reset_free_uses():
    c.execute("UPDATE users SET free_uses = 0 WHERE membership = 'free'")
    conn.commit()

if __name__ == "__main__":
    add_initial_admin()
    main()
    conn.close()
