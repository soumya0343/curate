// frontend/src/components/TopNavBar.tsx
import { Link } from "react-router-dom";

export function TopNavBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-primary/10 bg-surface/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Link to="/" className="font-serif text-2xl font-medium tracking-tight text-primary">
          Curate
        </Link>
        <nav className="hidden items-center gap-6 text-sm text-primary/60 sm:flex">
          <Link to="/" className="transition hover:text-primary">Discover</Link>
          <Link to="/explore" className="transition hover:text-primary">Explore</Link>
        </nav>
        <div className="w-24" />
      </div>
    </header>
  );
}
