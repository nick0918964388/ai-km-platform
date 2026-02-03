"""Profile management API routes."""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.profile import UserProfile, ProfileUpdateRequest, AvatarUploadResponse
from app.services.profile import get_user_profile, update_profile, update_avatar_url
from app.services.avatar import process_avatar, delete_avatar, get_avatar_path
from app.services.dashboard import get_metrics, get_recent_activity, get_top_topics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["Profile"])


# TODO: Replace with JWT authentication middleware
def get_current_user_id() -> str:
    """
    Placeholder for authentication.
    In production, this should extract user_id from JWT token.
    """
    return "demo-user-123"


@router.get("", response_model=UserProfile)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Retrieve the authenticated user's profile information.

    Returns:
        UserProfile: User profile with display_name, email, avatar_url, account_level, timestamps

    Raises:
        HTTPException: 404 if user not found
    """
    try:
        profile = await get_user_profile(db, user_id)

        if not profile:
            raise HTTPException(
                status_code=404,
                detail=f"User profile not found for user_id: {user_id}"
            )

        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving profile for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while retrieving profile"
        )


@router.patch("", response_model=UserProfile)
async def update_user_profile(
    profile_update: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Update the authenticated user's profile display name.

    Args:
        profile_update: ProfileUpdateRequest with display_name (2-50 chars, required)

    Returns:
        UserProfile: Updated user profile

    Raises:
        HTTPException: 404 if user not found, 422 if validation fails
    """
    try:
        updated_profile = await update_profile(db, user_id, profile_update)

        if not updated_profile:
            raise HTTPException(
                status_code=404,
                detail=f"User profile not found for user_id: {user_id}"
            )

        return updated_profile
    except HTTPException:
        raise
    except ValueError as e:
        # Pydantic validation errors
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating profile for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while updating profile"
        )


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Upload a new avatar image for the authenticated user.

    Accepts JPG, PNG, or GIF files up to 5MB.
    Image will be automatically resized to 200x200px and converted to JPG.

    Args:
        file: Image file upload (multipart/form-data)

    Returns:
        AvatarUploadResponse: New avatar URL and success message

    Raises:
        HTTPException: 400 if validation fails, 404 if user not found, 500 on server error
    """
    try:
        # Read file content
        file_content = await file.read()

        # Process and save avatar
        avatar_url, filename = await process_avatar(
            user_id=user_id,
            file_content=file_content,
            filename=file.filename or "avatar.jpg"
        )

        # Get user's current avatar to delete old one
        current_profile = await get_user_profile(db, user_id)
        if current_profile and current_profile.avatar_url:
            # Delete old avatar (don't fail if deletion fails)
            await delete_avatar(current_profile.avatar_url)

        # Update user's avatar URL in database
        await update_avatar_url(db, user_id, avatar_url)

        logger.info(f"Avatar uploaded successfully for user {user_id}")
        return AvatarUploadResponse(
            avatar_url=avatar_url,
            message="Avatar uploaded successfully"
        )

    except ValueError as e:
        # Validation errors from avatar service
        raise HTTPException(status_code=400, detail=str(e))
    except IOError as e:
        # File processing errors
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error uploading avatar for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while uploading avatar"
        )


@router.delete("/avatar")
async def remove_avatar(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Remove the authenticated user's custom avatar and revert to account initials display.

    Returns:
        Success message

    Raises:
        HTTPException: 404 if user not found, 500 on server error
    """
    try:
        # Get user's current avatar
        current_profile = await get_user_profile(db, user_id)

        if not current_profile:
            raise HTTPException(
                status_code=404,
                detail=f"User profile not found for user_id: {user_id}"
            )

        if current_profile.avatar_url:
            # Delete avatar file
            await delete_avatar(current_profile.avatar_url)

            # Update database to remove avatar URL
            await update_avatar_url(db, user_id, None)

            logger.info(f"Avatar removed for user {user_id}")
            return {"message": "Avatar removed successfully"}
        else:
            return {"message": "No avatar to remove"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing avatar for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while removing avatar"
        )


# Dashboard endpoints
@router.get("/dashboard/metrics")
async def get_dashboard_metrics(
    refresh: bool = Query(False, description="Bypass cache and fetch fresh data"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get complete dashboard metrics for the authenticated user.

    Returns aggregated metrics:
    - Document count
    - Query count
    - Recent activity (last 20 entries)
    - Top topics (top 5)
    - User profile info

    Uses Redis caching with 60s TTL (unless refresh=True).

    Args:
        refresh: Optional boolean to bypass cache

    Returns:
        Dashboard metrics object

    Raises:
        HTTPException: 404 if user not found, 500 on server error
    """
    try:
        metrics = await get_metrics(db, user_id, refresh=refresh)
        return metrics

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching dashboard metrics for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching dashboard metrics"
        )


@router.get("/dashboard/activity")
async def get_dashboard_activity(
    limit: int = Query(20, ge=1, le=100, description="Number of activity entries to return"),
    offset: int = Query(0, ge=0, description="Number of entries to skip"),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get recent activity entries for the authenticated user with pagination.

    Args:
        limit: Maximum number of entries to return (1-100, default 20)
        offset: Number of entries to skip for pagination

    Returns:
        Activity timeline response with entries and pagination info

    Raises:
        HTTPException: 500 on server error
    """
    try:
        # Fetch activity (offset + limit to support pagination)
        all_activities = await get_recent_activity(user_id, limit=offset + limit)

        # Apply offset
        activities = all_activities[offset:offset + limit]

        return {
            "activities": activities,
            "total": len(all_activities),
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error fetching activity for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching activity"
        )


@router.get("/dashboard/topics")
async def get_dashboard_topics(
    limit: int = Query(5, ge=1, le=20, description="Number of top topics to return"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Get top searched topics for the authenticated user.

    Args:
        limit: Number of topics to return (1-20, default 5)

    Returns:
        Top topics response with query text and counts

    Raises:
        HTTPException: 500 on server error
    """
    try:
        topics = await get_top_topics(db, user_id, limit=limit)

        return {
            "topics": topics,
            "total": len(topics),
        }

    except Exception as e:
        logger.error(f"Error fetching top topics for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching top topics"
        )


# Static file serving endpoint (separate router to avoid /api/profile prefix)
avatar_router = APIRouter(prefix="/api/avatars", tags=["Avatars"])


@avatar_router.get("/{filename}")
async def serve_avatar(filename: str):
    """
    Serve avatar image files.

    No authentication required for public avatar access.

    Args:
        filename: Avatar filename

    Returns:
        FileResponse: Avatar image file

    Raises:
        HTTPException: 404 if file not found
    """
    file_path = get_avatar_path(filename)

    if not file_path:
        raise HTTPException(status_code=404, detail="Avatar not found")

    return FileResponse(
        path=file_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000",  # Cache for 1 year
        }
    )
