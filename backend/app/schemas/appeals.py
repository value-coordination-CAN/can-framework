from pydantic import BaseModel, Field

class AppealCreate(BaseModel):
    user_id: str
    request_id: str
    reason: str = Field(..., min_length=1, max_length=5000)

class AppealOut(BaseModel):
    id: str
    user_id: str
    request_id: str
    reason: str
    status: str

    class Config:
        from_attributes = True
