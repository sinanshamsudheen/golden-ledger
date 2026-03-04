import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

const Navbar = () => {
  const { user, login, logout, isLoading } = useAuth();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/30 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <span className="font-heading text-xl font-semibold tracking-wide text-foreground">
          Watar Intelligence
        </span>
        <div className="flex items-center gap-6">
          {["Docs", "Support"].map((item) => (
            <a
              key={item}
              href="#"
              className="text-sm text-muted-foreground transition-colors duration-200 hover:text-primary"
            >
              {item}
            </a>
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
