import { z } from "zod";

// Password rule mirrors the backend's RegisterRequest (app/schemas/auth.py:
// Field(min_length=8, max_length=128)) — kept in sync manually since there's
// no shared-schema package between the two languages yet.
//
// EP-25.1: account_type mirrors the backend's Literal["personal","business"]
// default "personal"; organization_name is only required (and only shown by
// the form) when account_type === "business".
export const signupSchema = z
  .object({
    display_name: z.string().trim().min(1, "Enter your name"),
    email: z.string().trim().email("Enter a valid email address"),
    password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .max(128, "Password is too long"),
    account_type: z.enum(["personal", "business"]),
    organization_name: z.string().trim().max(255).optional(),
  })
  .refine((values) => values.account_type !== "business" || !!values.organization_name?.trim(), {
    message: "Enter a workspace name",
    path: ["organization_name"],
  });

export type SignupFormValues = z.infer<typeof signupSchema>;

export const loginSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
