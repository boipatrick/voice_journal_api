Product Requirements Document: Voice Journal Backend Implementation
1. Overview
The Voice Journal application requires backend enhancements to support audio transcription functionality with persistent storage. This document outlines the requirements for implementing PostgreSQL integration and completing the API endpoints needed by the frontend.

2. Core Requirements
Database Integration
Implement PostgreSQL storage using SQLAlchemy ORM
Store transcriptions with full text, segments, and metadata
Support historical retrieval of past transcriptions
API Endpoints
Complete missing endpoints required by frontend
Maintain consistent response format across all endpoints
Ensure proper error handling with descriptive messages
3. API Specification
Endpoint	Method	Purpose	Request	Response
/upload-audio	POST	Upload audio file	file (Form)	{file_id, filename, message}
/process-transcript/{file_id}	POST	Transcribe and analyze	{prompt} (optional)	{file_id, transcript, analysis}
/transcription/{id}	GET	Get single transcription	-	{id, title, created_at, summary, transcript:[{timestamp, text}]}
/transcriptions	GET	List all transcriptions	-	[{id, title, created_at, duration}]
4. Database Schema
Tables
Transcriptions

id (PK): String - Unique identifier
title: String - Filename or user-given title
audio_file_path: String - Path to stored audio file
transcript: Text - Full transcript text
summary: Text - AI-generated summary
created_at: DateTime - Creation timestamp
TranscriptionSegments

id (PK): Integer - Auto-increment ID
transcription_id (FK): String - Reference to parent transcription
timestamp: String - Timestamp in format "00:00"
text: Text - Segment text content
5. Implementation Plan
Phase 1: Database Setup
Configure SQLAlchemy with PostgreSQL connection
Create database models and relationships
Implement schema migration
Phase 2: Endpoint Implementation
Update /upload-audio endpoint to store in database
Enhance /process-transcript/{id} to update database records
Implement /transcription/{id} endpoint
Implement /transcriptions listing endpoint
Phase 3: Error Handling & Testing
Add comprehensive error handling
Implement CORS for frontend compatibility
Create test cases for each endpoint
6. Technical Requirements
Database: PostgreSQL on Railway
ORM: SQLAlchemy
API Framework: FastAPI
File Storage: Local with paths stored in DB
Authentication: None in initial phase (add later)
7. Success Criteria
Frontend can upload audio files successfully
Transcription processing works end-to-end
Transcription history is persistently stored
All API responses match frontend expectations
System handles errors gracefully
8. Future Considerations
User authentication and multi-user support
Cloud storage for audio files
Advanced transcript segmentation with accurate timestamps
Performance optimization for large audio files
This PRD provides a complete roadmap for implementing the necessary backend changes to support the Voice Journal application's frontend requirements.