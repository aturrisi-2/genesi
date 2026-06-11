from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class Pet(BaseModel):
    type: str
    name: str
    breed: Optional[str] = None

class Child(BaseModel):
    name: str

class UserProfile(BaseModel):
    # Identity & metadata
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = None
    profession: Optional[str] = None
    spouse: Optional[str] = None
    
    # Collections
    pets: List[Pet] = Field(default_factory=list)
    children: List[Child] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)
    traits: List[str] = Field(default_factory=list)
    
    # Integration tokens
    google_token: Optional[Dict[str, Any]] = None
    
    # Metadata
    updated_at: Optional[datetime] = None
