export function TopNavBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-primary/10 bg-surface/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <span className="font-serif text-2xl font-medium tracking-tight text-primary">
          Curate
        </span>
        <nav className="hidden items-center gap-6 text-sm text-primary/60 sm:flex">
          <a href="#" className="transition hover:text-primary">Discover</a>
          <a href="#" className="transition hover:text-primary">Wedding</a>
          <a href="#" className="transition hover:text-primary">Anniversary</a>
          <a href="#" className="transition hover:text-primary">Gear</a>
        </nav>
        <div className="w-24" />
      </div>
    </header>
  );
}
