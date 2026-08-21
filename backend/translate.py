# ============================================================
#  MHEWS — backend/translate.py
#  Complete Translation API with Fallback Chain
# ============================================================
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from backend.main import database

router = APIRouter(prefix="/alerts/translate", tags=["Translation"])

class TranslateRequest(BaseModel):
    alert_id: str
    language: str

async def translate_text(text: str, target_lang: str) -> str:
    """Robust translation chain with multiple fallbacks."""
    if target_lang == "en" or not text:
        return text

    # 1. Try MyMemory (Free, no key required)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text, "langpair": f"en|{target_lang}"}
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("responseStatus") == 200:
                translated = data["responseData"]["translatedText"]
                if translated and translated != text:
                    return translated
    except Exception as e:
        print(f"MyMemory failed: {e}")

    # 2. Try LibreTranslate (Public fallback)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://libretranslate.de/translate",
                json={"q": text, "source": "en", "target": target_lang, "format": "text"}
            )
            resp.raise_for_status()
            translated = resp.json().get("translatedText", "")
            if translated and translated != text:
                return translated
    except Exception as e:
        print(f"LibreTranslate failed: {e}")

    # 3. Final Fallback: Return original English text
    print(f"⚠️ All translation APIs failed for {target_lang}. Returning English.")
    return text

@router.post("", summary="Translate an alert into a target language")
async def translate_alert(request: TranslateRequest):
    # Fetch the alert from the database
    row = await database.fetch_one("SELECT id, description, plain_text FROM alerts WHERE id = :id", values={"id": request.alert_id})
    
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    text_to_translate = row["plain_text"] or row["description"]
    if not text_to_translate:
        raise HTTPException(status_code=400, detail="Alert has no text to translate")

    # Run through the fallback chain
    translated_text = await translate_text(text_to_translate, request.language)

    # Update the database with the new translation
    await database.execute(
        "UPDATE alerts SET plain_text = :text, plain_text_language = :lang WHERE id = :id",
        values={"text": translated_text, "lang": request.language, "id": request.alert_id}
    )

    return {
        "alert_id": request.alert_id,
        "language": request.language,
        "plain_text": translated_text
    }