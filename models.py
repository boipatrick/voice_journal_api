from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class Transcription(Base):
    __tablename__ = "transcriptions"
    
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    audio_file_path = Column(String)
    audio_data = Column(LargeBinary)  # Store audio file as binary
    audio_mime_type = Column(String)  # Store MIME type (e.g., audio/mpeg)
    transcript = Column(Text)
    summary = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to segments
    segments = relationship("TranscriptionSegment", back_populates="transcription", cascade="all, delete-orphan")
    
    def to_dict(self):
        """Return full transcription with segments for detail view"""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "summary": self.summary or "",
            "transcript": [
                {
                    "timestamp": segment.timestamp,
                    "text": segment.text
                }
                for segment in self.segments
            ]
        }
    
    def to_list_dict(self):
        """Return condensed info for list view"""
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "duration": "00:00"  # You can calculate this if needed
        }


class TranscriptionSegment(Base):
    __tablename__ = "transcription_segments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    transcription_id = Column(String, ForeignKey("transcriptions.id", ondelete="CASCADE"))
    timestamp = Column(String)
    text = Column(Text)
    
    # Relationship back to transcription
    transcription = relationship("Transcription", back_populates="segments")