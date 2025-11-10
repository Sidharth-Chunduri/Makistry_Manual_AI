import { motion } from "framer-motion";

export function LoadingDots({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      {label ? <span>{label}</span> : null}
      <motion.span
        className="inline-block w-1.5 h-1.5 rounded-full bg-current"
        animate={{ opacity: [0.2, 1, 0.2] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut", delay: 0 }}
      />
      <motion.span
        className="inline-block w-1.5 h-1.5 rounded-full bg-current"
        animate={{ opacity: [0.2, 1, 0.2] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut", delay: 0.2 }}
      />
      <motion.span
        className="inline-block w-1.5 h-1.5 rounded-full bg-current"
        animate={{ opacity: [0.2, 1, 0.2] }}
        transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut", delay: 0.4 }}
      />
    </div>
  );
}