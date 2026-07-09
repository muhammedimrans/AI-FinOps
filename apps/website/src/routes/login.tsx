import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { SiteLayout } from "@/components/site/SiteLayout";
import { LogoMark } from "@/components/site/SiteNav";
import { ApiError, buildDashboardHandoffUrl, login as loginRequest } from "@/lib/api";
import { type LoginFormValues, loginSchema } from "@/lib/authSchemas";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Log in — Costorah" },
      { name: "description", content: "Log in to your Costorah workspace." },
    ],
  }),
  component: Login,
});

function Login() {
  const [formError, setFormError] = useState<string | null>(null);
  const [succeeded, setSucceeded] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = async (values: LoginFormValues) => {
    setFormError(null);
    try {
      const session = await loginRequest(values);
      setSucceeded(true);
      window.location.href = buildDashboardHandoffUrl("/", session);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setFormError("Incorrect email or password.");
      } else if (err instanceof ApiError && err.status === 429) {
        setFormError("Too many attempts. Please wait a moment and try again.");
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
        <h1 className="mt-6 font-display text-3xl font-semibold tracking-tight">Welcome back</h1>
        <p className="mt-2 text-sm text-muted-foreground">Log in to your Costorah workspace.</p>
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
              Logged in — redirecting…
            </p>
          )}
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
              autoComplete="current-password"
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
            {isSubmitting ? "Logging in…" : "Log in"}
          </button>
          <p className="text-center text-xs text-muted-foreground">
            No account?{" "}
            <Link to="/signup" className="text-[#14D9D3]">
              Start free
            </Link>
          </p>
        </form>
      </section>
    </SiteLayout>
  );
}
