import { useQuery } from "@tanstack/react-query";
import { ArrowDown, CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { fetchApiHealth } from "@/lib/api";

export function HomePage() {
  const healthQuery = useQuery({
    queryKey: ["api", "health"],
    queryFn: ({ signal }) => fetchApiHealth(signal),
  });

  const apiOnline = healthQuery.data?.status === "ok";

  return (
    <div className="min-h-screen">
      <header className="border-b border-border/70">
        <nav
          aria-label="Main navigation"
          className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5"
        >
          <Link
            to="/"
            className="font-serif text-xl font-semibold tracking-tight text-foreground"
          >
            Ink <span className="text-primary">&</span> Insight
          </Link>
          <a
            href="#platform-status"
            className="text-sm font-medium text-muted-foreground transition hover:text-foreground"
          >
            Platform status
          </a>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid min-h-[min(760px,calc(100svh-73px))] max-w-6xl content-center gap-10 px-6 py-20 md:grid-cols-[1.4fr_0.6fr] md:items-end">
          <div>
            <p className="mb-6 text-xs font-semibold uppercase tracking-[0.24em] text-primary">
              A home for thoughtful writing
            </p>
            <h1 className="max-w-3xl font-serif text-5xl leading-[1.05] tracking-tight text-foreground sm:text-6xl md:text-7xl">
              Make room for
              <br />
              <span className="italic text-primary">thoughtful stories.</span>
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-muted-foreground">
              Ink &amp; Insight brings curious readers and independent voices
              together, one considered idea at a time.
            </p>
            <a
              href="#platform-status"
              className="mt-9 inline-flex items-center gap-3 rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
            >
              Explore the platform
              <ArrowDown aria-hidden="true" size={16} />
            </a>
          </div>

          <aside
            aria-label="Platform introduction"
            className="border-l border-border py-2 pl-6 md:mb-2"
          >
            <p className="font-serif text-2xl leading-snug text-foreground">
              Good ideas deserve a place to grow.
            </p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Read deeply. Share generously. Write what matters.
            </p>
          </aside>
        </section>

        <section
          id="platform-status"
          aria-labelledby="status-heading"
          className="border-y border-border bg-card"
        >
          <div className="mx-auto flex max-w-6xl flex-col gap-5 px-6 py-12 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                Platform
              </p>
              <h2
                id="status-heading"
                className="mt-2 font-serif text-2xl text-foreground"
              >
                Service status
              </h2>
            </div>
            <div
              className="flex items-start gap-3 text-sm"
              aria-live="polite"
              aria-busy={healthQuery.isPending}
            >
              {healthQuery.isPending ? (
                <>
                  <LoaderCircle
                    aria-hidden="true"
                    className="mt-0.5 animate-spin text-muted-foreground"
                    size={18}
                  />
                  <span className="text-muted-foreground">
                    Checking the API…
                  </span>
                </>
              ) : apiOnline ? (
                <>
                  <CircleCheck
                    aria-hidden="true"
                    className="mt-0.5 text-emerald-700"
                    size={18}
                  />
                  <span className="text-foreground">
                    API is responding normally.
                  </span>
                </>
              ) : (
                <>
                  <CircleAlert
                    aria-hidden="true"
                    className="mt-0.5 text-amber-700"
                    size={18}
                  />
                  <span className="max-w-md text-muted-foreground">
                    The API could not be reached. Start the Flask server and
                    check the configured API URL.
                  </span>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-8 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span>Ink &amp; Insight</span>
        <span>Thoughtful writing starts with a good question.</span>
      </footer>
    </div>
  );
}
