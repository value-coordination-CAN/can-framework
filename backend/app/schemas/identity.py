from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    email: EmailStr


class UserPublicOut(BaseModel):
    """What other people may see: no email."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str


class CareConsentIn(BaseModel):
    factors: list[str] = Field(default_factory=list, description="The complete set of care factors you consent to")


class CareConsentOut(BaseModel):
    consented_factors: list[str]
    available_factors: list[str]
    granted: list[str] = Field(default_factory=list)
    revoked: list[str] = Field(default_factory=list)
    entries_deleted: int = 0
