import sys
sys.path.append('.')

import fitz
from perfect_system import detect_placeholders_perfect

def debug_placeholder_detection():
    """Placeholder detection'ı debug et"""
    print("🔍 DEBUG: PLACEHOLDER DETECTION")
    print("=" * 40)
    
    # Original PDF'i analyze et
    pdf_path = "perfect_sessions/0e28a84a-ffdb-44dc-8674-39a5aa4e6c2c_original.pdf"
    doc = fitz.open(pdf_path)
    
    print(f"📄 Analyzing: {pdf_path}")
    print(f"📊 Pages: {len(doc)}")
    
    # NEW text location
    print(f"\n📍 NEW TEXT LOCATIONS:")
    for page_num, page in enumerate(doc):
        new_instances = page.search_for("NEW")
        for rect in new_instances:
            print(f"   NEW at page {page_num+1}: ({rect.x0:.1f}, {rect.y0:.1f}) - ({rect.x1:.1f}, {rect.y1:.1f})")
    
    # Run detection
    print(f"\n🎯 RUNNING PLACEHOLDER DETECTION:")
    placeholders = detect_placeholders_perfect(doc)
    
    print(f"\n📊 DETECTION RESULTS:")
    print(f"   Total placeholders found: {len(placeholders)}")
    
    for ph in placeholders:
        rect = ph['rect']
        print(f"   📍 '{ph['key']}' = '{ph['text']}' at ({rect[0]:.1f}, {rect[1]:.1f}) - ({rect[2]:.1f}, {rect[3]:.1f})")
        
        # NEW ile overlap kontrolü
        new_rect = [164.3, 138.3, 429.7, 256.1]  # NEW'in bilinen pozisyonu
        if (rect[0] < new_rect[2] and rect[2] > new_rect[0] and 
            rect[1] < new_rect[3] and rect[3] > new_rect[1]):
            print(f"      ❌ OVERLAPS WITH NEW TEXT!")
    
    doc.close()

if __name__ == "__main__":
    debug_placeholder_detection()
