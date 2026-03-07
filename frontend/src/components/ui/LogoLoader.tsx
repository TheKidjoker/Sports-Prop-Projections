import { motion } from "framer-motion";

interface LogoLoaderProps {
  text?: string;
  size?: "sm" | "md" | "lg";
  fullScreen?: boolean;
}

const sizes = {
  sm: "w-12 h-12",
  md: "w-20 h-20",
  lg: "w-32 h-32",
};

export function LogoLoader({ text = "LOADING...", size = "md", fullScreen = false }: LogoLoaderProps) {
  const content = (
    <div className="flex flex-col items-center gap-4">
      <motion.img
        src="/static/logo.png"
        alt="Loading"
        className={`${sizes[size]} drop-shadow-[0_0_20px_rgba(220,38,38,0.4)]`}
        animate={{ rotate: 360 }}
        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
      />
      <span className="text-primary font-heading tracking-[0.2em] text-xs sm:text-sm animate-pulse">
        {text}
      </span>
    </div>
  );

  if (fullScreen) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        {content}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center py-12">
      {content}
    </div>
  );
}
