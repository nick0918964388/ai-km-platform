'use client';

import { useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getProfile, updateProfile as updateProfileApi } from '@/services/profileService';

/**
 * Hook for managing user profile state
 * Provides profile data, loading state, and update functions
 */
export function useProfile() {
  const profile = useStore((state) => state.profile);
  const profileLoading = useStore((state) => state.profileLoading);
  const profileError = useStore((state) => state.profileError);
  const setProfile = useStore((state) => state.setProfile);
  const updateProfile = useStore((state) => state.updateProfile);

  /**
   * Fetch user profile from API
   */
  const fetchProfile = useCallback(async () => {
    useStore.setState({ profileLoading: true, profileError: null });

    try {
      const fetchedProfile = await getProfile();
      setProfile(fetchedProfile);
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Failed to fetch profile';
      useStore.setState({ profileError: errorMessage });
      console.error('Error fetching profile:', error);
    } finally {
      useStore.setState({ profileLoading: false });
    }
  }, [setProfile]);

  /**
   * Update user profile display name with optimistic updates
   * @param displayName - New display name
   */
  const updateDisplayName = useCallback(
    async (displayName: string) => {
      if (!profile) {
        throw new Error('No profile loaded');
      }

      // Store previous profile for rollback
      const previousProfile = { ...profile };

      // Optimistic update
      updateProfile({ display_name: displayName });
      useStore.setState({ profileLoading: true, profileError: null });

      try {
        const updatedProfile = await updateProfileApi(displayName);
        setProfile(updatedProfile);
      } catch (error) {
        // Rollback on error
        setProfile(previousProfile);
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to update profile';
        useStore.setState({ profileError: errorMessage });
        console.error('Error updating profile:', error);
        throw error; // Re-throw so caller can handle
      } finally {
        useStore.setState({ profileLoading: false });
      }
    },
    [profile, setProfile, updateProfile]
  );

  /**
   * Refresh profile data
   */
  const refreshProfile = useCallback(async () => {
    await fetchProfile();
  }, [fetchProfile]);

  return {
    profile,
    profileLoading,
    profileError,
    fetchProfile,
    updateDisplayName,
    refreshProfile,
  };
}
