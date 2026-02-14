from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Pet(BaseModel):
    type: str
    name: str

class Child(BaseModel):
    name: str

class UserProfile(BaseModel):
    name: Optional[str] = None
    profession: Optional[str] = None
    spouse: Optional[str] = None
    pets: List[Pet] = Field(default_factory=list)
    children: List[Child] = Field(default_factory=list)
    updated_at: Optional[datetime] = None
