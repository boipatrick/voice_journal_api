from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import json
from pathlib import Path
import shutil
from typing import Optional, List
import uuid
import datetime
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text

#Database components
from database import get_db, create_tables
from models import Transcription, TranscriptionSegment



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

@app.on_event("startup")
def startup_db_client():
    create_tables()
    print("Database tables created!")





@app.get("/")
def read_root():
    return {"message": "API connected to Postgres!"}

# Azure Configuration
AZURE_API_KEY = os.getenv("AZURE_API_KEY")
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
AZURE_TRANSCRIBE_DEPLOYMENT = os.getenv("AZURE_TRANSCRIBE_DEPLOYMENT")
AZURE_CHAT_DEPLOYMENT = os.getenv("AZURE_CHAT_DEPLOYMENT")

API_VERSION = "2024-12-01-preview"

# Test Azure credentials
if not AZURE_API_KEY or not AZURE_ENDPOINT:
    raise ValueError("Missing required Azure configuration")



@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...), db: Session = Depends(get_db)):
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
        file_extension = Path(file.filename).suffix
        unique_filename = f"{file_id}{file_extension}"
        
        # Read file data
        file_data = await file.read()
        
        # Create initial database record with placeholder title
        title = f"New Recording {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        transcription = Transcription(
            id=file_id,
            title=title,
            audio_file_path=file.filename,  # Store original filename
            audio_data=file_data,  # Store binary data
            audio_mime_type=file.content_type,
            transcript="",
            summary=""
        )
        db.add(transcription)
        db.commit()
            
        return JSONResponse({
            "message": "Audio file uploaded successfully",
            "file_id": file_id,
            "filename": file.filename
        })
    
    except Exception as e:
        if 'db' in locals():
            db.rollback()
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
async def process_transcript(
    file_id: str, 
    title: Optional[str] = None,
    prompt: str = "Please analyze this text and provide insights:",
    db: Session = Depends(get_db)
):
    try:
        # Find the transcription in database
        transcription = db.query(Transcription).filter(Transcription.id == file_id).first()
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        if title:
            transcription.title = title
        
        # Create temporary file for processing
        temp_file = Path(f"temp_{file_id}")
        try:
            # Write audio data to temp file
            with open(temp_file, "wb") as f:
                f.write(transcription.audio_data)
            
            # Get MIME type for the Azure API
            mime_type = transcription.audio_mime_type
            
            # Process with Azure Whisper
            transcribe_url = f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_TRANSCRIBE_DEPLOYMENT}/audio/transcriptions"
            
            with open(temp_file, "rb") as audio_file:
                files = {
                    "file": (transcription.audio_file_path, audio_file, mime_type)
                }
                
                params = {"api-version": API_VERSION}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        transcribe_url,
                        headers={"api-key": AZURE_API_KEY},
                        files=files,
                        params=params
                    )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Azure Transcription API error: {response.text}"
                    )
                
                transcription_result = response.json()
                transcript_text = transcription_result.get("text", "")
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
        
        # Process transcript with Azure GPT
        processed_text = await process_with_azure_gpt(prompt, transcript_text)
        
        # Save results to database
        transcription.transcript = transcript_text
        transcription.summary = processed_text
        
        # Create segments based on sentences
        import re
        # Delete existing segments
        db.query(TranscriptionSegment).filter(TranscriptionSegment.transcription_id == file_id).delete()
        
        # Create basic segmentation (one segment per sentence)
        sentences = re.split(r'(?<=[.!?])\s+', transcript_text)
        total_chars = len(transcript_text)
        
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            
            # Calculate approximate timestamp based on position in text
            position = transcript_text.find(sentence) / total_chars if total_chars > 0 else 0
            # Assuming 3-minute audio on average - adjust as needed
            minutes = int(position * 3)
            seconds = int((position * 3 * 60) % 60)
            timestamp = f"{minutes:02d}:{seconds:02d}"
            
            segment = TranscriptionSegment(
                transcription_id=file_id,
                timestamp=timestamp,
                text=sentence.strip()
            )
            db.add(segment)
        
        db.commit()
        
        return {
            "message": "Audio processed successfully",
            "file_id": file_id,
            "title": transcription.title,
            "transcript": transcript_text,
            "analysis": processed_text
        }
    
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        print(f"Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-processed/{file_id}")
async def download_summary(file_id: str, db: Session = Depends(get_db)):
    try:
        # Get transcription from database
        transcription = db.query(Transcription).filter(Transcription.id == file_id).first()
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
            
        # Generate the summary content from database fields
        content = f"# {transcription.title}\n\n"
        content += "## Transcript\n\n"
        content += transcription.transcript + "\n\n"
        content += "## Analysis\n\n"
        content += transcription.summary
        
        # Create a temporary file to serve
        temp_file = Path(f"temp_summary_{file_id}.txt")
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            # Return the file as a download
            return FileResponse(
                path=temp_file,
                media_type="text/plain",
                filename=f"{transcription.title.replace(' ', '_')}_summary.txt"
            )
        finally:
            # We'll let FastAPI clean up after sending
            pass
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# Add these endpoints to your app.py file

