import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";

const Hero = () => {
  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: "easeOut" }}
      className="flex min-h-[80vh] flex-col items-center justify-center px-6 pt-16 text-center"
    >
      <h1 className="font-heading text-5xl font-bold leading-tight tracking-tight text-foreground md:text-6xl lg:text-7xl">
        Investment Document
        <br />
        Intelligence
      </h1>
      <p className="mt-6 max-w-xl text-lg text-muted-foreground">
        Automatically organize and analyze your investment documents.
      </p>
      <Button
        variant="outline"
        className="mt-10 border-primary bg-transparent px-8 py-6 text-sm font-medium tracking-wider text-primary transition-all duration-300 hover:bg-primary hover:text-primary-foreground"
      >
        Connect Google Drive
      </Button>
    </motion.section>
  );
};

export default Hero;
