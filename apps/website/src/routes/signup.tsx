import { createFileRoute, Link } from "@tanstack/react-router";
import { SiteLayout } from "@/components/site/SiteLayout";
import { LogoMark } from "@/components/site/SiteNav";

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
  return (
    <SiteLayout>
      <section className="mx-auto flex max-w-md flex-col items-center px-6 py-24">
        <LogoMark className="h-9 w-9" />
        <h1 className="mt-6 font-display text-3xl font-semibold tracking-tight">Start free</h1>
        <p className="mt-2 text-sm text-muted-foreground">Free forever. No credit card required.</p>
        <form
          onSubmit={(e) => e.preventDefault()}
          className="mt-8 w-full space-y-4 rounded-2xl border border-white/10 bg-[#0C1117] p-6"
        >
          <div>
            <label className="text-sm text-muted-foreground">Full name</label>
            <input
              placeholder="Ada Lovelace"
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40"
            />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Work email</label>
            <input
              type="email"
              placeholder="you@company.com"
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40"
            />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">Password</label>
            <input
              type="password"
              placeholder="••••••••"
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2.5 text-sm outline-none focus:border-[#14D9D3]/40"
            />
          </div>
          <button className="w-full rounded-full bg-gradient-brand px-5 py-3 text-sm font-medium text-primary-foreground">
            Create account
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
