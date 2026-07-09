import { Building2 } from "lucide-react";
import { cn } from "../utils";
import { useOrgStore } from "../stores/org";

interface OrgLogoProps {
  size?: number;
  className?: string;
}

/** Renders the organization's uploaded logo when set, falling back to a building icon badge. */
export default function OrgLogo({ size = 28, className }: OrgLogoProps) {
  const organizationId = useOrgStore((s) => s.organizationId);
  const logoUrl = useOrgStore((s) => (organizationId ? s.organizationLogos[organizationId] : undefined));

  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt="Organization logo"
        style={{ width: size, height: size }}
        className={cn("rounded-lg object-cover flex-shrink-0 border border-border-subtle", className)}
      />
    );
  }

  return (
    <div
      style={{ width: size, height: size }}
      className={cn("rounded-lg bg-brand-subtle flex items-center justify-center flex-shrink-0", className)}
      aria-hidden="true"
    >
      <Building2 size={size * 0.55} className="text-brand" />
    </div>
  );
}
