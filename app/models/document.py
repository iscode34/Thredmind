from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentResponse(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: Optional[str] = None
    summary: Optional[str] = None
    entities_json: Optional[dict] = None
    keywords: Optional[list[str]] = None
    word_count: int = 0
    created_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
