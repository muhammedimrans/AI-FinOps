import { describe, expect, it } from "vitest";
import { loginSchema, signupSchema } from "./authSchemas";

describe("signupSchema", () => {
  it("accepts valid input", () => {
    const result = signupSchema.safeParse({
      display_name: "Ada Lovelace",
      email: "ada@example.com",
      password: "correct-horse-battery-staple",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a password shorter than 8 characters", () => {
    const result = signupSchema.safeParse({
      display_name: "Ada",
      email: "ada@example.com",
      password: "short",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a password longer than 128 characters", () => {
    const result = signupSchema.safeParse({
      display_name: "Ada",
      email: "ada@example.com",
      password: "a".repeat(129),
    });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid email address", () => {
    const result = signupSchema.safeParse({
      display_name: "Ada",
      email: "not-an-email",
      password: "correct-horse-battery-staple",
    });
    expect(result.success).toBe(false);
  });

  it("rejects an empty display name", () => {
    const result = signupSchema.safeParse({
      display_name: "",
      email: "ada@example.com",
      password: "correct-horse-battery-staple",
    });
    expect(result.success).toBe(false);
  });

  it("trims whitespace from display_name and email", () => {
    const result = signupSchema.safeParse({
      display_name: "  Ada  ",
      email: "  ada@example.com  ",
      password: "correct-horse-battery-staple",
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.display_name).toBe("Ada");
      expect(result.data.email).toBe("ada@example.com");
    }
  });
});

describe("loginSchema", () => {
  it("accepts valid input", () => {
    const result = loginSchema.safeParse({ email: "ada@example.com", password: "x" });
    expect(result.success).toBe(true);
  });

  it("rejects an empty password", () => {
    const result = loginSchema.safeParse({ email: "ada@example.com", password: "" });
    expect(result.success).toBe(false);
  });

  it("rejects an invalid email", () => {
    const result = loginSchema.safeParse({ email: "not-an-email", password: "x" });
    expect(result.success).toBe(false);
  });
});
