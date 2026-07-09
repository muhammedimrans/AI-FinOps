import { z } from "zod";

// Password rule mirrors the backend's RegisterRequest (app/schemas/auth.py:
// Field(min_length=8, max_length=128)) — kept in sync manually since there's
// no shared-schema package between the two languages yet.
export const signupSchema = z.object({
  display_name: z.string().trim().min(1, "Enter your name"),
  email: z.string().trim().email("Enter a valid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .max(128, "Password is too long"),
});

export type SignupFormValues = z.infer<typeof signupSchema>;

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
