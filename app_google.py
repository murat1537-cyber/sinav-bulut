import streamlit as st
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import random
import pandas as pd # Veri analizi ve grafikler için

# --- AYARLAR VE TASARIM ---
st.set_page_config(page_title="Sınav Koçu Pro", layout="wide", page_icon="🎓")

# Özel CSS ile biraz makyaj yapalım
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
@st.cache_data(ttl=60) # Verileri 1 dakika önbellekte tut ki hızlansın
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
        verileri_cek.clear() # Kayıt yapınca önbelleği temizle
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
        "last_error": hata_turu
    }
    
    # Session ve Drive güncelle
    st.session_state['user_data'][s_id] = yeni_veri
    
    # Sorular listesini de güncelle (Anlık grafik için)
    for s in st.session_state['sorular']:
        if str(s['id']) == s_id:
            s.update(yeni_veri)
            break
            
    ilerlemeyi_kaydet(st.session_state['user_data'])
    
    st.session_state['aktif_soru'] = None
    st.session_state['step'] = 'soru_goster'
    st.rerun()

# --- ARAYÜZ (TABS SİSTEMİ) ---
st.title("🚀 Sınav Koçu Pro")

tab1, tab2 = st.tabs(["📝 Soru Çözümü", "📊 Analiz ve Raporlar"])

# --- SEKME 1: SORU ÇÖZÜMÜ ---
with tab1:
    # Soru Seçme
    if st.session_state['aktif_soru'] is None:
        bugun = datetime.date.today().strftime("%Y-%m-%d")
        havuz = [s for s in st.session_state['sorular'] if s['status'] == 'yeni' or (s['next_review'] and s['next_review'] <= bugun)]
        
        if not havuz:
            st.success("🎉 Harika! Bugünlük programını tamamladın.")
            st.info("İstersen 'Analiz' sekmesinden durumuna bakabilirsin.")
            st.stop()
        st.session_state['aktif_soru'] = random.choice(havuz)

    soru = st.session_state['aktif_soru']

    # Modern Soru Kartı Tasarımı
    with st.container():
        st.markdown(f"#### 🔹 Soru (ID: {soru['id']})")
        st.info(soru['soru'], icon="❓")
        
        if st.session_state['step'] == 'soru_goster':
            with st.form(key='cevap_form'):
                secim = st.radio("Doğru seçenek hangisi?", soru['secenekler'], index=None)
                st.write("")
                col_sub1, col_sub2 = st.columns([1, 4])
                with col_sub1:
                    submit = st.form_submit_button("Yanıtla ➡️", use_container_width=True)
                
                if submit and secim:
                    st.session_state['verilen_cevap'] = secim
                    st.session_state['dogru_mu'] = (secim == soru['dogru_cevap'])
                    st.session_state['step'] = 'sonuc_goster'
                    st.rerun()

        # SONUÇ EKRANI VE BUTONLAR
        elif st.session_state['step'] == 'sonuc_goster':
            if st.session_state['dogru_mu']:
                st.success(f"✅ TEBRİKLER! Doğru Cevap: {st.session_state['verilen_cevap']}")
                st.markdown("---")
                st.write("**Bu soruyu ne kadar iyi biliyorsun?**")
                c1, c2 = st.columns(2)
                if c1.button("😎 Eminim (Tam Öğrendim)", type="primary"):
                    cevap_isleme(soru, 2)
                if c2.button("🤔 Tahmin Ettim / Şans"):
                    cevap_isleme(soru, 1)
            else:
                st.error(f"❌ Maalesef Yanlış. Senin cevabın: {st.session_state['verilen_cevap']}")
                st.warning(f"👉 Doğru Cevap: **{soru['dogru_cevap']}**")
                
                if "aciklama" in soru:
                    with st.expander("ℹ️ Neden Yanlış? (Açıklama)"):
                        st.write(soru["aciklama"])
                
                st.markdown("---")
                st.write("🛑 **Hata Analizi: Neden Yanlış Yaptın? (Seç ve İlerle)**")
                
                # Hata butonları artık direkt işlemi bitiriyor
                h1, h2, h3, h4 = st.columns(4)
                if h1.button("📚 Bilgi Eksiği"): cevap_isleme(soru, 0, "Bilgi Eksiği")
                if h2.button("👀 Dikkat Hatası"): cevap_isleme(soru, 0, "Dikkat Hatası")
                if h3.button("🧠 Yanlış Yorum"): cevap_isleme(soru, 0, "Yanlış Yorum")
                if h4.button("⏳ Süre / Diğer"): cevap_isleme(soru, 0, "Diğer")

# --- SEKME 2: ANALİZ VE RAPORLAR ---
with tab2:
    st.header("📊 Performans Analizin")
    
    # Veriyi Pandas DataFrame'e çevir (Analiz için çok güçlüdür)
    df = pd.DataFrame(st.session_state['sorular'])
    
    # 1. Genel Durum Metrikleri
    total = len(df)
    master = len(df[df['status'] == 'master'])
    learning = len(df[df['status'] == 'ogreniliyor'])
    new = len(df[df['status'] == 'yeni'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Toplam Soru", total)
    col2.metric("Ustalaşılan (Master)", master, delta=f"%{(master/total)*100:.1f}")
    col3.metric("Çalışılan / Riskli", learning)
    
    st.markdown("---")
    
    # 2. Grafikler Yan Yana
    g_col1, g_col2 = st.columns(2)
    
    with g_col1:
        st.subheader("📈 Öğrenme Durumu")
        # Basit bir bar chart
        chart_data = pd.DataFrame({
            'Durum': ['Yeni', 'Öğreniliyor', 'Master'],
            'Soru Sayısı': [new, learning, master]
        }).set_index('Durum')
        st.bar_chart(chart_data, color=["#FF6C6C"]) # Kırmızı tonu
        
    with g_col2:
        st.subheader("🛑 Hata Türleri Analizi")
        # Sadece hatası olanları filtrele
        errors = df[df['last_error'].notnull()]['last_error'].value_counts()
        
        if not errors.empty:
            st.bar_chart(errors)
            st.caption("En çok hangi hatayı yapıyorsan ona odaklanmalısın!")
        else:
            st.info("Henüz yeterince hata verisi oluşmadı.")
            
    # 3. Detaylı Liste (İsteğe bağlı)
    with st.expander("📋 Detaylı Soru Listesi (Tüm Veriler)"):
        st.dataframe(df[['id', 'soru', 'status', 'streak', 'last_error']])