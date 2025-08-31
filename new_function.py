def insert_natural_text_with_analysis(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str], font_analysis: Dict[str, Any], font_choice: Optional[str] = None, text_color: Optional[List[float]] = None, font_size_mode: str = "auto", fixed_font_size: Optional[float] = None, min_font_size: Optional[float] = None, max_font_size: Optional[float] = None, allow_overflow: bool = False, text_alignments: Dict[str, str] = {}, alignment_offsets: Dict[str, float] = {}) -> fitz.Document:
    """🎯 SMART PLACEHOLDER FILLING - Her placeholder için özel font size ve SADECE KULLANILAN KEY'LER"""
    print(f"✨ SMART PLACEHOLDER FILLING: {len(values)} values to fill")

    def _get_turkish_fontfile() -> Optional[str]:
        # Font öncelikleri
        font_priorities = [
            "DejaVuSans.ttf", "NotoSans-Regular.ttf", "OpenSans-Regular.ttf",
            "Roboto-Regular.ttf", "Ubuntu-Regular.ttf", "BebasNeue-Regular.ttf"
        ]
        
        for font_name in font_priorities:
            font_path = FONTS_DIR / font_name
            if font_path.exists():
                return str(font_path)
        return None

    default_ttf = _get_turkish_fontfile()
    if default_ttf:
        print(f"🇹🇷 Default TTF: {default_ttf}")
    
    # Kullanıcı font seçimi varsa kullan
    if font_choice and Path(font_choice).exists():
        print(f"👤 User selected font: {font_choice}")
        default_ttf = font_choice

    # STEP 1: Sadece gerçekten kullanılacak placeholder'ları filtrele
    active_placeholders = []
    processed_keys = set()  # Aynı key'i iki kez işlemeyi engelle
    
    for ph in placeholders:
        key = ph.get("key", "")
        base_key = key.split('_')[0] if '_' in key else key  # sitead_1 -> sitead
        
        # Bu key için değer var mı ve daha önce işlenmiş mi?
        if base_key in values and key not in processed_keys:
            active_placeholders.append(ph)
            processed_keys.add(key)
            print(f"✅ ACTIVE PLACEHOLDER: '{key}' -> '{values[base_key][:30]}...'")
        elif key in processed_keys:
            print(f"⏭️ SKIPPING DUPLICATE: '{key}' (already processed)")
        else:
            print(f"⏭️ SKIPPING UNUSED: '{key}' (no value provided)")
    
    print(f"🎯 PROCESSING {len(active_placeholders)} unique placeholders (filtered from {len(placeholders)} total)")
    
    # STEP 2: Her aktif placeholder'ı individual olarak işle
    for ph in active_placeholders:
        key = ph.get("key", "")
        base_key = key.split('_')[0] if '_' in key else key  # sitead_1 -> sitead
        
        if base_key not in values:
            print(f"⚠️ No value for base key '{base_key}' (from '{key}')")
            continue

        raw_val = values.get(base_key, "")
        text = normalize_turkish_text(raw_val)
        if not text:
            print(f"⚠️ Empty text after normalization for '{key}'")
            continue

        page = doc[ph.get("page", 0)]
        rect = fitz.Rect(*ph.get("rect", [0, 0, 0, 0]))
        print(f"\n🎯 PROCESSING '{key}' (base: '{base_key}') -> '{text}'")
        print(f"📐 Original rect: {rect} (W:{rect.width:.1f} H:{rect.height:.1f})")

        # Rect genişletme - overflow izni varsa daha geniş alan
        if allow_overflow:
            page_rect = page.rect
            expanded_width = rect.width * 1.5
            expanded_height = rect.height * 1.3
            
            center_x = (rect.x0 + rect.x1) / 2
            center_y = (rect.y0 + rect.y1) / 2
            
            new_x0 = max(0, center_x - expanded_width / 2)
            new_x1 = min(page_rect.width, center_x + expanded_width / 2)
            new_y0 = max(0, center_y - expanded_height / 2)
            new_y1 = min(page_rect.height, center_y + expanded_height / 2)
            
            rect = fitz.Rect(new_x0, new_y0, new_x1, new_y1)
            print(f"📏 EXPANDED RECT for overflow: {rect}")
        else:
            try:
                rect = _expand_rect_to_line(page, rect)
                print(f"📏 LINE-EXPANDED RECT: {rect}")
            except Exception:
                print(f"📏 Using original rect (expansion failed)")

        # INDIVIDUAL FONT SIZE CALCULATION - Her placeholder için farklı
        if font_size_mode == "fixed" and fixed_font_size:
            fs = float(fixed_font_size)
            print(f"🔧 FIXED FONT SIZE: {fs:.1f}pt")
        elif font_size_mode == "min_max" and min_font_size and max_font_size:
            base_fs = rect.height * 0.60
            fs = round(base_fs, 1)
            fs = max(float(min_font_size), min(fs, float(max_font_size)))
            print(f"🎯 MIN/MAX FONT SIZE: base={base_fs:.1f}pt -> constrained={fs:.1f}pt")
        else:
            # INDIVIDUAL AUTO SIZING - Bu placeholder'ın boyutuna göre
            base_fs = rect.height * 0.65  # %65 doldurma oranı
            fs = round(min(base_fs, 28.0), 1)  # Max 28pt
            fs = max(fs, 6.0)  # Min 6pt
            print(f"🎯 INDIVIDUAL AUTO SIZE: rect.height={rect.height:.1f} -> {fs:.1f}pt")
        
        # Renk belirleme
        if text_color and len(text_color) >= 3:
            color = tuple(text_color[:3])
            print(f"🎨 USER COLOR: {color}")
        else:
            color = tuple(ph.get("original_color", (0, 0, 0)))
            print(f"🎨 ORIGINAL COLOR: {color}")
        
        # Hizalama belirleme
        user_alignment = text_alignments.get(key, "center")
        manual_offset = alignment_offsets.get(key, 0.0)
        
        if manual_offset != 0:
            alignment = fitz.TEXT_ALIGN_LEFT
            align_text = f"MANUEL ({manual_offset:+.1f}px)"
        elif user_alignment == "left":
            alignment = fitz.TEXT_ALIGN_LEFT
            align_text = "SOL"
        elif user_alignment == "right":
            alignment = fitz.TEXT_ALIGN_RIGHT
            align_text = "SAĞ"
        else:
            alignment = fitz.TEXT_ALIGN_CENTER
            align_text = "MERKEZ"
        
        print(f"📍 ALIGNMENT: {align_text}")
        
        # Font seçimi
        fontfile_path = None
        font_source = "fallback"
        
        if font_choice and Path(font_choice).exists():
            has_turkish = any(c in text for c in "çğıöşüÇĞİÖŞÜ")
            if has_turkish:
                unicode_support = test_font_unicode_support(font_choice, text)
                if unicode_support:
                    fontfile_path = font_choice
                    font_source = "user_selected"
                    print(f"✅ USER FONT OK: {Path(font_choice).name}")
                else:
                    fontfile_path = default_ttf
                    font_source = "unicode_fallback"
                    print(f"⚠️ USER FONT UNICODE FAIL -> fallback")
            else:
                fontfile_path = font_choice
                font_source = "user_selected"
                print(f"✅ USER FONT OK (ASCII): {Path(font_choice).name}")
        else:
            font_config = get_font_config_for_placeholder(font_analysis, ph)
            fontfile_path = font_config.get("fontfile") or default_ttf
            font_source = font_config.get("source", "fallback")
        
        if fontfile_path:
            font_name = Path(fontfile_path).stem
            print(f"🖨️ FONT: {font_name} ({font_source})")

        # SINGLE PLACEMENT ATTEMPT - Bu placeholder için sadece bir kez
        success = False
        attempt_count = 0
        max_attempts = 3  # Daha az deneme
        current_fs = fs
        
        print(f"🚀 PLACEMENT ATTEMPTS for '{key}':")
        while not success and attempt_count < max_attempts:
            attempt_count += 1
            try:
                if fontfile_path:
                    print(f"   🔍 ATTEMPT {attempt_count}: {current_fs:.1f}pt")
                    
                    # Hizalamaya göre rect'i ayarla (çok minimal adjustment)
                    adjusted_rect = fitz.Rect(rect)
                    offset_x = manual_offset if manual_offset != 0 else 0
                    
                    if user_alignment == "left":
                        adjusted_rect = fitz.Rect(rect.x0 + offset_x, rect.y0, rect.x1, rect.y1)
                    elif user_alignment == "right":  
                        adjusted_rect = fitz.Rect(rect.x0 + offset_x, rect.y0, rect.x1 + offset_x, rect.y1)
                    else:  # center
                        adjusted_rect = fitz.Rect(rect.x0 + offset_x, rect.y0, rect.x1 + offset_x, rect.y1)
                    
                    if offset_x != 0:
                        print(f"   🎯 OFFSET: {offset_x}px")
                    
                    result = page.insert_textbox(
                        adjusted_rect,
                        text,
                        fontname="embedded",
                        fontfile=fontfile_path,
                        fontsize=current_fs,
                        align=alignment,
                        color=color
                    )
                    
                    if result in (0, None, ""):
                        print(f"   ✅ SUCCESS: {current_fs:.1f}pt")
                        success = True
                    else:
                        print(f"   ⚠️ OVERFLOW: Result={result}")
                        if allow_overflow and attempt_count == max_attempts:
                            print(f"   🚧 FORCE PLACEMENT (overflow allowed)")
                            try:
                                # Force placement with insert_text
                                pos_x = rect.x0 + (rect.width / 2)  # Merkez
                                
                                if user_alignment == "left":
                                    pos_x = rect.x0 + 2
                                elif user_alignment == "right":
                                    pos_x = rect.x1 - 20
                                
                                if manual_offset != 0:
                                    pos_x += manual_offset
                                    print(f"   🎯 FORCE OFFSET: {manual_offset}px")
                                
                                pos_y = rect.y0 + (rect.height * 0.7)
                                
                                page.insert_text(
                                    (pos_x, pos_y),
                                    text,
                                    fontname="embedded",
                                    fontfile=fontfile_path,
                                    fontsize=current_fs,
                                    color=color
                                )
                                print(f"   ✅ FORCE PLACED: {current_fs:.1f}pt")
                                success = True
                            except Exception as e:
                                print(f"   ❌ FORCE FAILED: {e}")
                        
                        if not success:
                            current_fs = max(6.0, current_fs * 0.8)
                            print(f"   📉 Reducing to {current_fs:.1f}pt")
                            
                            if current_fs <= 6.0:
                                print(f"   ⚠️ Min size reached, accepting")
                                success = True
                                
                else:
                    # ASCII fallback
                    ascii_map = {'ç':'c','ğ':'g','ı':'i','ö':'o','ş':'s','ü':'u','Ç':'C','Ğ':'G','İ':'I','Ö':'O','Ş':'S','Ü':'U'}
                    safe_text = ''.join(ascii_map.get(ch, ch) for ch in text)
                    
                    result = page.insert_textbox(
                        rect,
                        safe_text,
                        fontname="helv",
                        fontsize=current_fs,
                        align=alignment,
                        color=color
                    )
                    
                    if result in (0, None, ""):
                        print(f"   ✅ ASCII SUCCESS: {current_fs:.1f}pt")
                        success = True
                    else:
                        current_fs = max(6.0, current_fs * 0.8)
                        if current_fs <= 6.0:
                            success = True
            
            except Exception as e:
                print(f"   ❌ ATTEMPT {attempt_count} FAILED: {e}")
                current_fs = max(6.0, current_fs * 0.8)
                if current_fs <= 6.0:
                    success = True
        
        if not success:
            print(f"❌ ALL ATTEMPTS FAILED for '{key}' after {max_attempts} tries")
        else:
            print(f"💎 COMPLETED '{key}' successfully")

    print("✨ SMART PLACEHOLDER FILLING COMPLETED")
    return doc
