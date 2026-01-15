import {
  signInAnonymously,
  updateProfile,
  User,
  onAuthStateChanged,
} from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { auth, db } from "./firebase";
import { UserProfile } from "./types";

/**
 * Sign in a user anonymously with a nickname.
 * If the user is already signed in anonymously, just updates their display name.
 * If the user is signed in with a real account, returns the existing user.
 */
export async function signInAsGuest(nickname: string): Promise<User> {
  // Check current auth state
  const currentUser = auth.currentUser;

  if (currentUser) {
    // User is already signed in
    if (currentUser.isAnonymous) {
      // Update display name for anonymous user
      await updateProfile(currentUser, { displayName: nickname });
    }
    return currentUser;
  }

  // Sign in anonymously
  const credential = await signInAnonymously(auth);
  const user = credential.user;

  // Set display name
  await updateProfile(user, { displayName: nickname });

  return user;
}

/**
 * Check if the current user is a guest (anonymous).
 */
export function isGuestUser(user: User | null): boolean {
  return user?.isAnonymous ?? false;
}

/**
 * Fetch user profile from Firestore.
 * Returns null if user doesn't exist or on error.
 */
export async function getUserProfile(
  userId: string
): Promise<UserProfile | null> {
  try {
    const userRef = doc(db, "users", userId);
    const userDoc = await getDoc(userRef);

    if (userDoc.exists()) {
      return userDoc.data() as UserProfile;
    }
    return null;
  } catch (error) {
    console.error("Error fetching user profile:", error);
    return null;
  }
}

/**
 * Fetch multiple user profiles in batch.
 * Returns a map of userId -> UserProfile.
 */
export async function getUserProfiles(
  userIds: string[]
): Promise<Map<string, UserProfile>> {
  const profiles = new Map<string, UserProfile>();

  // Fetch all profiles in parallel
  const promises = userIds.map((userId) => getUserProfile(userId));
  const results = await Promise.all(promises);

  results.forEach((profile, index) => {
    if (profile) {
      profiles.set(userIds[index], profile);
    }
  });

  return profiles;
}

/**
 * Get a promise that resolves when auth state is initialized.
 */
export function waitForAuth(): Promise<User | null> {
  return new Promise((resolve) => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      unsubscribe();
      resolve(user);
    });
  });
}

/**
 * Get user display name with fallback.
 */
export function getUserDisplayName(user: User | null): string {
  if (!user) return "Guest";
  return user.displayName || (user.isAnonymous ? "Guest" : "User");
}
