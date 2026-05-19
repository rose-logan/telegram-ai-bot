import re
import ollama
import whisper
from config import OLLAMA_MODEL

# Загружаем модель Whisper в память один раз при старте (base — оптимально по скорости/качеству)
print("⏳ Загружаю локальную модель Whisper для распознавания голоса...")
whisper_model = whisper.load_model("base")

def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'@\S+', '', text)
    return text.strip()

def ask_local_ai(prompt_text: str) -> str:
    if not prompt_text: return "Без описания"
    try:
        response = ollama.generate(
            model=OLLAMA_MODEL,
            prompt=f"Ты — эксперт по Reels/TikTok. На основе текста: '{prompt_text}' напиши хайповый вовлекающий текст с 3-5 тегами на русском.",
            options={"num_predict": 300}
        )
        return response['response'].strip()
    except Exception as e:
        return clean_text(prompt_text)

def transcribe_voice_to_text(audio_path: str) -> str:
    try:
        print(f"🎙 Распознаю аудиофайл: {audio_path}")
        result = whisper_model.transcribe(audio_path, language="ru")
        raw_text = result["text"].strip()
        
        if not raw_text:
            return "❌ Не удалось разобрать слова в аудиосообщении."
            
        # Запрос к Qwen с жестким ограничением на длину ответа (options)
        response = ollama.generate(
            model=OLLAMA_MODEL,
            prompt=(
                f"Перед тобой текстовая расшифровка голосового сообщения: '{raw_text}'. "
                f"Сделай из неё короткий, красивый, структурированный текстовый пост для соцсетей. "
                f"Разбей на небольшие абзацы, добавь эмодзи. Пиши строго по сути, без лишней воды."
            ),
            options={
                "num_predict": 250,  # Уменьшаем лимит, чтобы ИИ физически не мог писать длинные сказки
                "temperature": 0.1,  # Минимальная температура делает ИИ максимально точным и запрещает фантазировать
                "top_p": 0.1
            }
        )
        return f"📝 **Расшифровка ГС (Обработано ИИ):**\n\n{response['response'].strip()}"
    except Exception as e:
        return f"❌ Ошибка распознавания голоса: {e}"
