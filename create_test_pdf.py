import fitz  # PyMuPDF

# Test PDF oluştur
doc = fitz.open()  # Boş PDF
page = doc.new_page()

# Placeholder'lar ekle
page.insert_text((100, 100), "Ad Soyad: {{ad_soyad}}", fontsize=14)
page.insert_text((100, 130), "Tarih: {{tarih}}", fontsize=14)
page.insert_text((100, 160), "Şehir: {{sehir}}", fontsize=14)
page.insert_text((100, 190), "E-posta: {{email}}", fontsize=14)

# Arka plan ekle (renk ve şekil)
shape = page.new_shape()
shape.draw_rect(fitz.Rect(50, 50, 550, 250))
shape.finish(color=(0.8, 0.9, 1.0), fill=(0.8, 0.9, 1.0), width=2)
shape.commit()

# Test PDF'i kaydet
doc.save("test_placeholder.pdf")
doc.close()

print("✅ Test PDF oluşturuldu: test_placeholder.pdf")


