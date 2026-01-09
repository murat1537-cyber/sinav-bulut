import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import random
import time

# --- AYARLAR ---
st.set_page_config(page_title="Pro Sınav Koçu", layout="wide")

# Dosya İsimleri
SORU_DOSYASI = "sorular_duzeltilmis.json"
TABLO_ADI = "SinavVerileri"

# --- 1. GOOGLE BAĞLANTISI ---
def google_baglan():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Secrets yoksa yerel dosyadan, varsa secrets'tan oku
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", scope)
    
    client = gspread.authorize(creds)
    sheet = client.open(TABLO_ADI).sheet1
    return sheet

# --- 2. ALGORİTMA (SPACED REPETITION) ---
def tarih_farki_hesapla(son_tarih_str):
    if not son_tarih_str:
        return 999 # Yeni soru
    son = datetime.datetime.strptime(son_tarih_str, "%Y-%m-%d").date()
    bugun = datetime.date.today()
    return (bugun - son).days

def sonraki_tekrar_hesapla(mevcut_interval, performans):
    # Performans: 0 (Bilmiyordum/Yanlış), 1 (Tahmin/Tereddüt), 2 (Eminim)
    
    if performans == 0:
        return 0 # Yarın tekrar sor (Interval sıfırlandı)
    elif performans == 1:
        return 1 # 1 gün sonra sor (Öğrenildi ama pekişmedi)
    else:
        # SuperMemo-2 benzeri basit mantık: Aralığı genişlet
        if mevcut_interval == 0: return 1
        elif mevcut_interval == 1: return 3
        elif mevcut_interval == 3: return 7
        elif mevcut_interval == 7: return 21
        else: return mevcut_interval * 2 # 21'den sonra katlanarak git

# --- 3. VERİ YÖNETİMİ ---
def verileri_hazirla():
    # 1. Ham soruları yükle
    with open(SORU_DOSYASI, 'r', encoding='utf-8') as f:
        ham_sorular = json.load(f)
    
    # 2. Kullanıcı ilerlemesini Google'dan çek
    try:
        sheet = google_baglan()
        kayitli_veri_str = sheet.acell('A1').value
        kullanici_verisi = json.loads(kayitli_veri_str) if kayitli_veri_str else {}
    except:
        kullanici_verisi = {}

    # 3. Verileri Birleştir (ID bazlı eşleştirme)
    islenmis_sorular = []
    
    for soru in ham_sorular:
        s_id = str(soru['id'])
        
        # Kullanıcı geçmişi varsa al, yoksa varsayılan oluştur
        gecmis = kullanici_verisi.get(s_id, {
            "status": "yeni", # yeni, ogreniliyor, master
            "interval": 0,    # Kaç gün ara verilecek
            "next_review": None, # Hangi tarihte sorulacak
            "streak": 0,      # Üst üste doğru sayısı
            "attempts": 0,     # Toplam deneme
            "last_error": None # Hata türü
        })
        
        # Soru objesine geçmişi ekle
        soru.update(gecmis)
        islenmis_sorular.append(soru)
        
    return islenmis_sorular, kullanici_verisi

def ilerlemeyi_kaydet(guncel_veri_dict):
    try:
        sheet = google_baglan()
        sheet.update_acell('A1', json.dumps(guncel_veri_dict))
    except Exception as e:
        st.error(f"Kayıt hatası: {e}")

# --- 4. OTURUM YÖNETİMİ (SESSION STATE) ---
if 'sorular' not in st.session_state:
    st.session_state['sorular'], st.session_state['user_data'] = verileri_hazirla()
    st.session_state['aktif_soru'] = None
    st.session_state['step'] = 'soru_goster' # Adımlar: soru_goster -> sonuc_goster -> analiz
    
# --- 5. SORU SEÇME MOTORU ---
def soru_getir():
    # Bugün çözülmesi gerekenleri filtrele
    bugun = datetime.date.today().strftime("%Y-%m-%d")
    havuz = []
    
    for s in st.session_state['sorular']:
        # 1. Hiç çözülmemişler (Yeni)
        if s['status'] == 'yeni':
            havuz.append(s)
        # 2. Tekrar zamanı gelmiş olanlar
        elif s['next_review'] and s['next_review'] <= bugun:
            havuz.append(s)
            
    if not havuz:
        return None
    
    # Öncelik: Önce tekrarlar, sonra yeniler
    # Karıştırıp bir tane seç
    return random.choice(havuz)

# --- ARAYÜZ ---
st.title("🧠 Pro Sınav Koçu")

# İstatistik Paneli (Sidebar)
if st.session_state['sorular']:
    total = len(st.session_state['sorular'])
    mastered = sum(1 for s in st.session_state['sorular'] if s['status'] == 'master')
    learning = sum(1 for s in st.session_state['sorular'] if s['status'] == 'ogreniliyor')
    new = sum(1 for s in st.session_state['sorular'] if s['status'] == 'yeni')
    
    with st.sidebar:
        st.header("📊 Gelişim Haritası")
        st.metric("Öğrenilen (Master)", f"{mastered}", delta=f"%{(mastered/total)*100:.1f}")
        st.metric("Riskli / Öğreniliyor", f"{learning}")
        st.progress(mastered / total)
        st.info("Algoritma: Spaced Repetition (SM-2)")

