# ============================================================
#  MHEWS — backend/translate.py
#  B9: Plain-language translation endpoint
#
#  Uses MyMemory free translation API — no key, no cost.
#  https://mymemory.translated.net/
#
#  Strategy:
#  1. Build a simple plain-language English version
#     from the CAP fields (event, description, instruction)
#  2. Send that to MyMemory to translate into target language
#  3. Cache result in PostGIS so we never translate twice
#
#  Supports all 11 official South African languages.
# ============================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
import os

from backend.main import database

router = APIRouter(
    prefix="/alerts",
    tags=["Translation"]
)

# ============================================================
#  Language configuration
# ============================================================
#  MyMemory language codes for all 11 official SA languages.
#  Format: "source|target" e.g. "en-ZA|zu-ZA"
# ============================================================
SUPPORTED_LANGUAGES = {
    'en':  {'name': 'English',                  'code': 'en-ZA'},
    'af':  {'name': 'Afrikaans',                'code': 'af-ZA'},
    'zu':  {'name': 'Zulu (isiZulu)',            'code': 'zu-ZA'},
    'xh':  {'name': 'Xhosa (isiXhosa)',          'code': 'xh-ZA'},
    'st':  {'name': 'Sotho (Sesotho)',           'code': 'st-ZA'},
    'nso': {'name': 'Northern Sotho (Sepedi)',   'code': 'nso-ZA'},
    'tn':  {'name': 'Tswana (Setswana)',         'code': 'tn-ZA'},
    'ts':  {'name': 'Tsonga (Xitsonga)',         'code': 'ts-ZA'},
    've':  {'name': 'Venda (Tshivenda)',         'code': 've-ZA'},
    'nr':  {'name': 'Ndebele (isiNdebele)',      'code': 'nr-ZA'},
    'ss':  {'name': 'Swati (siSwati)',           'code': 'ss-ZA'},
}

MYMEMORY_URL = "https://api.mymemory.translated.net/get"


# ============================================================
#  Request / response models
# ============================================================

class TranslateRequest(BaseModel):
    alert_id:    str
    language:    str = 'en'
    description: Optional[str] = None
    instruction: Optional[str] = None
    event:       Optional[str] = None


class TranslateResponse(BaseModel):
    alert_id:   str
    language:   str
    plain_text: str
    cached:     bool


# ============================================================
#  Helper — build plain English from CAP fields
# ============================================================

def build_plain_english(event: str, description: str,
                        instruction: str, area_desc: str) -> str:
    """
    Builds a simple plain-English sentence from CAP fields.
    This is what gets translated into other languages.

    Keeps it short and clear — 2-3 sentences max.
    """
    # Clean up the fields
    event       = (event or '').strip()
    description = (description or '').strip()
    instruction = (instruction or '').strip()
    area        = (area_desc or 'the affected area').strip()

    # Build a simple plain sentence
    # "There is a [event] in [area]. [description]. [instruction]."
    parts = []

    if event and area:
        parts.append(f"There is a {event} in {area}.")

    if description:
        # Shorten description to first sentence only
        first_sentence = description.split('.')[0].strip()
        if first_sentence and first_sentence not in parts[0] if parts else True:
            parts.append(first_sentence + '.')

    if instruction:
        # Take first instruction sentence
        first_instruction = instruction.split('.')[0].strip()
        parts.append(first_instruction + '.')

    return ' '.join(parts)


# ============================================================
#  Helper — call MyMemory translation API
# ============================================================

async def translate_text(text: str, target_lang_code: str) -> str:
    """
    Calls MyMemory free translation API.

    MyMemory API:
      GET https://api.mymemory.translated.net/get
        ?q=text to translate
        &langpair=en-ZA|zu-ZA

    Free tier: 1000 requests/day, no key needed.
    Returns translated text or raises an exception.
    """
    # English doesn't need translation
    if target_lang_code == 'en-ZA':
        return text

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                MYMEMORY_URL,
                params={
                    'q':        text,
                    'langpair': f'en-ZA|{target_lang_code}',
                    'de':       'mhews@thesis.ac.za'  # Optional email for higher limits
                }
            )

        if response.status_code != 200:
            raise Exception(f"MyMemory returned {response.status_code}")

        data = response.json()

        # MyMemory response structure:
        # { "responseData": { "translatedText": "..." }, "responseStatus": 200 }
        if data.get('responseStatus') != 200:
            raise Exception(f"MyMemory error: {data.get('responseDetails')}")

        translated = data['responseData']['translatedText']

        # MyMemory sometimes returns the original if it can't translate
        # Check if it actually translated (different from input)
        if translated.strip().lower() == text.strip().lower():
            return text  # Return original if no translation

        return translated.strip()

    except httpx.TimeoutException:
        raise Exception("Translation service timed out")
    except Exception as e:
        raise Exception(f"Translation failed: {str(e)}")


# ============================================================
#  B9 — POST /alerts/translate
# ============================================================

@router.post("/translate", response_model=TranslateResponse,
             summary="Translate alert into plain language")
async def translate_alert(request: TranslateRequest):
    """
    Translates a CAP alert into plain language in any
    of the 11 official South African languages.

    Uses MyMemory free translation API — no API key needed.
    Caches results in PostGIS to avoid duplicate requests.

    Request:
      { "alert_id": "SAWS-20240525-THU-001", "language": "zu" }
    """

    # Step 1: Validate language
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language '{request.language}'. "
                   f"Supported: {list(SUPPORTED_LANGUAGES.keys())}"
        )

    lang_config = SUPPORTED_LANGUAGES[request.language]
    lang_code   = lang_config['code']

    # Step 2: Fetch alert from DB if not provided directly
    if not request.description:
        row = await database.fetch_one(
            """
            SELECT description, instruction, event,
                   area_desc, plain_text, plain_text_language
            FROM alerts WHERE id = :id
            """,
            values={"id": request.alert_id}
        )

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Alert '{request.alert_id}' not found"
            )

        # Return cached if same language
        if (row["plain_text"] and
                row["plain_text_language"] == request.language):
            return TranslateResponse(
                alert_id=request.alert_id,
                language=request.language,
                plain_text=row["plain_text"],
                cached=True
            )

        description = row["description"] or ''
        instruction = row["instruction"] or ''
        event       = row["event"] or ''
        area_desc   = row["area_desc"] or ''

    else:
        description = request.description
        instruction = request.instruction or ''
        event       = request.event or ''
        area_desc   = ''

    # Step 3: Build plain English base text
    plain_english = build_plain_english(
        event, description, instruction, area_desc
    )

    # Step 4: Translate using MyMemory
    try:
        plain_text = await translate_text(plain_english, lang_code)
    except Exception as e:
        # If translation fails, return plain English as fallback
        # Better to show English than nothing during an emergency
        print(f"⚠️  Translation failed, using English fallback: {e}")
        plain_text = plain_english

    # Step 5: Cache in database
    if not request.description:
        await database.execute(
            """
            UPDATE alerts
            SET plain_text = :plain_text,
                plain_text_language = :language
            WHERE id = :id
            """,
            values={
                "plain_text": plain_text,
                "language":   request.language,
                "id":         request.alert_id,
            }
        )

    return TranslateResponse(
        alert_id=request.alert_id,
        language=request.language,
        plain_text=plain_text,
        cached=False
    )


# ============================================================
#  GET /alerts/languages
# ============================================================

@router.get("/languages", summary="List supported languages")
async def get_languages():
    """Returns all supported translation languages."""
    return {
        "languages": [
            {"code": code, "name": cfg["name"]}
            for code, cfg in SUPPORTED_LANGUAGES.items()
        ]
    }
