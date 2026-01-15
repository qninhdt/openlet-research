"use client";

import { useEffect } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { doc, setDoc, serverTimestamp } from "firebase/firestore";
import { auth, db } from "@/lib/firebase";
import { useAuthStore } from "@/lib/store";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { setUser, setLoading } = useAuthStore();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setUser(user);
      setLoading(false);

      // Save/update user profile in Firestore for non-anonymous users
      if (user && !user.isAnonymous) {
        try {
          const userRef = doc(db, "users", user.uid);
          await setDoc(
            userRef,
            {
              uid: user.uid,
              displayName: user.displayName,
              email: user.email,
              photoURL: user.photoURL,
              lastLoginAt: serverTimestamp(),
            },
            { merge: true }
          );
        } catch (error) {
          console.error("Error saving user profile:", error);
        }
      }
    });

    return () => unsubscribe();
  }, [setUser, setLoading]);

  return <>{children}</>;
}
