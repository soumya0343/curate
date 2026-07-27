// frontend/src/components/TopNavBar.tsx
import { Link } from "react-router-dom";
import { useWishlist } from "../contexts/WishlistContext";
import { useCart } from "../contexts/CartContext";

export function TopNavBar() {
  const { count: wishlistCount } = useWishlist();
  const { count: cartCount } = useCart();

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
        <div className="flex items-center gap-4">
          <Link to="/wishlist" aria-label="Wishlist" className="relative text-primary/60 transition hover:text-primary">
            ♡
            {wishlistCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-gold-400 text-[10px] font-medium text-white">
                {wishlistCount}
              </span>
            )}
          </Link>
          <Link to="/cart" aria-label="Cart" className="relative text-primary/60 transition hover:text-primary">
            🛒
            {cartCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-medium text-white">
                {cartCount}
              </span>
            )}
          </Link>
        </div>
      </div>
    </header>
  );
}
