from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    refresh_token: Optional[str] = None


class UserUpdate(BaseModel):
    refresh_token: Optional[str] = None
    folder_id: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    company_name: Optional[str] = None
    custom_prompt: Optional[str] = None


class UserResponse(UserBase):
    id: int
    folder_id: Optional[str] = None
    company_name: Optional[str] = None
    custom_prompt: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
