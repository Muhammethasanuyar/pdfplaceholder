# clean_system.py - Temiz Placeholder Sistemi
import os
import json
import uuid
import tempfile
import unicodedata
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

import fitz  # PyMuPDF
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Clean PDF Placeholder Filler")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session storage
SESSIONS: Dict[str, Dict] = {}
SESSION_DIR = Path("clean_sessions")
SESSION_DIR.mkdir(exist_ok=True)

class FillRequest(BaseModel):
    session_id: str
    values: Dict[str, str]

def normalize_turkish_text(text: str) -> str:
    """Türkçe karakterleri doğru şekilde normalize eder"""
    if not isinstance(text, str):
        return str(text)
    
    try:
        # Unicode normalize
        normalized = unicodedata.normalize('NFC', text)
        print(f"🇹🇷 Turkish normalized: '{text}' -> '{normalized}'")
        return normalized
    except Exception as e:
        print(f"⚠️ Turkish normalization error: {e}")
        return text

def detect_placeholders(doc: fitz.Document) -> List[Dict]:
    """{{}} formatındaki placeholder'ları tespit eder"""
    placeholders = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"📄 Scanning page {page_num + 1}...")
        
        # Method 1: Direct regex search
        try:
            text_instances = page.search_for(r"\{\{[^}]+\}\}")
            print(f"🔍 Found {len(text_instances)} potential matches with regex")
            
            for inst in text_instances:
                rect = inst if isinstance(inst, fitz.Rect) else fitz.Rect(inst)
                
                # Get text in this area
                clip_text = page.get_textbox(rect)
                print(f"📝 Text in rect: '{clip_text}'")
                
                if "{{" in clip_text and "}}" in clip_text:
                    # Extract key from {{key}}
                    key_match = re.search(r'\{\{([^}]+)\}\}', clip_text)
                    if key_match:
                        key = key_match.group(1).strip()
                        full_match = key_match.group(0)
                        
                        placeholder = {
                            "key": key,
                            "text": full_match,
                            "page": page_num,
                            "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                            "suggestion": f"Örnek_{key}"
                        }
                        placeholders.append(placeholder)
                        print(f"🎯 Found placeholder: '{full_match}' -> key: '{key}' at page {page_num+1}")
        
        except Exception as e:
            print(f"⚠️ Regex search error: {e}")
        
        # Method 2: Manual text scanning (fallback)
        if not placeholders:
            print("🔍 Trying manual text scanning...")
            try:
                text_dict = page.get_text("dict")
                
                for block in text_dict.get("blocks", []):
                    if "lines" not in block:
                        continue
                    
                    for line in block["lines"]:
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            if "{{" in span_text and "}}" in span_text:
                                print(f"📝 Found text with {{}}: '{span_text}'")
                                
                                # Extract all {{}} patterns from this span
                                matches = re.finditer(r'\{\{([^}]+)\}\}', span_text)
                                for match in matches:
                                    key = match.group(1).strip()
                                    full_match = match.group(0)
                                    
                                    # Calculate approximate rect
                                    bbox = span.get("bbox", [0, 0, 100, 100])
                                    rect = fitz.Rect(bbox)
                                    
                                    placeholder = {
                                        "key": key,
                                        "text": full_match,
                                        "page": page_num,
                                        "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                                        "suggestion": f"Örnek_{key}"
                                    }
                                    placeholders.append(placeholder)
                                    print(f"🎯 Manual found: '{full_match}' -> key: '{key}' at page {page_num+1}")
                
            except Exception as e:
                print(f"⚠️ Manual scan error: {e}")
    
    # Remove duplicates
    unique_placeholders = []
    seen_keys = set()
    
    for ph in placeholders:
        if ph["key"] not in seen_keys:
            unique_placeholders.append(ph)
            seen_keys.add(ph["key"])
    
    print(f"📋 Total unique placeholders: {len(unique_placeholders)}")
    return unique_placeholders

