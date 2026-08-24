"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    expiration_date: str = Field(..., description="Required, format YYYY-MM-DD")
    start_date: Optional[str] = Field(None, description="Optional, format YYYY-MM-DD")


def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Validate that the given username belongs to a signed in teacher/admin."""
    if not teacher_username:
        raise HTTPException(
            status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401, detail="Invalid teacher credentials")

    return teacher


def _validate_dates(start_date: Optional[str], expiration_date: str) -> None:
    """Ensure dates are well formed and start_date is not after expiration_date."""
    try:
        expiration = datetime.strptime(expiration_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400, detail="expiration_date must be in YYYY-MM-DD format")

    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="start_date must be in YYYY-MM-DD format")

        if start > expiration:
            raise HTTPException(
                status_code=400, detail="start_date must be on or before expiration_date")


def _serialize(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": announcement["_id"],
        "message": announcement["message"],
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement["expiration_date"],
        "created_by": announcement.get("created_by"),
        "created_at": announcement.get("created_at"),
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get all currently active announcements for public display (no auth required)"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": today}},
        ],
    }

    return [_serialize(a) for a in announcements_collection.find(query)]


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements - requires teacher authentication"""
    _require_teacher(teacher_username)

    announcements = announcements_collection.find().sort("expiration_date", 1)
    return [_serialize(a) for a in announcements]


@router.post("")
@router.post("/")
def create_announcement(announcement: AnnouncementInput, teacher_username: Optional[str] = Query(None)):
    """Create a new announcement - requires teacher authentication"""
    _require_teacher(teacher_username)
    _validate_dates(announcement.start_date, announcement.expiration_date)

    new_announcement = {
        "_id": str(uuid.uuid4()),
        "message": announcement.message,
        "start_date": announcement.start_date,
        "expiration_date": announcement.expiration_date,
        "created_by": teacher_username,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    announcements_collection.insert_one(new_announcement)
    return _serialize(new_announcement)


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementInput,
    teacher_username: Optional[str] = Query(None)
):
    """Update an existing announcement - requires teacher authentication"""
    _require_teacher(teacher_username)
    _validate_dates(announcement.start_date, announcement.expiration_date)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated_fields = {
        "message": announcement.message,
        "start_date": announcement.start_date,
        "expiration_date": announcement.expiration_date,
    }

    announcements_collection.update_one(
        {"_id": announcement_id}, {"$set": updated_fields})

    existing.update(updated_fields)
    return _serialize(existing)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: Optional[str] = Query(None)):
    """Delete an announcement - requires teacher authentication"""
    _require_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
