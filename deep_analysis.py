import fitz
import sys
import requests

def analyze_pdf_deeply(pdf_path):
    print(f"🔍 DETAYLI PDF ANALİZ: {pdf_path}")
    print("=" * 50)
    
    doc = fitz.open(pdf_path)
    
    for page_num, page in enumerate(doc, 1):
        print(f"\n📄 SAYFA {page_num}:")
        print("-" * 20)
        
        # Tüm text blokları
        blocks = page.get_text("dict")["blocks"]
        
        print(f"📝 Toplam text blokları: {len([b for b in blocks if 'lines' in b])}")
        
        for i, block in enumerate(blocks):
            if "lines" in block:
                for j, line in enumerate(block["lines"]):
                    for k, span in enumerate(line["spans"]):
                        text = span["text"].strip()
                        if text:
                            bbox = span["bbox"]
                            print(f"  📍 [{i}.{j}.{k}] '{text}' @ ({bbox[0]:.1f}, {bbox[1]:.1f}) - ({bbox[2]:.1f}, {bbox[3]:.1f})")
                            
                            # NEW metni kontrolü
                            if "NEW" in text.upper():
                                print(f"    🚨 'NEW' metni tespit edildi: '{text}'")
                            
                            # Ad pattern kontrolü  
                            if "{{" in text and "}}" in text:
                                print(f"    🎯 Placeholder tespit edildi: '{text}'")
    
    doc.close()

def compare_before_after():
    print(f"\n🔄 ÖNCE/SONRA KARŞILAŞTIRMA")
    print("=" * 50)
    
    # Son session ID'yi al
    import glob
    session_files = glob.glob("perfect_sessions/*_original.pdf")
    if session_files:
        latest_session = sorted(session_files)[-1]
        session_id = latest_session.split("\\")[-1].replace("_original.pdf", "")
        
        print(f"📊 Session ID: {session_id}")
        
        original_path = f"perfect_sessions/{session_id}_original.pdf"
        cleaned_path = f"perfect_sessions/{session_id}_cleaned.pdf"
        filled_path = f"perfect_sessions/{session_id}_filled.pdf"
        
        print(f"\n📄 ORIGINAL PDF ANALİZİ:")
        analyze_pdf_deeply(original_path)
        
        print(f"\n🧹 CLEANED PDF ANALİZİ:")
        analyze_pdf_deeply(cleaned_path)
        
        print(f"\n✅ FILLED PDF ANALİZİ:")
        analyze_pdf_deeply(filled_path)
        
        return session_id
    
    return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_pdf_deeply(sys.argv[1])
    else:
        session_id = compare_before_after()
        print(f"\n🌐 Preview URLs:")
        print(f"Original: http://localhost:8011/api/preview/{session_id}?original=true")
        print(f"Cleaned:  http://localhost:8011/api/preview/{session_id}?cleaned=true")
        print(f"Filled:   http://localhost:8011/api/preview/{session_id}")
