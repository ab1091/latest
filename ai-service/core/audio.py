"""Audio module — ElevenLabs removed. Twilio inbound now uses Vapi or <Say> fallback."""


async def warmup(phrases: list[str]) -> None:
    pass


async def synthesize(text: str):
    return None


def get_audio(audio_id: str) -> tuple:
    return None, "audio/mpeg"
