from pydantic import BaseModel

class ScoreOut(BaseModel):
    user_id: str
    contribution_score: float
    reliability_score: float
    care_score: float
    overall_score: float
