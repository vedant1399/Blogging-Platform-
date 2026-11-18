import { Route, Routes } from "react-router-dom";
import { HomePage } from "@/pages/HomePage";
import { PostPage } from "@/pages/PostPage";

function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <div className="text-center">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-primary">
          404
        </p>
        <h1 className="mt-3 font-serif text-4xl">Page not found</h1>
        <a
          className="mt-6 inline-flex rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
          href="/"
        >
          Return home
        </a>
      </div>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/posts/:slug" element={<PostPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
