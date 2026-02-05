from pydantic import BaseModel, Field

class APIMessage(BaseModel):
    message: str = Field(..., examples=["ok"])
