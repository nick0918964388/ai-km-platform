# Quickstart Guide: Profile Settings & Dashboard

**Feature**: 009-profile-dashboard
**Date**: 2026-02-03
**For**: Developers implementing this feature

## Overview

This guide provides step-by-step instructions to implement and test the Profile Settings & Dashboard feature. Follow these steps in order to set up your development environment, implement the feature, and verify functionality.

---

## Prerequisites

Before starting, ensure you have:

- ✅ Python 3.10+ installed
- ✅ Node.js 20+ installed
- ✅ Backend and frontend development environments set up (per main README.md)
- ✅ SQLite database initialized
- ✅ Qdrant instance running (for activity logs)
- ✅ Redis instance running (for caching)
- ✅ Existing authentication system functional

---

## Step 1: Database Migration

Run the database migration to add profile fields to the users table.

```bash
# Navigate to backend directory
cd backend

# Create migration file
cat > migrations/add_profile_fields.sql << 'EOF'
-- Add profile fields to users table
ALTER TABLE users ADD COLUMN display_name VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255) NULL;
ALTER TABLE users ADD COLUMN account_level VARCHAR(20) NOT NULL DEFAULT 'free';
ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_id ON users(id);
EOF

# Run migration (adjust command based on your migration tool)
sqlite3 data/database.db < migrations/add_profile_fields.sql

# Verify migration
sqlite3 data/database.db "PRAGMA table_info(users);"
```

Expected output should include new columns: `display_name`, `avatar_url`, `account_level`, `created_at`, `updated_at`.

---

## Step 2: Create Storage Directory

Create the directory for avatar image storage.

```bash
# Navigate to repository root
cd ..

# Create storage directory
mkdir -p storage/avatars

# Add .gitkeep to track empty directory
touch storage/avatars/.gitkeep

# Set permissions (ensure web server can write)
chmod 755 storage/avatars
```

---

## Step 3: Install Backend Dependencies

Install Pillow for image processing.

```bash
cd backend

# Add Pillow to requirements.txt (if not already present)
echo "Pillow==10.2.0" >> requirements.txt

# Install dependencies
pip install -r requirements.txt

# Verify Pillow installation
python -c "from PIL import Image; print(Image.__version__)"
```

---

## Step 4: Backend Implementation

### 4.1 Create Pydantic Models

Create `backend/app/models/profile.py`:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str = Field(..., min_length=2, max_length=50)
    avatar_url: Optional[str] = None
    account_level: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=50)

    @validator('display_name')
    def validate_display_name(cls, v):
        if not v.strip():
            raise ValueError('Display name cannot be empty')
        return v.strip()

class DashboardMetrics(BaseModel):
    user_id: str
    document_count: int
    query_count: int
    account_level: str
    created_at: datetime
    recent_activity: list
    top_topics: list
```

### 4.2 Create Services

Create `backend/app/services/avatar.py`:

```python
from PIL import Image
import os
import time
from fastapi import UploadFile, HTTPException

AVATAR_DIR = "./storage/avatars"
MAX_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_FORMATS = {"JPEG", "PNG", "GIF"}
OUTPUT_SIZE = (200, 200)

async def process_avatar(user_id: str, file: UploadFile) -> str:
    # Validate file size
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)

    if size > MAX_SIZE:
        raise HTTPException(400, "File size exceeds 5MB limit")

    # Read and validate image
    try:
        img = Image.open(file.file)
        if img.format not in ALLOWED_FORMATS:
            raise HTTPException(400, f"Invalid format. Allowed: {ALLOWED_FORMATS}")
    except Exception as e:
        raise HTTPException(400, f"Invalid or corrupted image file: {str(e)}")

    # Resize and convert to JPEG
    img = img.convert("RGB")  # Ensure RGB mode
    img.thumbnail(OUTPUT_SIZE, Image.Resampling.LANCZOS)

    # Generate filename
    timestamp = int(time.time())
    filename = f"{user_id}_{timestamp}.jpg"
    filepath = os.path.join(AVATAR_DIR, filename)

    # Save processed image
    img.save(filepath, "JPEG", quality=85, optimize=True)

    return f"/api/avatars/{filename}"

