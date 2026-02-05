from pydantic import BaseModel, Field

class AllocationRequestCreate(BaseModel):
    user_id: str
    pool: str = Field(..., pattern="^(housing|transport|food|energy|learning)$")
    description: str = Field(..., min_length=1, max_length=5000)

class AllocationRequestOut(BaseModel):
    id: str
    user_id: str
    pool: str
    description: str
    status: str
    priority_score: float | None

    class Config:
        from_attributes = True
