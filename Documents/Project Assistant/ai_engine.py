import os
import whisper
import re
import requests
import PyPDF2
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

print("Loading AI Models... This will take a moment.")
whisper_model = whisper.load_model("base")
sum_tokenizer = AutoTokenizer.from_pretrained("facebook/bart-large-cnn")
sum_model = AutoModelForSeq2SeqLM.from_pretrained("facebook/bart-large-cnn")


def fetch_youtube_audio_api(youtube_url, output_path="temp_audio.mp3"):
    """
    Outsources extraction to RapidAPI to bypass local FFmpeg requirements.
    Uses the key provided by the user in image_a3703e.png.
    """
    video_id = youtube_url.split("v=")[-1].split("&")[0]
    api_url = "https://youtube-mp36.p.rapidapi.com/dl"
    querystring = {"id": video_id}

    headers = {
        "X-RapidAPI-Key": "1f9896df56msh9e0a09874c7eaefp13959djsn55cdde1c3fba",  # Your personal key
        "X-RapidAPI-Host": "youtube-mp36.p.rapidapi.com"
    }

    try:
        response = requests.get(api_url, headers=headers, params=querystring)
        response.raise_for_status()
        response_data = response.json()

        download_link = response_data.get("link")
        if not download_link:
            raise Exception("API failed to provide an audio link.")

        audio_data = requests.get(download_link)
        with open(output_path, 'wb') as f:
            f.write(audio_data.content)

        return output_path
    except Exception as e:
        raise Exception(f"Third-party extraction failed: {str(e)}")


def extract_text_from_file(file_path):
    text = ""
    if file_path.endswith('.pdf'):
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() + " "
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    return text.strip()


def generate_quiz(transcript):
    """Fulfills the Objective in Chapter 1 for automated review materials."""
    sentences = re.split(r'(?<=[.!?]) +', transcript)
    quiz = []

    for s in sentences:
        s = s.strip()
        if 8 < len(s.split()) < 35:
            if " is defined as " in s:
                parts = s.split(" is defined as ")
                quiz.append({"question": f"What is defined as {parts[1].strip('.?')}?", "answer": parts[0].strip()})
            elif " refers to " in s:
                parts = s.split(" refers to ")
                quiz.append({"question": f"What refers to {parts[1].strip('.?')}?", "answer": parts[0].strip()})

    if not quiz:  # Fallback quiz generation
        for s in sentences[:5]:
            if len(s.split()) > 10:
                words = s.split()
                blank_word = words[-2]
                question = s.replace(blank_word, "______")
                quiz.append({"question": f"Fill in the blank: {question}", "answer": blank_word})

    return quiz[:10]


def process_lecture(source_path, is_url=False, is_text=False):
    audio_path = "temp_audio.mp3"
    target_file = source_path
    transcript = ""

    try:
        if is_text:
            transcript = extract_text_from_file(source_path)
        else:
            if is_url:
                fetch_youtube_audio_api(source_path, audio_path)
                target_file = audio_path

            # Transcription using Whisper Base model
            result = whisper_model.transcribe(target_file)
            transcript = result["text"]

        # Summarization using BART
        summary = "Document too short for summary."
        if len(transcript) > 200:
            # Handling 1024-token limit via truncation
            inputs = sum_tokenizer(transcript[:1024], return_tensors="pt", max_length=1024, truncation=True)
            summary_ids = sum_model.generate(inputs["input_ids"], max_length=150, min_length=50, do_sample=False)
            summary = sum_tokenizer.decode(summary_ids[0], skip_special_tokens=True)

        quiz_data = generate_quiz(transcript)
        return {"transcript": transcript, "summary": summary, "quiz": quiz_data}

    finally:
        if is_url and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except:
                pass