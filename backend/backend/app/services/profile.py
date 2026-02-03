"""Profile service for user profile management."""

import logging
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.profile import UserProfile, ProfileUpdateRequest

logger = logging.getLogger(__name__)


async def get_user_profile(db: AsyncSession, user_id: str) -> Optional[UserProfile]:
    """
    Get user profile by user ID.

    Args:
        db: Database session
        user_id: User ID

    Returns:
        UserProfile object or None if user not found
    """
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User {user_id} not found")
            return None

        # Convert SQLAlchemy model to Pydantic model
        return UserProfile.model_validate(user)
    except Exception as e:
        logger.error(f"Error fetching profile for user {user_id}: {e}")
        raise


async def update_profile(
    db: AsyncSession,
    user_id: str,
    profile_update: ProfileUpdateRequest
) -> Optional[UserProfile]:
    """
    Update user profile display name.

    Args:
        db: Database session
        user_id: User ID
        profile_update: Profile update request with display_name

    Returns:
        Updated UserProfile object or None if user not found

    Raises:
        ValueError: If validation fails
    """
    try:
        # Verify user exists
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User {user_id} not found for profile update")
            return None

        # Update display name
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(display_name=profile_update.display_name)
        )
        await db.commit()

        # Fetch updated user
        result = await db.execute(select(User).where(User.id == user_id))
        updated_user = result.scalar_one()

        logger.info(f"Updated profile for user {user_id}")
        return UserProfile.model_validate(updated_user)

    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating profile for user {user_id}: {e}")
        raise


async def update_avatar_url(
    db: AsyncSession,
    user_id: str,
    avatar_url: Optional[str]
) -> None:
    """
    Update user's avatar URL.

    Args:
        db: Database session
        user_id: User ID
        avatar_url: New avatar URL or None to remove avatar
    """
    try:
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(avatar_url=avatar_url)
        )
        await db.commit()
        logger.info(f"Updated avatar URL for user {user_id}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating avatar URL for user {user_id}: {e}")
        raise
