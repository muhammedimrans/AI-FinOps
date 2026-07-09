import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merges class names, resolving conflicting Tailwind utility classes
 * (twMerge) after combining conditional class lists (clsx). Single
 * source of truth for both apps/website and apps/dashboard, which
 * previously each defined an identical copy of this function.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
