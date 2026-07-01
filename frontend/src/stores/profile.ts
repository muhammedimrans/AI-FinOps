import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ProfileState {
  avatarUrl: string | null;
  timezone: string;
  language: string;
  bio: string;
  setAvatar: (dataUrl: string | null) => void;
  setTimezone: (timezone: string) => void;
  setLanguage: (language: string) => void;
  setBio: (bio: string) => void;
}

function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return "UTC";
  }
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set) => ({
      avatarUrl: null,
      timezone: detectTimezone(),
      language: "en",
      bio: "",
      setAvatar: (avatarUrl) => set({ avatarUrl }),
      setTimezone: (timezone) => set({ timezone }),
      setLanguage: (language) => set({ language }),
      setBio: (bio) => set({ bio }),
    }),
    { name: "costorah-profile" },
  ),
);
