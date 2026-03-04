import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

interface DocumentCardProps {
  type: string;
  name: string;
  date: string;
  description: string;
}

const DocumentCard = ({ type, name, date, description }: DocumentCardProps) => {
  return (
    <motion.div
      whileHover={{ y: -4, borderColor: "hsl(38 38% 60%)" }}
      transition={{ duration: 0.2 }}
      className="rounded-lg border border-border bg-card p-6 transition-shadow duration-300 hover:shadow-[0_0_20px_hsl(38_38%_60%/0.08)]"
    >
      <Badge
        variant="outline"
        className="border-primary/40 text-primary"
      >
        {type}
      </Badge>
      <h3 className="mt-4 font-heading text-lg font-semibold text-foreground">
        {name}
      </h3>
      <p className="mt-1 text-xs text-muted-foreground">{date}</p>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
    </motion.div>
  );
};

export default DocumentCard;
