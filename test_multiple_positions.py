#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for multiple placeholder positions with different values
"""

import fitz
from pathlib import Path

def analyze_ornek_positions():
    """Ornek.pdf'deki placeholder pozisyonlarını analiz et"""
    
    pdf_path = "perfect_sessions/9ac1df93-8a55-4cc7-8915-db13e33aef73_original.pdf"
    if not Path(pdf_path).exists():
        # Diğer test dosyalarını dene
        test_files = [
            "ai_sessions/test_form.pdf",
            "Ornek.pdf",
            "Ornek (1).pdf",
            "Ornek (2).pdf"
        ]
        
        pdf_path = None
        for f in test_files:
            if Path(f).exists():
                pdf_path = f
                break
        
        if not pdf_path:
            print("❌ Test PDF bulunamadı!")
            return None
    
    print(f"📄 Analyzing PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    page = doc[0]
    
    # Tüm {{sitead}} placeholder'larını bul
    sitead_positions = page.search_for("{{sitead}}")
    oran_positions = page.search_for("{{oran}}")
    
    print(f"\n🎯 SITEAD Placeholder Positions ({len(sitead_positions)}):")
    for i, rect in enumerate(sitead_positions):
        print(f"   Position {i+1}: {rect} (x={rect.x0:.1f}, y={rect.y0:.1f}, w={rect.width:.1f}, h={rect.height:.1f})")
        
        # Çevresindeki metni al
        expanded = fitz.Rect(rect.x0-50, rect.y0-10, rect.x1+50, rect.y1+10)
        context = page.get_textbox(expanded).strip()
        if context:
            print(f"      Context: '{context[:60]}...' " if len(context) > 60 else f"      Context: '{context}'")
    
    print(f"\n🎯 ORAN Placeholder Positions ({len(oran_positions)}):")
    for i, rect in enumerate(oran_positions):
        print(f"   Position {i+1}: {rect} (x={rect.x0:.1f}, y={rect.y0:.1f}, w={rect.width:.1f}, h={rect.height:.1f})")
        
        # Çevresindeki metni al  
        expanded = fitz.Rect(rect.x0-50, rect.y0-10, rect.x1+50, rect.y1+10)
        context = page.get_textbox(expanded).strip()
        if context:
            print(f"      Context: '{context[:60]}...' " if len(context) > 60 else f"      Context: '{context}'")
    
    doc.close()
    
    # Önerilen çözüm
    print(f"\n💡 ÇÖZÜM ÖNERİSİ:")
    print(f"   📍 {len(sitead_positions)} farklı 'sitead' pozisyonu için ayrı değerler")
    print(f"   📍 {len(oran_positions)} farklı 'oran' pozisyonu için ayrı değerler")
    print(f"   🎯 Frontend'te: sitead_1, sitead_2, sitead_3 şeklinde ayrı inputlar")
    print(f"   🎯 Backend'te: pozisyon indeksi ile eşleştirme")

if __name__ == "__main__":
    analyze_ornek_positions()
