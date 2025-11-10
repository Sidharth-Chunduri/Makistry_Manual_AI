import { motion } from "framer-motion";

const FEATURES = [
  "Brainstorm with AI",
  "Define design requirements & components",
  "Auto-generate CAD models",
  "Edit with simple text prompts",
  "Access past version",
  "Export CAD models, images, and PDFs",
  "Share your project",
];

export function FeaturesScroller() {
  const list = [...FEATURES, ...FEATURES]; // loop
  return (
    <div className="relative h-40 overflow-hidden rounded-xl bg-white/40 backdrop-blur p-4">
      <motion.ul
        role="list"
        className="space-y-3 text-sm text-[#031926]"
        animate={{ y: ["0%", "-50%"] }}
        transition={{ repeat: Infinity, duration: 14, ease: "linear" }}
      >
        {list.map((f, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#031926]" />
            {f}
          </li>
        ))}
      </motion.ul>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-8 from-primary-light to-transparent bg-gradient-to-b" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 from-transparent to-primary-light bg-gradient-to-t" />
    </div>
  );
}