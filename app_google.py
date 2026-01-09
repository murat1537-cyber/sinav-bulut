import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import random
import pandas as pd

# --- AYARLAR VE TASARIM ---
st.set_page_config(page_title="Sınav Koçu Pro", layout="wide", page_icon="🎓")

st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
    }
    .big-font {
        font-size:20px !important;
    }
    .hata-kutusu {
        padding: 10px;
        border-radius: 5px;
        background-color: #ffe6e6;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# Dosya İsimleri
SORU_DOSYASI = "sorular_duzeltilmis.json"
TABLO_ADI = "SinavVerileri"

# --- 1. GOOGLE BAĞLANTISI ---
def google_baglan():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("google_key.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open(TABLO_ADI).sheet1
    return sheet

# --- 2. ALGORİTMA ---
def sonraki_tekrar_hesapla(mevcut_interval, performans):
    if performans == 0: return 0
    elif performans == 1: return 1
    else:
        if mevcut_interval == 0: return 1
        elif mevcut_interval == 1: return 3
        elif mevcut_interval == 3: return 7
        elif mevcut_interval == 7: return 21
        else: return mevcut_interval * 2

# --- 3. VERİ YÖNETİMİ ---
@st.cache_data(ttl=60)
def verileri_cek():
    with open(SORU_DOSYASI, 'r', encoding='utf-8') as f:
        ham_sorular = json.load(f)
    try:
        sheet = google_baglan()
        kayitli_veri_str = sheet.acell('A1').value
        kullanici_verisi = json.loads(kayitli_veri_str) if kayitli_veri_str else {}
    except:
        kullanici_verisi = {}
    
    islenmis_sorular = []
    for soru in ham_sorular:
        s_id = str(soru['id'])
        gecmis = kullanici_verisi.get(s_id, {
            "status": "yeni", "interval": 0, "next_review": None, 
            "streak": 0, "attempts": 0, "last_error": None
        })
        soru.update(gecmis)
        islenmis_sorular.append(soru)
    return islenmis_sorular, kullanici_verisi

def ilerlemeyi_kaydet(guncel_veri_dict):
    try:
        sheet = google_baglan()
        sheet.update_acell('A1', json.dumps(guncel_veri_dict))
        verileri_cek.clear()
    except Exception as e:
        st.error(f"Kayıt hatası: {e}")

# --- 4. OTURUM YÖNETİMİ ---
if 'sorular' not in st.session_state:
    st.session_state['sorular'], st.session_state['user_data'] = verileri_cek()
    st.session_state['aktif_soru'] = None
    st.session_state['step'] = 'soru_goster'

# --- 5. İŞLEM FONKSİYONU ---
def cevap_isleme(soru, puan, hata_turu=None):
    yeni_interval = sonraki_tekrar_hesapla(soru['interval'], puan)
    bugun = datetime.date.today()
    sonraki_tarih = bugun + datetime.timedelta(days=yeni_interval)
    
    status = "ogreniliyor"
    streak = soru['streak']
    
    if puan == 2: # Eminim
        streak += 1
        if streak >= 3: status = "master"
        hata_turu = None # Doğru bildiyse hata kaydını temizle (İstersen tutabilirsin)
    elif puan == 0: # Yanlış
        streak = 0
        status = "ogreniliyor"
    
    s_id = str(soru['id'])
    yeni_veri = {
        "status": status,
        "interval": yeni_interval,
        "next_review": str(sonraki_tarih),
        "streak": streak,
        "attempts": soru['attempts'] + 1,
        "last_error": hata_turu if hata_turu else soru['last_error'] # Yeni hata yoksa eskisini koru veya güncelle
    }
    
    # Hata türü temizleme mantığı: Eğer doğru bildiyse 'last_error'u silebiliriz
    # Veya geçmiş hatası kalsın istiyorsan yukarıdaki satırı değiştirmemelisin.
    # Ben temizliyorum ki "Hatalılar" listesinden düşsün.
    if puan == 2:
        yeni_veri["last_error"] = None 

    st.session_state['user_data'][s_id] = yeni_veri
    
    for s in st.session_state['sorular']:
        if str(s['id']) == s_id:
            s.update(yeni_veri)
            break
            
    ilerlemeyi_kaydet(st.session_state['user_data'])
    
    st.session_state['aktif_soru'] = None
    st.session_state['step'] = 'soru_goster'
    st.rerun()

# --- ARAYÜZ ---
st.title("🚀 Sınav Koçu Pro")

tab1, tab2 = st.tabs(["📝 Soru Çözümü", "📊 Analiz ve Hatalar"])

# --- SEKME 1: SORU ÇÖZÜMÜ ---
with tab1:
    if st.session_state['aktif_soru'] is None:
        bugun = datetime.date.today().strftime("%Y-%m-%d")
        havuz = [s for s in st.session_state['sorular'] if s['status'] == 'yeni' or (s['next_review'] and s['next_review'] <= bugun)]
        
        if not havuz:
            st.success("🎉 Harika! Bugünlük programını tamamladın.")
            st.info("Yan sekmeden yanlışlarına göz atabilirsin.")
            st.stop()
        st.session_state['aktif_soru'] = random.choice(havuz)

    soru = st.session_state['aktif_soru']

    with st.container():
        st.markdown(f"#### 🔹 Soru (ID: {soru['id']})")
        st.info(soru['soru'], icon="❓")
        
        if st.session_state['step'] == 'soru_goster':
            with st.form(key='cevap_form'):
                secim = st.radio("Seçenekler:", soru['secenekler'], index=None)
                st.write("")
                submit = st.form_submit_button("Yanıtla ➡️", type="primary")
                
                if submit and secim:
                    st.session_state['verilen_cevap'] = secim
                    st.session_state['dogru_mu'] = (secim == soru['dogru_cevap'])
                    st.session_state['step'] = 'sonuc_goster'
                    st.rerun()

        elif st.session_state['step'] == 'sonuc_goster':
            if st.session_state['dogru_mu']:
                st.success(f"✅ TEBRİKLER! Doğru Cevap: {st.session_state['verilen_cevap']}")
                st.write("**Kendini Değerlendir:**")
                c1, c2 = st.columns(2)
                if c1.button("😎 Eminim", type="primary"): cevap_isleme(soru, 2)
                if c2.button("🤔 Tahmin Ettim"): cevap_isleme(soru, 1)
            else:
                st.error(f"❌ Yanlış. Senin cevabın: {st.session_state['verilen_cevap']}")
                st.warning(f"👉 Doğru Cevap: **{soru['dogru_cevap']}**")
                
                if "aciklama" in soru:
                    with st.expander("ℹ️ Açıklama"):
                        st.write(soru["aciklama"])
                
                st.write("🛑 **Neden Yanlış Yaptın?**")
                h1, h2, h3, h4 = st.columns(4)
                if h1.button("📚 Bilgi Eksiği"): cevap_isleme(soru, 0, "Bilgi Eksiği")
                if h2.button("👀 Dikkat Hatası"): cevap_isleme(soru, 0, "Dikkat Hatası")
                if h3.button("🧠 Yanlış Yorum"): cevap_isleme(soru, 0, "Yanlış Yorum")
                if h4.button("⏳ Diğer"): cevap_isleme(soru, 0, "Diğer")

# --- SEKME 2: ANALİZ VE HATALAR (YENİLENMİŞ KISIM) ---
with tab2:
    st.header("📊 Analiz ve Hata Kütüphanesi")
    
    df = pd.DataFrame(st.session_state['sorular'])
    
    # Metrikler
    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam Soru", len(df))
    col2.metric("Öğrenilen (Master)", len(df[df['status'] == 'master']))
    hatali_sayisi = len(df[df['last_error'].notnull()])
    col3.metric("Düzeltilmesi Gereken Hatalar", hatali_sayisi, delta_color="inverse")
    
    st.markdown("---")
    
    # FİLTRELEME SEÇENEKLERİ
    st.subheader("🔍 Soru İnceleme")
    filtre = st.radio(
        "Hangi soruları listelemek istersin?",
        ["Sadece Yanlış Yaptıklarım (Hatalılar)", "Tüm Sorular", "Öğrendiklerim (Master)"],
        horizontal=True
    )
    
    if filtre == "Sadece Yanlış Yaptıklarım (Hatalılar)":
        # Hata kaydı olanları filtrele
        hatali_df = df[df['last_error'].notnull()]
        
        if hatali_df.empty:
            st.success("Harika! Şu an sistemde kayıtlı 'düzeltilmemiş' bir hatan yok.")
        else:
            st.warning(f"Toplam {len(hatali_df)} adet hatalı veya eksik olduğun soru var.")
            
            # Tabloyu göster ama okunabilir sütunları seç
            # HTML render ile tabloyu daha şık yapabiliriz ama şimdilik standart dataframe
            st.dataframe(
                hatali_df[['id', 'soru', 'dogru_cevap', 'last_error']],
                hide_index=True,
                use_container_width=True
            )
            
            st.markdown("### 📝 Hata Detayları")
            # Hataları tek tek kart olarak gösterme opsiyonu
            for index, row in hatali_df.iterrows():
                with st.expander(f"🔴 Soru {row['id']} - Hata Sebebi: {row['last_error']}"):
                    st.write(f"**Soru:** {row['soru']}")
                    st.success(f"**Doğru Cevap:** {row['dogru_cevap']}")
                    st.caption("Bu soruyu tekrar çözdüğünde ve 'Eminim' dediğinde listeden kalkacak.")

    elif filtre == "Öğrendiklerim (Master)":
        master_df = df[df['status'] == 'master']
        st.success(f"🏆 Toplam {len(master_df)} soruda ustalaştın!")
        st.dataframe(master_df[['id', 'soru', 'streak']], hide_index=True, use_container_width=True)

    else: # Tüm Sorular
        st.dataframe(df[['id', 'soru', 'status', 'last_error']], hide_index=True, use_container_width=True)