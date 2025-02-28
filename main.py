import json
import re
import whisper
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
from huggingface_hub import InferenceClient
from pyngrok import ngrok
from typing import List
from email_config import send_email
import db
import os

# load environment variables
from dotenv import load_dotenv

load_dotenv()


# Initialize FastAPI app
app = FastAPI(
    title="Podcast Processing API",
    description="API for transcribing, summarizing, and generating quizzes from podcasts.",
    version="1.0.9"
)

# ---------------------------
# Global Configurations
# ---------------------------

# Load Whisper model for transcription
whisper_model = whisper.load_model("base")

# Hugging Face LLaMA API setup
MODEL_ID = "meta-llama/Llama-3.2-3B-Instruct"
HF_API_KEY = os.getenv("HF_API_KEY")

client = InferenceClient(api_key=HF_API_KEY)


# Directory to store uploaded files
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Store quizzes in memory
quiz_storage = {}

# ---------------------------
# Helper Functions
# ---------------------------
def sanitize_json_output(text: str) -> str:
    """
    Attempt to fix minor JSON formatting issues such as trailing commas
    or missing closing braces.
    """
    # Remove trailing commas in arrays or objects: ", }" or ", ]"
    sanitized = re.sub(r",(\s*[\]}])", r"\1", text.strip())

    # If it doesn't end with '}', try appending it (very naive approach)
    if not sanitized.endswith("}"):
        sanitized += "}"
    return sanitized

def transcribe_audio(audio_file_path: str) -> str:
    """Transcribes audio using Whisper."""
    result = whisper_model.transcribe(audio_file_path)
    return result["text"]

def generate_summary(transcript: str) -> str:
    """Summarizes a podcast transcript using LLaMA."""
    prompt = (
        "You are a helpful assistant who summarizes podcasts. "
        f"Summarize the following podcast transcript in a concise and informative manner:\n\n{transcript}"
    )
    
    messages = [{"role": "user", "content": prompt}]
    completion = client.chat.completions.create(
        model=MODEL_ID,
        messages=messages,
        max_tokens=500
    )

    summary = completion.choices[0].message.content

    return summary

def generate_key_takeaways(transcript: str) -> List[str]:
    """
    Extracts 3 to 5 key takeaways from the podcast transcript.
    The number of takeaways depends on the length of the transcript.
    """
    prompt = (
        "You are an AI that extracts key insights from podcast transcripts.\n"
        "Analyze the following transcript and provide **3 to 5 key takeaways** in bullet points.\n"
        "Ensure the takeaways are clear, concise, and informative.\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Your response should be in the format:\n"
        "- Key takeaway 1\n"
        "- Key takeaway 2\n"
        "- Key takeaway 3\n"
        "- (Optional) Key takeaway 4\n"
        "- (Optional) Key takeaway 5"
    )

    messages = [{"role": "user", "content": prompt}]
    completion = client.chat.completions.create(
        model=MODEL_ID,
        messages=messages,
        max_tokens=500
    )

    # Extract takeaways from response
    output_text = completion.choices[0].message.content.strip()
    takeaways = [line.strip("- ") for line in output_text.split("\n") if line.startswith("-")]

    return takeaways

    db.save_podcast_data(transcript, summary, takeaways, quiz)


def generate_quiz_question(text: str) -> dict:
    """
    Generates exactly one quiz question from the provided text, returning
    valid JSON with keys: 'question', 'options', 'correct_answer'.
    Enforces exactly 4 options if the model provides more.
    """
    # Build a strict prompt
    prompt = (
        "You are a helpful assistant. Create exactly one quiz question from the text below.\n\n"
        "Requirements:\n"
        "1. Provide EXACTLY 4 answer choices.\n"
        "2. Return ONLY valid JSON.\n"
        "3. Use the keys: question, options, correct_answer.\n"
        "4. DO NOT include trailing commas or any extra text.\n"
        "5. DO NOT omit the closing brace.\n\n"
        f"Text:\n{text}\n\n"
        "Your entire response MUST be valid JSON in this exact format:\n"
        "```\n"
        "{\n"
        "  \"question\": \"...\",\n"
        "  \"options\": [\"...\", \"...\", \"...\", \"...\"],\n"
        "  \"correct_answer\": \"...\"\n"
        "}\n"
        "```\n"
    )

    # Call the LLM
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )

    # Get the raw output text
    output_text = response.choices[0].message.content.strip()

    # Attempt to sanitize the JSON
    sanitized_output = sanitize_json_output(output_text)

    # Parse the JSON
    try:
        quiz = json.loads(sanitized_output)

        # If the model returns more than 4 options, truncate to 4
        if "options" in quiz and len(quiz["options"]) > 4:
            quiz["options"] = quiz["options"][:4]

        return quiz

    except json.JSONDecodeError:
        # If still invalid, log the raw text
        print(f"Error decoding response: {output_text}")
        return {}

