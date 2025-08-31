import fitz

def analyze_at_sitead_char_positions():
    """at {{sitead}} span'ındaki karakter pozisyonlarını analiz et"""
    print("🔍 AT SITEAD KARAKTER POZİSYON ANALİZİ")
    print("=" * 50)
    
    doc = fitz.open("ornek_yeni.pdf")
    page = doc[0]
    
    # "at {{sitead}}" span'ını bul
    text_dict = page.get_text("dict")
    for block in text_dict["blocks"]:
        if "lines" in block:
            for line in block["lines"]:
                for span in line["spans"]:
                    span_text = span["text"]
                    if "at {{sitead}}" == span_text:
                        bbox = span["bbox"]
                        font_size = span["size"]
                        
                        print(f"📍 SPAN: '{span_text}'")
                        print(f"   Position: ({bbox[0]:.1f}, {bbox[1]:.1f}) - ({bbox[2]:.1f}, {bbox[3]:.1f})")
                        print(f"   Size: {bbox[2] - bbox[0]:.1f} x {bbox[3] - bbox[1]:.1f}")
                        print(f"   Font size: {font_size:.1f}")
                        print(f"   Characters: {len(span_text)} chars")
                        
                        # Karakter genişliği
                        total_width = bbox[2] - bbox[0]
                        char_width = total_width / len(span_text)
                        print(f"   Average char width: {char_width:.1f}")
                        
                        # {{sitead}} pozisyonunu hesapla
                        placeholder_text = "{{sitead}}"
                        start_index = span_text.find(placeholder_text)
                        print(f"   '{{{{sitead}}}}' starts at index: {start_index}")
                        
                        if start_index >= 0:
                            # Mevcut hesaplama
                            placeholder_start_x = bbox[0] + (start_index * char_width)
                            placeholder_end_x = placeholder_start_x + (len(placeholder_text) * char_width)
                            
                            print(f"\n📐 MEVCUT HESAPLAMA:")
                            print(f"   Placeholder start X: {placeholder_start_x:.1f}")
                            print(f"   Placeholder end X: {placeholder_end_x:.1f}")
                            print(f"   Placeholder width: {placeholder_end_x - placeholder_start_x:.1f}")
                            
                            # NEW text pozisyonu
                            new_rect = [164.3, 138.3, 429.7, 256.1]
                            print(f"\n🚨 NEW TEXT:")
                            print(f"   Position: ({new_rect[0]:.1f}, {new_rect[1]:.1f}) - ({new_rect[2]:.1f}, {new_rect[3]:.1f})")
                            
                            # Overlap kontrolü
                            if (placeholder_start_x < new_rect[2] and placeholder_end_x > new_rect[0] and 
                                bbox[1] < new_rect[3] and bbox[3] > new_rect[1]):
                                print(f"   ❌ PLACEHOLDER TAHMIN EDİLEN ALAN NEW İLE OVERLAP EDİYOR!")
                                
                                # Daha iyi hesaplama
                                print(f"\n💡 DAHA İYİ HESAPLAMA ÖNERİSİ:")
                                
                                # "at " kısmının genişliğini tahmin et (daha konservatif)
                                at_space_chars = 3  # "at " = 3 karakter
                                estimated_at_width = at_space_chars * char_width * 0.8  # %20 daha konservatif
                                better_start_x = bbox[0] + estimated_at_width
                                
                                # {{sitead}} genişliği için de daha konservatif tahmin
                                placeholder_chars = len("{{sitead}}")
                                estimated_placeholder_width = placeholder_chars * char_width * 0.7  # %30 daha konservatif
                                better_end_x = better_start_x + estimated_placeholder_width
                                
                                print(f"   Better start X: {better_start_x:.1f}")
                                print(f"   Better end X: {better_end_x:.1f}")
                                print(f"   Better width: {better_end_x - better_start_x:.1f}")
                                
                                # Yeni overlap kontrolü
                                if (better_start_x < new_rect[2] and better_end_x > new_rect[0] and 
                                    bbox[1] < new_rect[3] and bbox[3] > new_rect[1]):
                                    print(f"   ⚠️ Hâlâ overlap var")
                                else:
                                    print(f"   ✅ Artık overlap yok!")
    
    doc.close()

if __name__ == "__main__":
    analyze_at_sitead_char_positions()
