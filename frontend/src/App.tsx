// frontend/src/App.tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { CartProvider } from "./contexts/CartContext";
import { WishlistProvider } from "./contexts/WishlistContext";
import { TopNavBar } from "./components/TopNavBar";
import { DiscoverPage } from "./pages/DiscoverPage";

export default function App() {
  return (
    <CartProvider>
      <WishlistProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-surface font-sans">
            <TopNavBar />
            <Routes>
              <Route path="/" element={<DiscoverPage />} />
            </Routes>
          </div>
        </BrowserRouter>
      </WishlistProvider>
    </CartProvider>
  );
}
