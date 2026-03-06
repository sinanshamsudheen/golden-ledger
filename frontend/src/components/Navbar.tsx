import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

const NAV_LINKS = [
  { label: "Dashboard", to: "/dashboard" },
  { label: "Documents", to: "/documents" },
  { label: "Settings", to: "/settings" },
];

const Navbar = () => {
  const { user, login, logout, isLoading } = useAuth();
  const { pathname } = useLocation();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/30 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link
          to={user ? "/dashboard" : "/"}
          className="font-heading text-xl font-semibold tracking-wide text-foreground hover:text-primary transition-colors duration-200"
        >
          PCI Intelligence
        </Link>
        <div className="flex items-center gap-6">
          {user && NAV_LINKS.map(({ label, to }) => (
            <Link
              key={to}
              to={to}
              className={`text-sm transition-colors duration-200 ${
                pathname === to
                  ? "text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {label}
            </Link>
          ))}
          {!isLoading && (
            user ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={logout}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Sign out
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={login}
                className="border-primary text-primary hover:bg-primary hover:text-primary-foreground"
              >
                Sign in
              </Button>
            )
          )}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
