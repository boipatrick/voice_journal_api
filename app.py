from fastapi import FastAPI, File, UploadFile, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import json
from pathlib import Path
import shutil
from typing import Optional
import uuid


load_dotenv()

app = FastAPI()

# Add CORS middleware with specific allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",  # Local development
        "https://voice-frontend-nine.vercel.app"  # Production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@app.get("/")
def read_root():
    return {"message": "API connected to Postgres!"}

# Azure Configuration
AZURE_API_KEY = os.getenv("AZURE_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
AZURE_TRANSCRIBE_DEPLOYMENT = os.getenv("AZURE_TRANSCRIBE_DEPLOYMENT")
AZURE_CHAT_DEPLOYMENT = os.getenv("AZURE_CHAT_DEPLOYMENT")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
API_VERSION = "2024-12-01-preview"

# Test Azure credentials
if not AZURE_API_KEY or not AZURE_ENDPOINT:
    raise ValueError("Missing required Azure configuration")

# Create storage directories
UPLOAD_DIR = Path("audio_storage")
TEXT_DIR = Path("text_storage")
UPLOAD_DIR.mkdir(exist_ok=True)
TEXT_DIR.mkdir(exist_ok=True)

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    try:
        # Validate file type
        allowed_types = [
            "audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg",
            "audio/m4a", "audio/mp4", "audio/x-m4a"
        ]
        
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Supported formats: mp3, wav, ogg, m4a"
            )
        
        # Generate unique filename
        file_id = str(uuid.uuid4())
        file_extension = file.filename.split(".")[-1]
        filename = f"{file_id}.{file_extension}"
        
        # Save file
        file_path = UPLOAD_DIR / filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return JSONResponse({
            "message": "Audio file uploaded successfully",
            "file_id": file_id,
            "filename": filename
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    



# Update the process_transcript function to use Azure for chat completion
async def process_with_azure_gpt(prompt: str, transcript: str):
    try:
        azure_url = f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_CHAT_DEPLOYMENT}/chat/completions"
        headers = {
            "api-key": AZURE_API_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant analyzing transcribed audio."},
                {"role": "user", "content": f"{prompt}\n\nTranscript: {transcript}"}
            ],
            "max_tokens": 800,
            "temperature": 0.7,
            "model": "gpt-4"  # or "gpt-35-turbo"
        }
        
        params = {"api-version": API_VERSION}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                azure_url,
                headers=headers,
                json=payload,
                params=params
            )
            
            print(f"Chat GPT Response Status: {response.status_code}")  # Debug logging
            print(f"Chat GPT Response Content: {response.text}")  # Debug logging
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Azure Chat API error: {response.text}"
                )
            
            result = response.json()
            return result["choices"][0]["message"]["content"]
        
    except Exception as e:
        print(f"Azure GPT error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-transcript/{file_id}")
async def process_transcript(file_id: str, prompt: str = "Please analyze this text and provide insights:"):
    try:
        # Find the audio file
        audio_files = list(UPLOAD_DIR.glob(f"{file_id}.*"))
        if not audio_files:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        audio_path = audio_files[0]
        
        # Get the actual file extension and mime type
        file_extension = audio_path.suffix.lower()
        mime_type = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.m4a': 'audio/x-m4a',
            '.ogg': 'audio/ogg'
        }.get(file_extension, 'audio/mpeg')

        # Step 1: Transcribe audio using Azure
        transcribe_url = f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_TRANSCRIBE_DEPLOYMENT}/audio/transcriptions"
        
        # Transcribe the audio with modified file upload format
        with open(audio_path, "rb") as audio_file:
            # Create multipart form data with proper file format
            data = audio_file.read()
            if not data:
                raise HTTPException(status_code=400, detail="Audio file is empty")
            audio_file.seek(0)
            files = {
                "file": (audio_path.name, audio_file, mime_type)
            }
            
            params = {"api-version": API_VERSION}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    transcribe_url,
                    headers={"api-key": AZURE_API_KEY},
                    files=files,
                    params=params
                )
                
                print(f"Azure Response Status: {response.status_code}")
                print(f"Azure Response Content: {response.text}")
                
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Azure Transcription API error: {response.text}"
                )
                
            transcription_result = response.json()
            transcript_text = transcription_result.get("text", "")

        # Step 2: Process the transcript with Azure GPT
        processed_text = await process_with_azure_gpt(prompt, transcript_text)
        
        # Save processed text
        text_file_path = TEXT_DIR / f"{file_id}_processed.txt"
        with open(text_file_path, "w", encoding="utf-8") as f:
            f.write(f"Original Transcript:\n\n{transcript_text}\n\nAnalysis:\n\n{processed_text}")
        
        return {
            "message": "Audio processed successfully",
            "file_id": file_id,
            "transcript": transcript_text,
            "analysis": processed_text
        }
    
    except Exception as e:
        print(f"Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-processed/{file_id}")
async def download_processed_text(file_id: str):
    try:
        file_path = TEXT_DIR / f"{file_id}_processed.txt"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Processed text file not found")
            
        return FileResponse(
            path=file_path,
            filename=f"processed_transcript_{file_id}.txt",
            media_type="text/plain"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))