def send_detail(transcript: str, summary: str):
    """Sends a daily email with one key takeaway from the latest podcast."""
    
    email_subject = "Detail from Podcast"
    email_body = f"Hello there! 🌞\n\n➡️ Transcript:\n\n{transcript}\n\n➡️ Summary:\n\n{summary}\n\nHave a great day! 🚀"
    
    send_email(email_subject, email_body)
    print("✅ Detail from Podcast sent.")

# ---------------------------
# API Models
# ---------------------------

class PodcastTranscript(BaseModel):
    transcript: str

class QuizRequest(BaseModel):
    transcript: str

class QuizAnswer(BaseModel):
    quiz_id: str
    answer: str



# ---------------------------
# API Endpoints
# ---------------------------

@app.post("/process-podcast", summary="Upload and process podcast", tags=["Process podcast"])
async def upload_audio(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())

        transcript = transcribe_audio(file_path)
        summary = generate_summary(transcript)
        takeaways = generate_key_takeaways(transcript)
        quiz = generate_quiz_question(transcript)

        send_detail("Podcast summary", summary)

        # Save to database
        db.save_podcast_data(transcript, summary, takeaways, quiz)

        return {
            "message": "Podcast processed and saved successfully!",
            "transcript": transcript,
            "summary": summary,
            "takeaways": takeaways,
            "quiz": quiz
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.post("/summarize", summary="Generate Podcast Summary", tags=["Summarization"])
async def summarize_podcast(data: PodcastTranscript):
    """API endpoint to generate a summary from a podcast transcript."""
    try:
        summary = generate_summary(data.transcript)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


# Example usage inside the existing API:
@app.post("/key-takeaways", summary="Generate key takeaways", tags=["Extract key takeaways"])
async def get_key_takeaways(data: PodcastTranscript):
    """API endpoint to generate key takeaways from a podcast transcript."""
    try:
        takeaways = generate_key_takeaways(data.transcript)
        if not takeaways:
            raise HTTPException(status_code=500, detail="Failed to extract key takeaways.")
        
        return {"takeaways": takeaways}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/generate-quiz", summary="Generate a Quiz Question", tags=["Generate quiz"])
async def api_quiz(data: QuizRequest):
    """Generates a single quiz question from the provided transcript."""
    try:
        quiz = generate_quiz_question(data.transcript)
        if not quiz:
            raise HTTPException(status_code=500, detail="Failed to generate quiz question.")

        quiz_id = str(len(quiz_storage) + 1)  # Assign a unique ID
        quiz_storage[quiz_id] = quiz  # Store the quiz

        return {"quiz_id": quiz_id, "quiz": quiz}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quiz generation failed: {str(e)}")

@app.post("/quiz/submit-answer", summary="Submit Quiz Answer", tags=["Quiz answer"])
async def submit_quiz_answer(data: QuizAnswer):
    """Validates the user's quiz answer and returns the result."""
    quiz = quiz_storage.get(data.quiz_id)
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found.")

    is_correct = data.answer.strip().lower() == quiz["correct_answer"].strip().lower()

    return {"quiz_id": data.quiz_id, "correct": is_correct, "correct_answer": quiz["correct_answer"]}



@app.get("/latest-podcast", summary="Get the latest podcast", tags=["Latest Podcast"])
async def get_latest_podcast():
    """API endpoint to get the latest podcast from the database."""
    try:
        podcast = db.get_latest_podcast_data()
        if not podcast:
            raise HTTPException(status_code=404, detail="Podcast not found.")
        return {"podcast": podcast}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    
@app.get("/podcasts/{podcast_id}", summary="Get a podcast by ID", tags=["Podcast by ID"])
async def get_podcast_by_id(podcast_id: int):
    """API endpoint to get a podcast by ID from the database."""
    try:
        podcast = db.get_podcast_by_id(podcast_id)
        if not podcast:
            raise HTTPException(status_code=404, detail="Podcast not found.")
        return {"podcast": podcast}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    
@app.post("/send-email", summary="Send Email", tags=["Send email"])
async def send_email_api(data: PodcastTranscript):
    """API endpoint to send an email with the provided transcript."""
    summary = generate_summary(data.transcript)
    try:
        send_detail(data.transcript, summary)
        return {"message": "Email sent successfully!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")



@app.get("/", summary="Root Endpoint", tags=["General"])
def read_root():
    """Root endpoint for checking API status."""
    return {"message": "Podcast Transcription API is running!", "version": "1.0.1"}





# ---------------------------
# Start Server with ngrok
# ---------------------------


if __name__ == "__main__":
    # Start FastAPI server in a separate thread
    from threading import Thread


    def run_fastapi():
        uvicorn.run(app, host="0.0.0.0", port=8000)


    server_thread = Thread(target=run_fastapi, daemon=True)
    server_thread.start()

    # Start ngrok tunnel
    NGROK_AUTH_TOKEN = "2sru6psoX0AepLbLWUjjU3tXTV7_3vPStVRxahP5yrocAjV8H"  # Replace with your actual ngrok auth token
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)

    public_url = ngrok.connect(8000).public_url
    print(f"🔗 Public API URL: {public_url}")

    # Keep the script running
    server_thread.join()

# ngrok http --url=amoeba-allowed-mostly.ngrok-free.app 80