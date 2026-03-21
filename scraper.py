import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import json
import re
import requests
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ====================================================
# --- الإعدادات (التليجرام وجوجل شيت) ---
# ====================================================
TELEGRAM_TOKEN = "8751548132:AAGy_SOrb5M1w3L8pcal5Gkd5pQTyOFQ3U8"
TELEGRAM_CHAT_ID = "6117378583"

# اسم الجوجل شيت بتاعك (لازم تكون مشيره مع إيميل الـ Service Account)
GOOGLE_SHEET_NAME = "Safka_Trend_Hunter" 

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ خطأ في إرسال التليجرام: {e}")

def clean_number(text):
    num = re.findall(r'\d+', text.replace(',', ''))
    return int(num[0]) if num else 0

def get_google_sheet():
    """الاتصال بجوجل شيت لجلب وحفظ البيانات"""
    try:
        creds_json = os.environ.get("GCP_KEY")
        creds_dict = json.loads(creds_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open(GOOGLE_SHEET_NAME)
    except Exception as e:
        print(f"❌ خطأ في الاتصال بجوجل شيت: {e}")
        return None

def login_to_safka(driver):
    """دالة جديدة لتسجيل الدخول أوتوماتيكياً في سيرفر جيت هاب"""
    print("🔐 جاري تسجيل الدخول لموقع صفقة...")
    driver.get("https://aff.safka-eg.com/login") # تأكد من رابط تسجيل الدخول
    time.sleep(3)
    
    # هنجيب الإيميل والباسورد من إعدادات الأمان في جيت هاب
    email = os.environ.get("SAFKA_EMAIL")
    password = os.environ.get("SAFKA_PASSWORD")
    
    try:
        # !!! تنبيه: لازم تتأكد من الـ CSS Selectors دي من موقع صفقة !!!
        driver.find_element(By.CSS_SELECTOR, "input[type='email']").send_keys(email)
        driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)
        print("✅ تم تسجيل الدخول بنجاح!")
    except Exception as e:
        print(f"❌ فشل تسجيل الدخول: {e}")

def scan_all_pages():
    print(f"🚀 بدء الفحص الشامل | الوقت: {datetime.now().strftime('%I:%M:%S %p')}")
    
    # --- إعدادات الكروم المخفي (Headless) لجيت هاب ---
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("window-size=1920,1080")
    
    driver = webdriver.Chrome(options=options)
    
    # 1. تسجيل الدخول أولاً
    login_to_safka(driver)

    all_current_data = []
    page = 1
    
    while True:
        url = f"https://aff.safka-eg.com/products/available_products?page={page}"
        driver.get(url)
        time.sleep(3) 
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        cards = driver.find_elements(By.CSS_SELECTOR, "div[data-product-id]")
        
        if not cards:
            break
            
        print(f"📄 فحص الصفحة [{page}]... تم رصد {len(cards)} منتج")
        
        for card in cards:
            try:
                name = card.find_element(By.CSS_SELECTOR, "h3 a").text
                qty_text = card.find_element(By.XPATH, ".//span[contains(text(), 'الكمية:')]/following-sibling::span").text
                qty = clean_number(qty_text)
                
                all_current_data.append({
                    'name': name, 
                    'qty': qty, 
                    'time': datetime.now().strftime('%H:%M:%S')
                })
            except:
                continue
        page += 1
    
    driver.quit()

    # --- معالجة البيانات مع Google Sheets ---
    if all_current_data:
        df_new = pd.DataFrame(all_current_data)
        sheet = get_google_sheet()
        
        if sheet:
            try:
                worksheet_last_scan = sheet.worksheet("Last_Scan")
                worksheet_sales = sheet.worksheet("Sales_History")
                
                # جلب البيانات القديمة
                old_records = worksheet_last_scan.get_all_records()
                
                if old_records:
                    df_old = pd.DataFrame(old_records)
                    merged = pd.merge(df_new, df_old, on='name', suffixes=('_new', '_old'))
                    sales = merged[merged['qty_new'] < merged['qty_old']].copy()
                    
                    if not sales.empty:
                        print(f"🔥 رصد {len(sales)} عمليات سحب جديدة!")
                        for _, row in sales.iterrows():
                            sold_qty = row['qty_old'] - row['qty_new']
                            msg = (f"🛍️ سحب منتج!\n"
                                   f"📦 المنتج: {row['name']}\n"
                                   f"📉 سحب: {sold_qty} قطعة\n"
                                   f"✅ المخزون الحالي: {row['qty_new']}")
                            
                            send_telegram_msg(msg)
                            
                            # تسجيل المبيعة في شيت المبيعات
                            worksheet_sales.append_row([str(datetime.now()), row['name'], int(sold_qty), int(row['qty_new'])])
                
                # مسح البيانات القديمة وتحديثها بالجديدة
                worksheet_last_scan.clear()
                worksheet_last_scan.update([df_new.columns.values.tolist()] + df_new.values.tolist())
                print(f"💾 تم تحديث جوجل شيت. إجمالي المنتجات: {len(df_new)}")
                
            except Exception as e:
                print(f"⚠️ مشكلة في تحديث جوجل شيت: {e}")

if __name__ == "__main__":
    scan_all_pages()
    # شلنا الـ While True لأن جيت هاب هو اللي هيشغله
