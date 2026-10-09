"""
Voice Pipeline Model Tester
Test Groq (LLM), Deepgram (STT), ElevenLabs (TTS) individually or as full pipeline.

Usage:
  python test_models.py groq              # Test Groq LLM
  python test_models.py deepgram <file>   # Test Deepgram STT with audio file
  python test_models.py elevenlabs        # Test ElevenLabs TTS
  python test_models.py pipeline          # Full pipeline test
"""

import os
import sys
import json
import httpx
from dotenv import load_dotenv

load_dotenv("ai-service/.env")

GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
DEEPGRAM_API_KEY   = os.getenv("DEEPGRAM_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VAPI_API_KEY       = os.getenv("VAPI_API_KEY")
VAPI_ASSISTANT_ID  = os.getenv("VAPI_ASSISTANT_ID")

# ── ENGINE FLAG ───────────────────────────────────────────────────────────────
# Change in .env: VOICE_ENGINE=vapi  OR  VOICE_ENGINE=custom
VOICE_ENGINE = os.getenv("VOICE_ENGINE", "vapi")  # default: vapi

# ── GROQ MODELS ──────────────────────────────────────────────────────────────
GROQ_MODELS = {
    "1": "llama-3.3-70b-versatile",
    "2": "llama-3.1-8b-instant",
    "3": "mixtral-8x7b-32768",
    "4": "gemma2-9b-it",
    "5": "llama3-groq-70b-8192-tool-use-preview",
}

# ── DEEPGRAM MODELS ───────────────────────────────────────────────────────────
DEEPGRAM_MODELS = {
    "1": "nova-3",
    "2": "nova-2",
    "3": "enhanced",
    "4": "base",
}

# ── ELEVENLABS VOICES ─────────────────────────────────────────────────────────
ELEVENLABS_VOICES = {
    "1": ("EXAVITQu4vr4xnSDxMaL", "Sarah"),
    "2": ("21m00Tcm4TlvDq8ikWAM", "Rachel"),
    "3": ("AZnzlk1XvdvUeBnXmlld", "Domi"),
    "4": ("MF3mGyEYCl7XYWbV9V6O", "Elli"),
    "5": ("TxGEqnHWrfWFTfGW9XjX", "Josh"),
}

ELEVENLABS_MODELS = {
    "1": "eleven_flash_v2_5",
    "2": "eleven_multilingual_v2",
    "3": "eleven_turbo_v2_5",
}


def pick(label: str, options: dict) -> str:
    print(f"\n{label}:")
    for k, v in options.items():
        name = v[1] if isinstance(v, tuple) else v
        print(f"  {k}. {name}")
    choice = input("Select (default=1): ").strip() or "1"
    return options.get(choice, list(options.values())[0])


# ── TEST GROQ ─────────────────────────────────────────────────────────────────
def test_groq():
    print("\n" + "="*50)
    print("GROQ LLM TEST")
    print("="*50)

    model = pick("Choose Groq model", GROQ_MODELS)
    prompt = input("\nEnter your message (default: 'What services do you offer?'): ").strip()
    if not prompt:
        prompt = "What services do you offer?"

    system = "You are James, a receptionist at AllZone Medical Centre. Reply in 1 short sentence."

    print(f"\nModel: {model}")
    print(f"Sending: {prompt}")
    print("Response: ", end="", flush=True)

    with httpx.Client() as client:
        res = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                "max_tokens": 200,
                "temperature": 0.7,
            },
            timeout=30,
        )

    if res.status_code == 200:
        data = res.json()
        reply = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print(reply)
        print(f"\n[tokens: {usage.get('total_tokens', '?')} | model: {model}]")
    else:
        print(f"ERROR {res.status_code}: {res.text}")


# ── TEST DEEPGRAM ─────────────────────────────────────────────────────────────
def test_deepgram(audio_file: str = None):
    print("\n" + "="*50)
    print("DEEPGRAM STT TEST")
    print("="*50)

    model = pick("Choose Deepgram model", DEEPGRAM_MODELS)

    if not audio_file:
        audio_file = input("\nEnter path to audio file (mp3/wav/m4a): ").strip()

    if not os.path.exists(audio_file):
        print(f"File not found: {audio_file}")
        return

    print(f"\nModel: {model}")
    print(f"File: {audio_file}")
    print("Transcribing...")

    with open(audio_file, "rb") as f:
        audio_data = f.read()

    ext = audio_file.rsplit(".", 1)[-1].lower()
    mime_map = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4", "ogg": "audio/ogg"}
    mime = mime_map.get(ext, "audio/mpeg")

    with httpx.Client() as client:
        res = client.post(
            f"https://api.deepgram.com/v1/listen?model={model}&smart_format=true&punctuate=true",
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": mime,
            },
            content=audio_data,
            timeout=60,
        )

    if res.status_code == 200:
        data = res.json()
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
        confidence = data["results"]["channels"][0]["alternatives"][0]["confidence"]
        print(f"\nTranscript: {transcript}")
        print(f"Confidence: {confidence:.2%}")
        print(f"[model: {model}]")
    else:
        print(f"ERROR {res.status_code}: {res.text}")


