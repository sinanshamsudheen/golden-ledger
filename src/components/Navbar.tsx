const Navbar = () => {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/30 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <span className="font-heading text-xl font-semibold tracking-wide text-foreground">
          Watar Intelligence
        </span>
        <div className="flex items-center gap-8">
          {["Docs", "Support", "Account"].map((item) => (
            <a
              key={item}
              href="#"
              className="text-sm text-muted-foreground transition-colors duration-200 hover:text-primary"
            >
              {item}
            </a>
          ))}
        </div>
      </div>
    </nav>
  );
};

export default Navbar;
