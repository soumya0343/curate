// frontend/src/App.tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { CartProvider } from "./contexts/CartContext";
import { WishlistProvider } from "./contexts/WishlistContext";
import { TopNavBar } from "./components/TopNavBar";
import { DiscoverPage } from "./pages/DiscoverPage";
import { ExplorePage } from "./pages/ExplorePage";
import { WishlistPage } from "./pages/WishlistPage";
import { CartPage } from "./pages/CartPage";
import { CheckoutPage } from "./pages/CheckoutPage";

export default function App() {
  return (
    <CartProvider>
      <WishlistProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-surface font-sans">
            <TopNavBar />
            <Routes>
              <Route path="/" element={<DiscoverPage />} />
              <Route path="/explore" element={<ExplorePage />} />
              <Route path="/wishlist" element={<WishlistPage />} />
              <Route path="/cart" element={<CartPage />} />
              <Route path="/checkout" element={<CheckoutPage />} />
            </Routes>
          </div>
        </BrowserRouter>
      </WishlistProvider>
    </CartProvider>
  );
}
