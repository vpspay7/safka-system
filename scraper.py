import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import json
import re
import requests
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true

# ====================================================
# --- إعدادات الربط (بيتم جلبها من Secrets جيت هاب) ---
# ====================================================
# التوكن والشات أيدي بتوعك أهم
TELEGRAM_TOKEN = "8751548132:AAGy_SOrb5M1w3L8pcal5Gkd5pQTyOFQ3U8"
TELEGRAM_CHAT_ID = "6117378583"

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
    """الاتصال بجوجل شيت باستخدام المفتاح السري"""
    try:
        creds_json = os.environ.get("GCP_KEY")
        creds_dict = json.loads(creds_json)
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        # تأكد إن اسم الشيت في جوجل هو Safka_Trend_Hunter
        return client.open("Safka_Trend_Hunter")
    except Exception as e:
        print(f"❌ خطأ في الاتصال بجوجل شيت: {e}")
        return None

def login_to_safka(driver):
    """تسجيل دخول أوتوماتيكي لموقع صفقة"""
    print("🔐 جاري تسجيل الدخول لموقع صفقة...")
    driver.get("https://aff.safka-eg.com/login")
    time.sleep(3)
    
    email = os.environ.get("SAFKA_EMAIL")
    password = os.environ.get("SAFKA_PASSWORD")
    
    try:
        # البحث عن حقول الإدخال وإرسال البيانات
        driver.find_element(By.NAME, "email").send_keys(email)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(5)
        print("✅ تم تسجيل الدخول بنجاح!")
    except Exception as e:
        print(f"❌ فشل تسجيل الدخول: {e}")

def scan_all_pages():
    print(f"🚀 بدء الفحص الشامل | الوقت: {datetime.now().strftime('%I:%M:%S %p')}")
    
    # إعدادات المتصفح المخفي (Headless) للعمل على سيرفر جيت هاب
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    login_to_safka(driver)

    all_current_data = []
    page = 1
    
    while True:
        url = f"https://aff.safka-eg.com/products/available_products?page={page}"
        driver.get(url)
        time.sleep(4) 
        
        cards = driver.find_elements(By.CSS_SELECTOR, "div[data-product-id]")
        
        if not cards:
            break
            
        print(f"📄 فحص الصفحة [{page}]... تم رصد {len(cards)} منتج")
        
        for card in cards:
            try:
                name = card.find_element(By.CSS_SELECTOR, "h3 a").text
                qty_text = card.find_element(By.XPATH, ".//span[contains(text(), 'الكمية:')]/following-sibling::span").text
                qty = clean_number(qty_text)
                all_current_data.append({'name': name, 'qty': qty})
            except:
                continue
        page += 1
    
    driver.quit()

    # --- المقارنة وحفظ البيانات في جوجل شيت بدل الـ CSV ---
    if all_current_data:
        df_new = pd.DataFrame(all_current_data)
        sheet = get_google_sheet()
        
        if sheet:
            ws_last = sheet.worksheet("Last_Scan")
            ws_sales = sheet.worksheet("Sales_History")
            
            old_records = ws_last.get_all_records()
            if old_records:
                df_old = pd.DataFrame(old_records)
                merged = pd.merge(df_new, df_old, on='name', suffixes=('_new', '_old'))
                sales = merged[merged['qty_new'] < merged['qty_old']].copy()
                
                if not sales.empty:
                    for _, row in sales.iterrows():
                        sold_qty = row['qty_old'] - row['qty_new']
                        msg = (f"🛍️ سحب منتج!\n📦 المنتج: {row['name']}\n📉 سحب: {sold_qty} قطعة\n✅ المخزون الحالي: {row['qty_new']}")
                        send_telegram_msg(msg)
                        ws_sales.append_row([str(datetime.now()), row['name'], int(sold_qty), int(row['qty_new'])])
            
            # تحديث الحالة الحالية
            ws_last.clear()
            ws_last.update([df_new.columns.values.tolist()] + df_new.values.tolist())
            print(f"💾 تم تحديث جوجل شيت بنجاح.")

if __name__ == "__main__":
    scan_all_pages() # شلنا الـ While True عشان جيت هاب هو اللي بيكرر التشغيل
