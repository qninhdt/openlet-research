"use client";

import { signInWithPopup, signOut } from "firebase/auth";
import { auth, googleProvider } from "@/lib/firebase";
import { useAuthStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { LogOut, Chrome } from "lucide-react";
import Image from "next/image";

export function LoginButton() {
  const { user, loading } = useAuthStore();

  const handleSignIn = async () => {
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (error) {
      console.error("Sign in error:", error);
    }
  };

  const handleSignOut = async () => {
    try {
      await signOut(auth);
    } catch (error) {
      console.error("Sign out error:", error);
    }
  };

  if (loading) {
    return (
      <Button disabled variant="outline">
        Loading...
      </Button>
    );
  }

  if (user) {
    return (
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          {user.photoURL && (
            <Image
              src={user.photoURL}
              alt={user.displayName || "User"}
              className="rounded-full"
              width={32}
              height={32}
              unoptimized
            />
          )}
          <span className="text-sm font-medium hidden sm:inline">
            {user.displayName}
          </span>
        </div>
        <Button variant="outline" size="sm" onClick={handleSignOut}>
          <LogOut className="w-4 h-4 mr-2" />
          Sign out
        </Button>
      </div>
    );
  }

  return (
    <Button onClick={handleSignIn} className="gap-2">
      <Chrome className="w-4 h-4" />
      Sign in with Google
    </Button>
  );
}
