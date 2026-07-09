import { getInitials, cn } from "../utils";
import { useProfileStore } from "../stores/profile";

interface AvatarProps {
  name: string;
  size?: number;
  className?: string;
}

/** Renders the user's uploaded photo when set, falling back to initials. Used everywhere a user avatar appears. */
export default function Avatar({ name, size = 28, className }: AvatarProps) {
  const avatarUrl = useProfileStore((s) => s.avatarUrl);

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={`${name}'s avatar`}
        style={{ width: size, height: size }}
        className={cn("rounded-full object-cover flex-shrink-0", className)}
      />
    );
  }

  return (
    <div
      style={{ width: size, height: size }}
      className={cn("rounded-full bg-gradient-brand flex items-center justify-center flex-shrink-0", className)}
      aria-hidden="true"
    >
      <span className="font-semibold text-app-bg" style={{ fontSize: size * 0.4 }}>
        {getInitials(name)}
      </span>
    </div>
  );
}
