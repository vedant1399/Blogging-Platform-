import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, Clock3 } from "lucide-react";
import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { fetchPostBySlug } from "@/lib/api";

function formatPublishedDate(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "long",
  }).format(date);
}

export function PostPage() {
  const { slug = "" } = useParams();
  const postQuery = useQuery({
    queryKey: ["posts", slug],
    queryFn: ({ signal }) => fetchPostBySlug(slug, signal),
    enabled: slug.length > 0,
  });
  const post = postQuery.data;

  useEffect(() => {
    if (!post) {
      return;
    }

    const previousTitle = document.title;
    document.querySelectorAll("[data-post-seo]").forEach((element) => {
      element.remove();
    });

    const description =
      post.meta_description || post.excerpt || `Read ${post.title} on Ink & Insight.`;
    const pageUrl = new URL(`/posts/${encodeURIComponent(post.slug)}`, window.location.origin).href;
    const imageUrl = post.cover_image_url
      ? new URL(post.cover_image_url, window.location.origin).href
      : undefined;
    const metaEntries: Array<[string, string, string]> = [
      ["name", "description", description],
      ["name", "keywords", post.seo_keywords.join(", ")],
      ["property", "og:type", "article"],
      ["property", "og:title", post.title],
      ["property", "og:description", description],
      ["property", "og:url", pageUrl],
      ["name", "twitter:card", imageUrl ? "summary_large_image" : "summary"],
      ["name", "twitter:title", post.title],
      ["name", "twitter:description", description],
    ];
    if (imageUrl) {
      metaEntries.push(["property", "og:image", imageUrl]);
      metaEntries.push(["name", "twitter:image", imageUrl]);
    }

    document.title = `${post.title} | Ink & Insight`;
    for (const [attribute, name, content] of metaEntries) {
      const meta = document.createElement("meta");
      meta.setAttribute(attribute, name);
      meta.content = content;
      meta.dataset.postSeo = "true";
      document.head.append(meta);
    }

    const canonicalValue = post.canonical_url || pageUrl;
    try {
      const canonicalUrl = new URL(canonicalValue, window.location.origin);
      if (canonicalUrl.protocol === "https:" || canonicalUrl.protocol === "http:") {
        const canonical = document.createElement("link");
        canonical.rel = "canonical";
        canonical.href = canonicalUrl.href;
        canonical.dataset.postSeo = "true";
        document.head.append(canonical);
      }
    } catch {
      // Invalid canonical URLs are omitted; the platform URL remains in og:url.
    }

    const structuredData = {
      "@context": "https://schema.org",
      "@type": "BlogPosting",
      headline: post.title,
      description,
      datePublished: post.published_at || undefined,
      author: { "@type": "Person", name: post.author.username },
      mainEntityOfPage: pageUrl,
      image: imageUrl,
    };
    const jsonLd = document.createElement("script");
    jsonLd.type = "application/ld+json";
    jsonLd.textContent = JSON.stringify(structuredData).replace(/</g, "\\u003c");
    jsonLd.dataset.postSeo = "true";
    document.head.append(jsonLd);

    return () => {
      document.title = previousTitle;
      document.querySelectorAll("[data-post-seo]").forEach((element) => {
        element.remove();
      });
    };
  }, [post]);

  if (postQuery.isPending) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-24" aria-live="polite">
        <p className="text-sm text-muted-foreground">Loading article…</p>
      </main>
    );
  }

  if (postQuery.isError || !post) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-24">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"
        >
          <ArrowLeft aria-hidden="true" size={16} />
          Back to home
        </Link>
        <h1 className="mt-8 font-serif text-4xl">Article unavailable</h1>
        <p className="mt-3 text-muted-foreground">
          This story may have been unpublished or the address may be incorrect.
        </p>
      </main>
    );
  }

  const publishedDate = formatPublishedDate(post.published_at);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border/70">
        <nav className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <Link to="/" className="font-serif text-xl font-semibold tracking-tight">
            Ink <span className="text-primary">&amp;</span> Insight
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition hover:text-foreground"
          >
            <ArrowLeft aria-hidden="true" size={16} />
            All stories
          </Link>
        </nav>
      </header>

      <article className="mx-auto max-w-3xl px-6 pb-24 pt-12 sm:pt-20">
        {post.categories.length > 0 && (
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            {post.categories.map((category) => category.name).join(" · ")}
          </p>
        )}
        <h1 className="mt-4 font-serif text-4xl leading-tight tracking-tight sm:text-6xl">
          {post.title}
        </h1>
        {post.excerpt && (
          <p className="mt-6 text-lg leading-8 text-muted-foreground sm:text-xl">
            {post.excerpt}
          </p>
        )}
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3 border-y border-border py-5 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">By {post.author.username}</span>
          {publishedDate && (
            <span className="inline-flex items-center gap-2">
              <CalendarDays aria-hidden="true" size={15} />
              <time dateTime={post.published_at || undefined}>{publishedDate}</time>
            </span>
          )}
          <span className="inline-flex items-center gap-2">
            <Clock3 aria-hidden="true" size={15} />
            {post.read_time_minutes} min read
          </span>
        </div>
        {post.cover_image_url && (
          <img
            className="mt-9 max-h-[34rem] w-full rounded-2xl object-cover"
            src={post.cover_image_url}
            alt=""
            fetchPriority="high"
          />
        )}
        <div
          className="post-content mt-12 space-y-6 text-base leading-8 sm:text-lg"
          dangerouslySetInnerHTML={{ __html: post.content_html }}
        />
        {post.tags.length > 0 && (
          <ul className="mt-12 flex flex-wrap gap-2 border-t border-border pt-6">
            {post.tags.map((tag) => (
              <li
                key={tag.id}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground"
              >
                {tag.name}
              </li>
            ))}
          </ul>
        )}
      </article>
    </main>
  );
}
