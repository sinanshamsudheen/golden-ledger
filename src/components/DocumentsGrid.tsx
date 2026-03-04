import { motion } from "framer-motion";
import DocumentCard from "./DocumentCard";

const documents = [
  {
    type: "Pitch Deck",
    name: "Seed Deck Jan 2025",
    date: "Jan 12, 2025",
    description: "Series Seed fundraising deck for AI-powered logistics platform.",
  },
  {
    type: "Term Sheet",
    name: "Series A Terms — NovaTech",
    date: "Feb 3, 2025",
    description: "Preliminary term sheet outlining valuation and governance rights.",
  },
  {
    type: "Due Diligence",
    name: "DD Report — FinEdge",
    date: "Feb 18, 2025",
    description: "Comprehensive financial and legal due diligence summary.",
  },
  {
    type: "Cap Table",
    name: "Cap Table Q4 2024",
    date: "Dec 30, 2024",
    description: "Updated capitalization table reflecting latest SAFE conversions.",
  },
];

const DocumentsGrid = () => {
  return (
    <motion.section
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.6 }}
      className="mx-auto max-w-6xl px-6 py-24"
    >
      <h2 className="font-heading text-3xl font-semibold text-foreground">
        Latest Documents
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Recently processed investment documents.
      </p>
      <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {documents.map((doc) => (
          <DocumentCard key={doc.name} {...doc} />
        ))}
      </div>
    </motion.section>
  );
};

export default DocumentsGrid;
