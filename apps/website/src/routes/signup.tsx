import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { GoogleButton } from "@/components/site/GoogleButton";
import { SiteLayout } from "@/components/site/SiteLayout";
import { LogoMark } from "@/components/site/SiteNav";
import { ApiError, register as registerAccount } from "@/lib/api";
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
  const [submittedEmail, setSubmittedEmail] = useState("");

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { account_type: "personal" },
  });
  const accountType = watch("account_type");

  const onSubmit = async (values: SignupFormValues) => {
    setFormError(null);
    try {
      // EP-24.6.1 (Issue 2): register() no longer issues a session — the
      // account and workspace are created, but nothing is returned to hand
      // off to the dashboard. Stay on this page and tell the user to check
      // their inbox instead of redirecting anywhere.
      await registerAccount(values);
      setSubmittedEmail(values.email);
      setSucceeded(true);
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
        <div className="mt-8 w-full space-y-4 rounded-2xl border border-white/10 bg-[#0C1117] p-6">
          <GoogleButton label="Sign up with Google" />
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-white/10" />
            or sign up with email
            <span className="h-px flex-1 bg-white/10" />
          </div>
        </div>
        {succeeded ? (
          <div
            role="status"
            className="mt-4 w-full space-y-3 rounded-2xl border border-[#14D9D3]/30 bg-[#14D9D3]/10 p-6 text-center"
          >
            <h2 className="font-display text-lg font-semibold text-[#14D9D3]">Check your email</h2>
            <p className="text-sm text-muted-foreground">
              We sent a verification link to{" "}
              <span className="text-foreground">{submittedEmail}</span>. Click it to verify your
              address, then sign in to continue.
            </p>
            <Link
              to="/login"
              className="inline-flex w-full items-center justify-center rounded-full bg-gradient-brand px-5 py-3 text-sm font-medium text-primary-foreground"
            >
              Go to sign in
            </Link>
          </div>
        ) : (
          <form
            onSubmit={(e) => void handleSubmit(onSubmit)(e)}
            noValidate
            className="mt-4 w-full space-y-4 rounded-2xl border border-white/10 bg-[#0C1117] p-6"
          >
            {formError && (
              <p
                role="alert"
                className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300"
              >
                {formError}
              </p>
            )}
            <fieldset>
              <legend className="text-sm text-muted-foreground">Choose your account</legend>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                <label
                  className={`cursor-pointer rounded-lg border px-3 py-2.5 text-sm transition-colors ${
                    accountType === "business"
                      ? "border-white/10 bg-white/[0.02] text-muted-foreground"
                      : "border-[#14D9D3]/40 bg-[#14D9D3]/[0.06] text-foreground"
                  }`}
                >
                  <input
                    type="radio"
                    value="personal"
                    className="sr-only"
                    disabled={isSubmitting}
                    {...register("account_type")}
                  />
                  Personal
                </label>
                <label
                  className={`cursor-pointer rounded-lg border px-3 py-2.5 text-sm transition-colors ${
                    accountType === "business"
                      ? "border-[#14D9D3]/40 bg-[#14D9D3]/[0.06] text-foreground"
                      : "border-white/10 bg-white/[0.02] text-muted-foreground"
                  }`}
                >
                  <input
                    type="radio"
                    value="business"
                    className="sr-only"
                    disabled={isSubmitting}
                    {...register("account_type")}
                  />
                  Business / Team
                </label>
              </div>
            </fieldset>
            {accountType === "business" && (
              <div>
                <label className="text-sm text-muted-foreground" htmlFor="organization_name">
                  Workspace name
                </label>
                <input
                  id="organization_name"
                  placeholder="Acme Inc"
                  autoComplete="organization"
                  disabled={isSubmitting}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40 disabled:opacity-60"
                  {...register("organization_name")}
                />
                {errors.organization_name && (
                  <p className="mt-1 text-xs text-red-400">{errors.organization_name.message}</p>
                )}
              </div>
            )}
            <div>
              <label className="text-sm text-muted-foreground" htmlFor="display_name">
                Full name
              </label>
              <input
                id="display_name"
                placeholder="Ada Lovelace"
                autoComplete="name"
                disabled={isSubmitting}
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
                disabled={isSubmitting}
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
                disabled={isSubmitting}
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40 disabled:opacity-60"
                {...register("password")}
              />
              {errors.password && (
                <p className="mt-1 text-xs text-red-400">{errors.password.message}</p>
              )}
            </div>
            <button
              type="submit"
              disabled={isSubmitting}
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
        )}
      </section>
    </SiteLayout>
  );
}