@app.get("/transcriptions")
def get_transcriptions(db: Session = Depends(get_db)):
    """Get all transcriptions"""
    try:
        transcriptions = db.query(Transcription).order_by(Transcription.created_at.desc()).all()
        return [transcription.to_list_dict() for transcription in transcriptions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transcription/{id}")
def get_transcription(id: str, db: Session = Depends(get_db)):
    """Get a specific transcription by ID"""
    try:
        transcription = db.query(Transcription).filter(Transcription.id == id).first()
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        return transcription.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/transcription/{id}")
def delete_transcription(id: str, db: Session = Depends(get_db)):
    """Delete a transcription by ID"""
    try:
        transcription = db.query(Transcription).filter(Transcription.id == id).first()
        if not transcription:
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        # Delete from database (cascade will delete segments)
        db.delete(transcription)
        db.commit()
        
        return {"message": "Transcription deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/audio/{file_id}")
async def stream_audio(file_id: str, db: Session = Depends(get_db)):
    """Stream audio file from database"""
    try:
        # Get transcription from database
        transcription = db.query(Transcription).filter(Transcription.id == file_id).first()
        if not transcription or not transcription.audio_data:
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Create a temporary file to serve
        temp_file = Path(f"temp_{file_id}")
        try:
            with open(temp_file, "wb") as f:
                f.write(transcription.audio_data)
            
            # Return the file with proper content type
            return FileResponse(
                path=temp_file,
                media_type=transcription.audio_mime_type,
                filename=transcription.audio_file_path
            )
        finally:
            # FileResponse will handle cleanup
            pass
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 




@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    try:
        # Use text() to wrap the SQL query
        result = db.execute(text("SELECT 1")).fetchone()
        
        # For checking tables
        tables = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).fetchall()
        table_names = [table[0] for table in tables]
        
        return {
            "status": "Connected", 
            "result": result[0],
            "tables": table_names
        }
    except Exception as e:
        return {"status": "Error", "message": str(e)}

@app.get("/update-schema")
def update_schema(db: Session = Depends(get_db)):
    """Add missing columns to transcriptions table"""
    try:
        # Check if columns already exist
        columns_query = """
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'transcriptions' AND column_name IN ('audio_data', 'audio_mime_type')
        """
        existing_columns = [col[0] for col in db.execute(text(columns_query)).fetchall()]
        
        # Add audio_data column if missing
        if 'audio_data' not in existing_columns:
            db.execute(text("ALTER TABLE transcriptions ADD COLUMN audio_data BYTEA"))
        
        # Add audio_mime_type column if missing
        if 'audio_mime_type' not in existing_columns:
            db.execute(text("ALTER TABLE transcriptions ADD COLUMN audio_mime_type VARCHAR"))
        
        db.commit()
        return {"message": "Database schema updated successfully"}
    except Exception as e:
        db.rollback()
        return {"status": "Error", "message": str(e)}