def remove_placeholder_text(doc: fitz.Document, placeholders: List[Dict]) -> fitz.Document:
    """Placeholder'ları PDF'den tamamen siler (arka planı koruyarak)"""
    print(f"🧹 Removing {len(placeholders)} placeholders from PDF...")
    
    if not placeholders:
        print("📄 No placeholders to remove")
        return doc
    
    for placeholder in placeholders:
        page_num = placeholder["page"]
        rect = fitz.Rect(placeholder["rect"])
        text_to_remove = placeholder["text"]
        
        try:
            page = doc[page_num]
            
            print(f"🔄 Removing '{text_to_remove}' from page {page_num + 1}")
            
            # Method 1: Redaction (physically removes text while preserving background)
            page.add_redact_annot(rect)
            page.apply_redactions()
            print(f"✅ Successfully removed '{text_to_remove}'")
            
        except Exception as e:
            print(f"⚠️ Redaction failed for '{text_to_remove}': {e}")
            
            # Method 2: Fallback - Draw white rectangle
            try:
                page = doc[page_num]
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                print(f"✅ Fallback: Covered '{text_to_remove}' with white")
            except Exception as e2:
                print(f"❌ Both methods failed for '{text_to_remove}': {e2}")
    
    print("💾 Placeholder removal completed")
    return doc

def fill_placeholders(doc: fitz.Document, placeholders: List[Dict], values: Dict[str, str]) -> fitz.Document:
    """Temizlenmiş PDF'e yeni metinleri ekler"""
    print(f"📝 Filling {len(values)} placeholders...")
    
    for placeholder in placeholders:
        key = placeholder["key"]
        if key not in values:
            continue
            
        value = values[key]
        if not value:
            continue
            
        # Normalize Turkish text
        optimized_text = normalize_turkish_text(value)
        
        page_num = placeholder["page"]
        rect = fitz.Rect(placeholder["rect"])
        
        page = doc[page_num]
        
        # Calculate position and size
        rect_width = rect.width
        rect_height = rect.height
        
        # Font size calculation
        font_size = min(rect_height * 0.7, 14)  # Dynamic sizing
        font_size = max(font_size, 8)  # Minimum size
        
        # Position calculation (centered)
        x_pos = rect.x0 + (rect_width - len(optimized_text) * font_size * 0.6) / 2
        y_pos = rect.y1 - (rect_height - font_size) / 2
        
        try:
            # Insert text with Turkish support
            page.insert_text(
                (x_pos, y_pos),
                optimized_text,
                fontname="helv",
                fontsize=font_size,
                color=(0, 0, 0)  # Black
            )
            print(f"✅ Filled '{key}' with '{optimized_text}' (size: {font_size:.1f}pt)")
            
        except Exception as e:
            print(f"⚠️ Fill error for '{key}': {e}")
            # Fallback with basic text
            try:
                page.insert_text(
                    (rect.x0 + 5, rect.y1 - 5),
                    optimized_text,
                    fontname="helv",
                    fontsize=12
                )
                print(f"✅ Fallback fill for '{key}'")
            except Exception as e2:
                print(f"❌ Complete failure for '{key}': {e2}")
    
    return doc