# --- ANA AKIŞ ---

# Yeni Soru Seçimi
if st.session_state['aktif_soru'] is None:
    secilen = soru_getir()
    if secilen:
        st.session_state['aktif_soru'] = secilen
        st.session_state['step'] = 'soru_goster'
    else:
        st.success("🎉 Tebrikler! Bugünlük tekrar etmen gereken tüm sorular bitti.")
        st.balloons()
        st.stop()

soru = st.session_state['aktif_soru']

# ADIM 1: SORUYU GÖSTER
if st.session_state['step'] == 'soru_goster':
    st.markdown(f"### {soru['soru']}")
    st.info(f"📅 Bu soruyu en son {soru.get('next_review', 'hiç')} tarihinde görmeliydin.")
    
    with st.form(key='cevap_form'):
        kullanici_cevabi = st.radio("Cevabınız:", soru['secenekler'], index=None)
        submitted = st.form_submit_button("Yanıtla")
        
        if submitted and kullanici_cevabi:
            st.session_state['verilen_cevap'] = kullanici_cevabi
            st.session_state['dogru_mu'] = (kullanici_cevabi == soru['dogru_cevap'])
            st.session_state['step'] = 'sonuc_goster'
            st.rerun()

# ADIM 2: SONUCU VE ANALİZİ GÖSTER
elif st.session_state['step'] == 'sonuc_goster':
    st.markdown(f"### {soru['soru']}")
    
    # Cevap Kontrolü
    if st.session_state['dogru_mu']:
        st.success(f"✅ Doğru! (Cevabın: {st.session_state['verilen_cevap']})")
    else:
        st.error(f"❌ Yanlış! Senin cevabın: {st.session_state['verilen_cevap']}")
        st.info(f"👉 Doğru Cevap: **{soru['dogru_cevap']}**")
        
        # Hata Türü Analizi (Sadece yanlışsa sorulur)
        st.write("---")
        st.write("🛑 **Hata Analizi:** Neden yanlış yaptın?")
        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        if col_h1.button("Bilgi Eksiği"): st.session_state['hata_turu'] = "bilgi_eksigi"
        if col_h2.button("Dikkat Hatası"): st.session_state['hata_turu'] = "dikkat"
        if col_h3.button("Yanlış Yorum"): st.session_state['hata_turu'] = "yorum"
        if col_h4.button("Süre Baskısı"): st.session_state['hata_turu'] = "sure"

    # Mikro Öğrenme (Açıklama varsa göster)
    if "aciklama" in soru:
        with st.expander("ℹ️ Detaylı Açıklama (Neden?)", expanded=True):
            st.write(soru["aciklama"])
    else:
        with st.expander("ℹ️ Detaylı Açıklama"):
            st.write("Bu soru için henüz özel açıklama girilmemiş.")

    st.write("---")
    st.subheader("🤔 Kendini Değerlendir (Algoritma için gerekli)")
    
    col1, col2, col3 = st.columns(3)
    
    # Butonlar ve SRS Algoritması Tetikleme
    puan = -1
    if st.session_state['dogru_mu']:
        # Doğruysa 2 seçenek var: Eminim veya Tahmin Ettim
        if col1.button("✅ Eminim (Tam Öğrendim)"):
            puan = 2
        if col2.button("🤔 Tahmin Ettim / Tereddüt"):
            puan = 1
    else:
        # Yanlışsa tek yol var
        if col3.button("❌ Bilmiyordum / Yanlış Hatırladım"):
            puan = 0
            
    # Eğer bir butona basıldıysa kaydet ve ilerle
    if puan != -1:
        # 1. Yeni intervali hesapla
        yeni_interval = sonraki_tekrar_hesapla(soru['interval'], puan)
        
        # 2. Tarihi belirle
        bugun = datetime.date.today()
        sonraki_tarih = bugun + datetime.timedelta(days=yeni_interval)
        
        # 3. Status güncelle
        status = "ogreniliyor"
        streak = soru['streak']
        
        if puan == 2: # Eminim
            streak += 1
            if streak >= 3: status = "master" # Kural: 3 kere üst üste "Eminim"
        elif puan == 0: # Yanlış
            streak = 0
            status = "ogreniliyor" # Yanlış yapınca master düşer
            
        # 4. Dictionary güncelle
        s_id = str(soru['id'])
        yeni_veri = {
            "status": status,
            "interval": yeni_interval,
            "next_review": str(sonraki_tarih),
            "streak": streak,
            "attempts": soru['attempts'] + 1,
            "last_error": st.session_state.get('hata_turu', None)
        }
        
        # Session state güncelle (Anlık yansıması için)
        soru.update(yeni_veri)
        
        # Google Sheet için veri hazırla
        st.session_state['user_data'][s_id] = yeni_veri
        
        # Buluta Kaydet
        ilerlemeyi_kaydet(st.session_state['user_data'])
        
        # Sıradaki soruya geç
        st.session_state['aktif_soru'] = None
        st.session_state['step'] = 'soru_goster'
        st.rerun()