# ── TEST ELEVENLABS ───────────────────────────────────────────────────────────
def test_elevenlabs():
    print("\n" + "="*50)
    print("ELEVENLABS TTS TEST")
    print("="*50)

    voice_choice = pick("Choose voice", ELEVENLABS_VOICES)
    voice_id, voice_name = voice_choice if isinstance(voice_choice, tuple) else (voice_choice, "?")

    model_choice = pick("Choose ElevenLabs model", ELEVENLABS_MODELS)

    text = input("\nEnter text to speak (default: 'Hello, welcome to AllZone Medical Centre.'): ").strip()
    if not text:
        text = "Hello, welcome to AllZone Medical Centre. How can I help you today?"

    output_file = f"test_output_{voice_name.lower()}.mp3"

    print(f"\nVoice: {voice_name} ({voice_id})")
    print(f"Model: {model_choice}")
    print(f"Text: {text}")
    print("Generating audio...")

    with httpx.Client() as client:
        res = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": model_choice,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=30,
        )

    if res.status_code == 200:
        with open(output_file, "wb") as f:
            f.write(res.content)
        print(f"\nSaved to: {output_file}")
        print(f"Size: {len(res.content) / 1024:.1f} KB")
        os.system(f"afplay {output_file} 2>/dev/null || echo 'Play manually: {output_file}'")
    else:
        print(f"ERROR {res.status_code}: {res.text}")


# ── FULL PIPELINE ─────────────────────────────────────────────────────────────
def test_pipeline():
    print("\n" + "="*50)
    print("FULL PIPELINE TEST: Groq → ElevenLabs")
    print("="*50)

    groq_model    = pick("Choose Groq model", GROQ_MODELS)
    voice_choice  = pick("Choose ElevenLabs voice", ELEVENLABS_VOICES)
    voice_id, voice_name = voice_choice if isinstance(voice_choice, tuple) else (voice_choice, "?")
    el_model      = pick("Choose ElevenLabs model", ELEVENLABS_MODELS)

    user_input = input("\nWhat do you want to say to the bot? ").strip()
    if not user_input:
        user_input = "I want to book an appointment for tomorrow at 2pm"

    print(f"\n[1/2] Sending to Groq ({groq_model})...")

    system = (
        "You are James, a receptionist at AllZone Medical Centre. "
        "Reply in 1-2 short sentences only. Be friendly and helpful."
    )

    with httpx.Client() as client:
        groq_res = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": groq_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_input},
                ],
                "max_tokens": 150,
            },
            timeout=30,
        )

    if groq_res.status_code != 200:
        print(f"Groq ERROR: {groq_res.text}")
        return

    reply = groq_res.json()["choices"][0]["message"]["content"]
    print(f"Bot reply: {reply}")

    print(f"\n[2/2] Converting to speech ({voice_name}, {el_model})...")

    with httpx.Client() as client:
        el_res = client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": reply,
                "model_id": el_model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=30,
        )

    if el_res.status_code == 200:
        out = "pipeline_output.mp3"
        with open(out, "wb") as f:
            f.write(el_res.content)
        print(f"Audio saved: {out}")
        os.system(f"afplay {out} 2>/dev/null || echo 'Play manually: {out}'")
    else:
        print(f"ElevenLabs ERROR: {el_res.text}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def test_vapi_info():
    """Show current Vapi assistant info."""
    print("\n" + "="*50)
    print("VAPI ASSISTANT INFO")
    print("="*50)
    with httpx.Client() as client:
        res = client.get(
            f"https://api.vapi.ai/assistant/{VAPI_ASSISTANT_ID}",
            headers={"Authorization": f"Bearer {VAPI_API_KEY}"},
            timeout=15,
        )
    if res.status_code == 200:
        data = res.json()
        model = data.get("model", {})
        print(f"Name        : {data.get('name', '?')}")
        print(f"Provider    : {model.get('provider', '?')}")
        print(f"Model       : {model.get('model', '?')}")
        print(f"Voice       : {data.get('voice', {}).get('voiceId', '?')}")
        print(f"First Msg   : {data.get('firstMessage', '?')}")
    else:
        print(f"ERROR {res.status_code}: {res.text}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"\n[Engine: {VOICE_ENGINE.upper()}]  ← change in ai-service/.env VOICE_ENGINE=vapi/custom")

    if not cmd:
        print("\nVoice Pipeline Model Tester")
        if VOICE_ENGINE == "vapi":
            print("  1. Test Groq LLM")
            print("  2. Test Deepgram STT")
            print("  3. Test ElevenLabs TTS")
            print("  4. Full Pipeline (Groq + ElevenLabs)")
            print("  5. Vapi Assistant Info")
            print("\n  ⚡ Switch to custom: set VOICE_ENGINE=custom in ai-service/.env")
        else:
            print("  1. Test Groq LLM")
            print("  2. Test Deepgram STT")
            print("  3. Test ElevenLabs TTS")
            print("  4. Full Pipeline (Groq + ElevenLabs)")
            print("\n  ⚡ Switch to Vapi: set VOICE_ENGINE=vapi in ai-service/.env")

        choice = input("\nSelect: ").strip()
        cmd = {"1": "groq", "2": "deepgram", "3": "elevenlabs", "4": "pipeline", "5": "vapi"}.get(choice, "groq")

    if cmd == "groq":
        test_groq()
    elif cmd == "deepgram":
        test_deepgram(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "elevenlabs":
        test_elevenlabs()
    elif cmd == "pipeline":
        test_pipeline()
    elif cmd == "vapi":
        test_vapi_info()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python test_models.py [groq|deepgram|elevenlabs|pipeline|vapi]")


if __name__ == "__main__":
    main()
