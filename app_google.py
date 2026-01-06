import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# --- AYARLAR ---
st.set_page_config(page_title="Bulut Sınav Asistanı", layout="centered")

SORU_DOSYASI = "sorular_duzeltilmis.json" # Senin soru dosyanın adı
ANAHTAR_DOSYASI = "google_key.json"       # İndirdiğin anahtar dosya
TABLO_ADI = "SinavVerileri"               # Google Sheet adı

# --- GOOGLE BAĞLANTISI ---
def google_baglan():
    # Streamlit Cloud'a yükleyince şifreleri "Secrets" bölümünden alacağız.
    # Bu yapı hem bilgisayarında (secrets.toml dosyası varsa) hem bulutta çalışır.
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # st.secrets kullanarak bilgileri alıyoruz
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open(TABLO_ADI).sheet1
    return sheet

# --- VERİ YÖNETİMİ ---
def sorulari_yukle():
    if os.path.exists(SORU_DOSYASI):
        with open(SORU_DOSYASI, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def buluta_kaydet():
    # Kaydedilecek verileri hazırla
    veri = {
        'aktif_soru_index': st.session_state['aktif_soru_index'],
        'puan': st.session_state['puan'],
        'yanlislar': st.session_state['yanlislar'],
        'sinav_bitti': st.session_state['sinav_bitti']
        # Soruların sırasını kaydetmiyoruz yer kaplamasın diye, 
        # gerekirse onu da ekleyebiliriz ama Google Sheet hücresi dolabilir.
    }
    try:
        sheet = google_baglan()
        # Veriyi metne (JSON string) çevirip A1 hücresine yaz
        sheet.update_acell('A1', json.dumps(veri))
        # Başarılı olduğunu göstermek için sağ altta ufak uyarı (opsiyonel)
        # st.toast("Buluta kaydedildi!", icon="☁️")
    except Exception as e:
        st.error(f"Kayıt Hatası: {e}")

def buluttan_yukle():
    try:
        sheet = google_baglan()
        veri_str = sheet.acell('A1').value
        if veri_str:
            return json.loads(veri_str)
    except Exception as e:
        st.warning("Buluttan veri çekilemedi veya dosya boş.")
    return None

# --- BAŞLANGIÇ ---
if 'baslatildi' not in st.session_state:
    st.session_state['baslatildi'] = False

if not st.session_state['baslatildi']:
    st.title("☁️ Google Drive Sınav Botu")
    
    col1, col2 = st.columns(2)
    
    if col1.button("Buluttan Devam Et (Drive)"):
        kayit = buluttan_yukle()
        if kayit:
            st.session_state['aktif_soru_index'] = kayit['aktif_soru_index']
            st.session_state['puan'] = kayit['puan']
            st.session_state['yanlislar'] = kayit['yanlislar']
            st.session_state['sinav_bitti'] = kayit['sinav_bitti']
            st.session_state['sorular'] = sorulari_yukle() # Soruları yerel dosyadan al
            # Not: Soruları karıştırmıyoruz ki index kaymasın. 
            # Eğer karıştıracaksak soru sırasını da drive'a kaydetmek gerekir.
            st.session_state['baslatildi'] = True
            st.rerun()
        else:
            st.error("Drive'da kayıt bulunamadı.")

    if col2.button("Sıfırdan Başla"):
        st.session_state['sorular'] = sorulari_yukle()
        st.session_state['aktif_soru_index'] = 0
        st.session_state['puan'] = 0
        st.session_state['yanlislar'] = []
        st.session_state['sinav_bitti'] = False
        st.session_state['baslatildi'] = True
        buluta_kaydet() # Başlangıç durumunu kaydet
        st.rerun()

    st.stop()

# --- ANA AKIŞ ---
# (Burası eski kodun aynısı, sadece kaydetme fonksiyonu değişti)

soru_listesi = st.session_state['sorular']
index = st.session_state['aktif_soru_index']

if not st.session_state['sinav_bitti']:
    soru = soru_listesi[index]
    
    st.progress((index + 1) / len(soru_listesi))
    st.write(f"Soru {index + 1} / {len(soru_listesi)}")
    st.markdown(f"### {soru['soru']}")
    
    with st.form(key=f"form_{index}"):
        secim = st.radio("Seçenekler:", soru['secenekler'], index=None)
        btn = st.form_submit_button("Yanıtla")
        
    if btn:
        if secim:
            if secim == soru['dogru_cevap']:
                st.success("Doğru!")
                st.session_state['puan'] += 1
            else:
                st.error(f"Yanlış! Doğru cevap: {soru['dogru_cevap']}")
                st.session_state['yanlislar'].append(soru)
            
            # Soru bitince ilerle
            if index < len(soru_listesi) - 1:
                st.session_state['aktif_soru_index'] += 1
            else:
                st.session_state['sinav_bitti'] = True
            
            # HER CEVAPTA BULUTA KAYDET
            buluta_kaydet()
            st.rerun()
        else:
            st.warning("Seçim yapmadınız.")
else:
    st.balloons()
    st.write(f"Bitti! Puan: {st.session_state['puan']}")
    if st.button("Başa Dön"):
        st.session_state['baslatildi'] = False
        st.rerun()