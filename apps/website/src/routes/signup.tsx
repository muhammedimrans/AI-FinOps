import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { SiteLayout } from "@/components/site/SiteLayout";
import { LogoMark } from "@/components/site/SiteNav";
import { ApiError, DASHBOARD_URL, register as registerAccount } from "@/lib/api";
import { type SignupFormValues, signupSchema } from "@/lib/authSchemas";

export const Route = createFileRoute("/signup")({
  head: () => ({
    meta: [
      { title: "Start free — Costorah" },
      { name: "description", content: "Create your Costorah workspace in under a minute." },
    ],
  }),
  component: Signup,
});

function Signup() {
  const [formError, setFormError] = useState<string | null>(null);
  const [succeeded, setSucceeded] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({ resolver: zodResolver(signupSchema) });

  const onSubmit = async (values: SignupFormValues) => {
    setFormError(null);
    try {
      await registerAccount(values);
      setSucceeded(true);
      // The session cookie is already set (credentials: "include" on the
      // request) — this is a full navigation, not client-side routing,
      // because app.costorah.com is a different origin in production.
      window.location.href = `${DASHBOARD_URL}/onboarding`;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setFormError("An account with this email already exists. Try logging in instead.");
      } else if (err instanceof ApiError) {
        setFormError(err.message || "Something went wrong. Please try again.");
      } else {
        setFormError("Could not reach the server. Check your connection and try again.");
      }
    }
  };

  return (
    <SiteLayout>
      <section className="mx-auto flex max-w-md flex-col items-center px-6 py-24">
        <LogoMark className="h-9 w-9" />
        <h1 className="mt-6 font-display text-3xl font-semibold tracking-tight">Start free</h1>
        <p className="mt-2 text-sm text-muted-foreground">Free forever. No credit card required.</p>
        <form
          onSubmit={(e) => void handleSubmit(onSubmit)(e)}
          noValidate
          className="mt-8 w-full space-y-4 rounded-2xl border border-white/10 bg-[#0C1117] p-6"
        >
          {formError && (
            <p
              role="alert"
              className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
            >
              {formError}
            </p>
          )}
          {succeeded && (
            <p
              role="status"
              className="rounded-lg border border-[#14D9D3]/30 bg-[#14D9D3]/10 px-3 py-2 text-sm text-[#14D9D3]"
            >
              Account created — redirecting to your workspace…
            </p>
          )}
          <div>
            <label className="text-sm text-muted-foreground" htmlFor="display_name">
              Full name
            </label>
            <input
              id="display_name"
              placeholder="Ada Lovelace"
              autoComplete="name"
              disabled={isSubmitting || succeeded}
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40 disabled:opacity-60"
              {...register("display_name")}
            />
            {errors.display_name && (
              <p className="mt-1 text-xs text-red-400">{errors.display_name.message}</p>
            )}
          </div>
          <div>
            <label className="text-sm text-muted-foreground" htmlFor="email">
              Work email
            </label>
            <input
              id="email"
              type="email"
              placeholder="you@company.com"
              autoComplete="email"
              disabled={isSubmitting || succeeded}
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40 disabled:opacity-60"
              {...register("email")}
            />
            {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>}
          </div>
          <div>
            <label className="text-sm text-muted-foreground" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              autoComplete="new-password"
              disabled={isSubmitting || succeeded}
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40 disabled:opacity-60"
              {...register("password")}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-400">{errors.password.message}</p>
            )}
          </div>
          <button
            type="submit"
            disabled={isSubmitting || succeeded}
            className="w-full rounded-full bg-gradient-brand px-5 py-3 text-sm font-medium text-primary-foreground disabled:opacity-60"
          >
            {isSubmitting ? "Creating account…" : "Create account"}
          </button>
          <p className="text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="text-[#14D9D3]">
              Log in
            </Link>
          </p>
        </form>
      </section>
    </SiteLayout>
  );
}
