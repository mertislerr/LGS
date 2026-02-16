import os
from datetime import datetime
from fastapi import FastAPI, Request, Response
from supabase import create_client, Client
from groq import Groq
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv

load_dotenv()

# Bağlantılar
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
t_client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

app = FastAPI()
hafıza = {}

# --- BİLGİSAYARCI SİSTEM TALİMATI (TELEFON YOK) ---
SISTEM_TALIMATI = """
Sen profesyonel bir Bilgisayar ve Teknoloji Mağazası asistanısın. 
Abinin dükkanında 2. El ve Sıfır bilgisayar, parça, konsol alıp satılıyor.

HİZMET KAPSAMIMIZ:
✅ EVET: Masaüstü/Dizüstü Oyuncu Bilgisayarları, Ekran Kartı, İşlemci, RAM, Anakart, Monitör, Klavye/Mouse, PlayStation, Xbox.
❌ HAYIR: Telefon (Cep telefonu), Tablet veya Beyaz Eşya alım-satımımız YOKTUR.

KURALLARIN:
1. **TELEFON SORULARINA CEVAP:** Eğer müşteri telefon (iPhone, Samsung vb.) satmak veya almak isterse: "Maalesef biz sadece bilgisayar ve konsol üzerine çalışıyoruz, telefon ticaretimiz yok hocam" de.
2. **2. EL BİLGİSAYAR/KONSOL ALIMI:** Müşteri PC veya Konsol satmak isterse şu detayları sor:
   - "Kozmetik durumu nasıl? Çizik, kırık var mı?"
   - "Tamir gördü mü? Güvenlik etiketi duruyor mu?"
   - "Kutusu ve faturası mevcut mu?"
   - Sonra: "Hocam cihazı dükkana getirip test etmemiz lazım, net fiyatı testten sonra veririz" de. Asla telefonda kesin fiyat verme.
3. **SATIŞ & TOPLAMA:** PC toplamak isteyenin bütçesini ve oynayacağı oyunları sor (Valorant mı oynayacak, Cyberpunk mı?).

KAYIT FORMATI:
Müşteriyle anlaşırsan (Dükkana gelecekse veya ürün sorduysa):
KAYIT_PC: [Müşteri Adı], [İşlem Tipi (Alış/Satış/Tamir)], [Ürün Detayı]
"""

@app.post("/whatsapp")
async def whatsapp_reply(request: Request):
    form_data = await request.form()
    gelen_mesaj = form_data.get('Body', '')
    gonderen = form_data.get('From', '')
    bugun = datetime.now().strftime("%Y-%m-%d")

    # --- CRM: Müşteriyi Tanı ---
    # Not: Abinin dükkanı için 'bilgisayar_talepleri' tablosunu kullandığından emin ol.
    gecmis_sorgu = supabase.table("bilgisayar_talepleri").select("musteri_adi, urun_detayi")\
        .eq("musteri_no", gonderen).order("created_at", desc=True).limit(1).execute()
    
    isim = None
    gecmis_bilgi = "Yeni Müşteri"
    
    if gecmis_sorgu.data:
        isim = gecmis_sorgu.data[0]['musteri_adi']
        gecmis_bilgi = f"Daha önce {gecmis_sorgu.data[0]['urun_detayi']} sormuş/işlem yapmış."

    crm_notu = f"Müşteri Adı: {isim if isim else 'Bilinmiyor (İsmini öğren)'}. CRM Geçmişi: {gecmis_bilgi}"

    # Hafıza Yönetimi
    if gonderen not in hafıza: hafıza[gonderen] = []
    mesaj_gecmisi = [{"role": "system", "content": f"{SISTEM_TALIMATI}\nBugün: {bugun}\nCRM BİLGİSİ: {crm_notu}"}]
    
    for m in hafıza[gonderen][-5:]: mesaj_gecmisi.append(m)
    mesaj_gecmisi.append({"role": "user", "content": gelen_mesaj})

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=mesaj_gecmisi,
            temperature=0.3 # Esnaf ciddiyeti için düşük tutuyoruz
        )
        ai_cevabi = completion.choices[0].message.content

        # --- VERİTABANI KAYDI ---
        if "KAYIT_PC:" in ai_cevabi:
            parcalar = ai_cevabi.split("KAYIT_PC:")[1].split(",")
            # Hata önleyici kontrol
            if len(parcalar) >= 3:
                k_isim = parcalar[0].strip()
                k_tip = parcalar[1].strip()
                k_urun = parcalar[2].strip()
                
                # Tablo adının 'bilgisayar_talepleri' olduğundan emin ol (önceki adımda oluşturmuştuk)
                supabase.table("bilgisayar_talepleri").insert({
                    "musteri_no": gonderen,
                    "musteri_adi": k_isim,
                    "islem_tipi": k_tip,
                    "urun_detayi": k_urun,
                    "notlar": "WhatsApp Asistanı"
                }).execute()
                
                # AI cevabından kod kısmını temizle
                ai_cevabi = ai_cevabi.split("KAYIT_PC:")[0].strip() + "\n\n✅ Notumu aldım, dükkana bekliyoruz hocam."

        hafıza[gonderen].append({"role": "user", "content": gelen_mesaj})
        hafıza[gonderen].append({"role": "assistant", "content": ai_cevabi})
        
    except Exception as e:
        ai_cevabi = "Hocam sisteme bakıyorum, 1 dakika sonra tekrar yazar mısın?"

    return Response(content=f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{ai_cevabi}</Message></Response>", media_type="application/xml")