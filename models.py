from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base

class Transcription(Base):
    __tablename__ = "transcriptions"
    
    id = Column(String, primary_key=True)
    title = Column(String)
    audio_file_path = Column(String)
    transcript = Column(Text)
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    audio_data = Column(LargeBinary)  # Store the actual audio data
    audio_mime_type = Column(String)  # Store mime type
    
    # Relationship with segments
    segments = relationship("TranscriptionSegment", back_populates="transcription", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "transcript": self.transcript,
            "summary": self.summary
        }
    
    def to_list_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "duration": self.get_duration()
        }
    
    def get_duration(self):
        # Get the last segment timestamp or return "00:00" if no segments
        if not self.segments:
            return "00:00"
        last_segment = max(self.segments, key=lambda s: self.parse_timestamp(s.timestamp))
        return last_segment.timestamp
    
    @staticmethod
    def parse_timestamp(timestamp):
        # Convert timestamp string like "00:00" to seconds
        minutes, seconds = map(int, timestamp.split(':'))
        return minutes * 60 + seconds


class TranscriptionSegment(Base):
    __tablename__ = "transcription_segments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transcription_id = Column(String, ForeignKey("transcriptions.id"))
    timestamp = Column(String)  # Format: "00:00"
    text = Column(Text)
    
    # Relationship with parent
    transcription = relationship("Transcription", back_populates="segments")
    
    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "text": self.text
        }