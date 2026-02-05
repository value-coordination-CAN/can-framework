from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr

class UserOut(BaseModel):
    id: str
    display_name: str
    email: EmailStr

    class Config:
        from_attributes = True