@app.post("/api/analyze")
async def analyze_pdf(file: UploadFile = File(...)):
    """PDF'i analiz eder ve placeholder'ları tespit eder"""
    try:
        session_id = str(uuid.uuid4())
        
        # Save original file
        file_content = await file.read()
        original_path = SESSION_DIR / f"{session_id}_original.pdf"
        
        with open(original_path, "wb") as f:
            f.write(file_content)
        
        print(f"📁 Analyzing: {file.filename}")
        
        # Open PDF and detect placeholders
        doc = fitz.open(original_path)
        placeholders = detect_placeholders(doc)
        
        if not placeholders:
            doc.close()
            return JSONResponse({
                "success": False,
                "message": "Bu PDF'de {{}} formatında placeholder bulunamadı.",
                "session_id": session_id,
                "placeholders": []
            })
        
        # Remove placeholders and save cleaned version
        cleaned_doc = remove_placeholder_text(doc, placeholders)
        cleaned_path = SESSION_DIR / f"{session_id}_cleaned.pdf"
        cleaned_doc.save(cleaned_path)
        
        # Close documents properly
        doc.close()
        if cleaned_doc != doc:  # Only close if it's a different document
            cleaned_doc.close()
        
        # Store session
        SESSIONS[session_id] = {
            "original_file": str(original_path),
            "cleaned_file": str(cleaned_path),
            "placeholders": placeholders,
            "filename": file.filename
        }
        
        print(f"💾 Session saved: {session_id}")
        
        return JSONResponse({
            "success": True,
            "message": f"{len(placeholders)} placeholder tespit edildi ve temizlendi.",
            "session_id": session_id,
            "placeholders": placeholders
        })
        
    except Exception as e:
        print(f"❌ Analysis error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analiz hatası: {str(e)}")

@app.get("/api/preview/{session_id}")
async def preview_pdf(session_id: str, cleaned: bool = False):
    """PDF önizlemesini döner"""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session bulunamadı")
    
    session = SESSIONS[session_id]
    file_path = session["cleaned_file"] if cleaned else session["original_file"]
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı")
    
    return FileResponse(file_path, media_type="application/pdf")

@app.post("/api/fill")
async def fill_pdf(request: FillRequest):
    """Placeholder'ları doldurur ve sonucu döner"""
    try:
        session_id = request.session_id
        values = request.values
        
        if session_id not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session bulunamadı")
        
        session = SESSIONS[session_id]
        placeholders = session["placeholders"]
        cleaned_file = session["cleaned_file"]
        
        print(f"📝 Filling PDF for session: {session_id}")
        print(f"📊 Values to fill: {values}")
        
        # Open cleaned PDF
        doc = fitz.open(cleaned_file)
        
        # Fill placeholders
        filled_doc = fill_placeholders(doc, placeholders, values)
        
        # Save filled version
        filled_path = SESSION_DIR / f"{session_id}_filled.pdf"
        filled_doc.save(filled_path)
        
        doc.close()
        filled_doc.close()
        
        # Update session
        session["filled_file"] = str(filled_path)
        
        print(f"💾 Filled PDF saved: {filled_path}")
        
        return JSONResponse({
            "success": True,
            "message": f"{len(values)} alan dolduruldu.",
            "download_url": f"/api/download/{session_id}"
        })
        
    except Exception as e:
        print(f"❌ Fill error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Doldurma hatası: {str(e)}")

@app.get("/api/download/{session_id}")
async def download_filled_pdf(session_id: str):
    """Doldurulmuş PDF'i indirir"""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session bulunamadı")
    
    session = SESSIONS[session_id]
    
    if "filled_file" not in session:
        raise HTTPException(status_code=404, detail="Doldurulmuş PDF bulunamadı")
    
    filled_file = session["filled_file"]
    if not os.path.exists(filled_file):
        raise HTTPException(status_code=404, detail="PDF dosyası bulunamadı")
    
    filename = session.get("filename", "filled.pdf")
    return FileResponse(
        filled_file,
        media_type="application/pdf",
        filename=f"filled_{filename}"
    )

@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "Clean System Running"}

# Serve frontend
@app.get("/")
async def serve_frontend():
    try:
        from fastapi.responses import HTMLResponse
        with open("clean_frontend.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return JSONResponse({"message": "Clean PDF System Running", "port": 8009})
    except Exception as e:
        print(f"Frontend serve error: {e}")
        return JSONResponse({"message": "Clean PDF System Running", "port": 8009, "error": str(e)})

if __name__ == "__main__":
    import uvicorn
    print("🚀 Clean PDF Placeholder System başlatılıyor...")
    print("📱 URL: http://localhost:8009")
    print("🧹 Features: True Text Deletion, Turkish Support")
    print("⚡ Clean & Simple!")
    
    uvicorn.run(app, host="127.0.0.1", port=8009)