def delete_avatar(avatar_url: str) -> None:
    if avatar_url and avatar_url.startswith("/api/avatars/"):
        filename = avatar_url.split("/")[-1]
        filepath = os.path.join(AVATAR_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
```

Create `backend/app/services/profile.py` and `backend/app/services/dashboard.py` following similar patterns (refer to data-model.md and contracts).

### 4.3 Create Router

Create `backend/app/routers/profile.py`:

```python
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.models.profile import UserProfile, ProfileUpdateRequest, DashboardMetrics
from app.services import profile as profile_service
from app.services import avatar as avatar_service
from app.services import dashboard as dashboard_service
# Import your auth dependency
# from app.auth import get_current_user

router = APIRouter(prefix="/api", tags=["profile"])

@router.get("/profile", response_model=UserProfile)
async def get_profile(user_id: str = Depends(get_current_user)):
    return await profile_service.get_user_profile(user_id)

@router.patch("/profile", response_model=UserProfile)
async def update_profile(
    request: ProfileUpdateRequest,
    user_id: str = Depends(get_current_user)
):
    return await profile_service.update_profile(user_id, request)

@router.post("/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    avatar_url = await avatar_service.process_avatar(user_id, file)
    await profile_service.update_avatar_url(user_id, avatar_url)
    return {"avatarUrl": avatar_url, "message": "Avatar uploaded successfully"}

@router.delete("/profile/avatar")
async def delete_avatar(user_id: str = Depends(get_current_user)):
    profile = await profile_service.get_user_profile(user_id)
    if profile.avatar_url:
        avatar_service.delete_avatar(profile.avatar_url)
        await profile_service.update_avatar_url(user_id, None)
    return {"message": "Avatar removed successfully"}

@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def get_dashboard_metrics(
    refresh: bool = False,
    user_id: str = Depends(get_current_user)
):
    return await dashboard_service.get_metrics(user_id, refresh)
```

### 4.4 Register Router

Add to `backend/app/main.py`:

```python
from app.routers import profile

app.include_router(profile.router)
```

---

## Step 5: Frontend Implementation

### 5.1 Create Types

Create `frontend/src/types/profile.ts`:

```typescript
export interface UserProfile {
  id: string;
  email: string;
  displayName: string;
  avatarUrl: string | null;
  accountLevel: 'free' | 'pro' | 'enterprise';
  createdAt: string;
  updatedAt: string;
}

export interface DashboardMetrics {
  userId: string;
  documentCount: number;
  queryCount: number;
  accountLevel: string;
  createdAt: string;
  recentActivity: ActivityEntry[];
  topTopics: TopicEntry[];
}

export interface ActivityEntry {
  actionType: 'document_upload' | 'query' | 'profile_update';
  timestamp: string;
  metadata: Record<string, any>;
}

export interface TopicEntry {
  queryText: string;
  count: number;
}
```

### 5.2 Create Services

Create `frontend/src/services/profileService.ts`:

```typescript
import { UserProfile } from '@/types/profile';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

export const profileService = {
  async getProfile(): Promise<UserProfile> {
    const response = await fetch(`${API_BASE}/profile`, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
    });
    if (!response.ok) throw new Error('Failed to fetch profile');
    return response.json();
  },

  async updateProfile(displayName: string): Promise<UserProfile> {
    const response = await fetch(`${API_BASE}/profile`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ displayName }),
    });
    if (!response.ok) throw new Error('Failed to update profile');
    return response.json();
  },

  async uploadAvatar(file: File): Promise<{ avatarUrl: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/profile/avatar`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
      body: formData,
    });
    if (!response.ok) throw new Error('Failed to upload avatar');
    return response.json();
  },

  async deleteAvatar(): Promise<void> {
    const response = await fetch(`${API_BASE}/profile/avatar`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
      },
    });
    if (!response.ok) throw new Error('Failed to delete avatar');
  },
};
```

### 5.3 Create Components

Create components following the structure in plan.md:
- `frontend/src/components/profile/ProfileForm.tsx`
- `frontend/src/components/profile/AvatarUploader.tsx`
- `frontend/src/components/profile/AccountInitials.tsx`
- `frontend/src/components/dashboard/MetricsCard.tsx`
- `frontend/src/components/dashboard/ActivityTimeline.tsx`
- `frontend/src/components/dashboard/TopTopics.tsx`

### 5.4 Create Pages

Create `frontend/src/app/profile/page.tsx`:

```typescript
'use client';

import { useEffect } from 'react';
import ProfileForm from '@/components/profile/ProfileForm';
import { useProfile } from '@/hooks/useProfile';

export default function ProfilePage() {
  const { profile, loading, error, fetchProfile } = useProfile();

  useEffect(() => {
    fetchProfile();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold mb-6">Profile Settings</h1>
      {profile && <ProfileForm profile={profile} />}
    </div>
  );
}
```

Create `frontend/src/app/dashboard/page.tsx` similarly.

---

## Step 6: Testing

### 6.1 Manual Testing Checklist

**Profile Settings:**
- [ ] Navigate to `/profile` and verify profile loads
- [ ] Update display name (2-50 chars) and verify save works
- [ ] Upload avatar (JPG, <5MB) and verify preview + save
- [ ] Upload invalid file (GIF, >5MB) and verify error messages
- [ ] Remove avatar and verify fallback to initials
- [ ] Check avatar displays throughout app after update

**Dashboard:**
- [ ] Navigate to `/dashboard` and verify metrics load
- [ ] Verify document count matches actual count
- [ ] Verify query count matches actual count
- [ ] Verify recent activity shows last 10-20 actions
- [ ] Verify top topics show correct counts
- [ ] Test empty state (new user with no data)

### 6.2 API Testing with cURL

```bash
# Get profile
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/profile

# Update profile
curl -X PATCH -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"displayName":"Jane Doe"}' \
  http://localhost:8000/api/profile

# Upload avatar
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/avatar.jpg" \
  http://localhost:8000/api/profile/avatar

# Get dashboard metrics
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/dashboard/metrics
```

---

## Step 7: Verification

### 7.1 Check Database

```bash
sqlite3 data/database.db "SELECT id, display_name, avatar_url, account_level FROM users LIMIT 5;"
```

### 7.2 Check File Storage

```bash
ls -lh storage/avatars/
```

### 7.3 Check Redis Cache

```bash
redis-cli KEYS "dashboard:*"
redis-cli GET "dashboard:YOUR_USER_ID"
```

---

## Troubleshooting

### Avatar Upload Fails

**Symptom**: 500 error on avatar upload

**Solution**:
1. Check `storage/avatars/` directory exists and has write permissions
2. Verify Pillow is installed: `pip list | grep Pillow`
3. Check backend logs for detailed error message

### Dashboard Shows Empty Metrics

**Symptom**: All counts are 0

**Solution**:
1. Verify activity logs exist in Qdrant: Check collection `activity_logs`
2. Verify queries table has data: `sqlite3 data/database.db "SELECT COUNT(*) FROM queries;"`
3. Check Redis connection: `redis-cli PING`

### Display Name Not Updating

**Symptom**: Display name changes but doesn't reflect in UI

**Solution**:
1. Clear Zustand store: `useStore.getState().reset()`
2. Verify API response includes updated `updatedAt` timestamp
3. Check browser console for errors

---

## Next Steps

After completing this quickstart:

1. ✅ Run `/speckit.tasks` to generate task breakdown
2. ✅ Implement tests (optional, based on feature spec)
3. ✅ Update navigation to include Profile and Dashboard links
4. ✅ Test responsive design on mobile/tablet devices
5. ✅ Create PR and request code review

---

## Reference

- **Feature Spec**: [spec.md](./spec.md)
- **Implementation Plan**: [plan.md](./plan.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Contracts**: [contracts/](./contracts/)
- **Research**: [research.md](./research.md)
