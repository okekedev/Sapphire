import { cn } from "@/shared/lib/utils";
import { Check, X } from "lucide-react";

interface PasswordStrengthProps {
  password: string;
}

const rules = [
  { label: "8+ characters", test: (p: string) => p.length >= 8 },
  { label: "Uppercase letter", test: (p: string) => /[A-Z]/.test(p) },
  { label: "Lowercase letter", test: (p: string) => /[a-z]/.test(p) },
  { label: "Number", test: (p: string) => /[0-9]/.test(p) },
];

const strengthLabels = ["", "Weak", "Fair", "Good", "Strong"];
const strengthColors = ["", "bg-red-500", "bg-yellow-500", "bg-emerald-400", "bg-emerald-500"];

export function PasswordStrength({ password }: PasswordStrengthProps) {
  if (!password) return null;

  const passed = rules.filter((r) => r.test(password)).length;

  return (
    <div className="mt-3 space-y-3">
      {/* Progress bar */}
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={cn(
              "h-1 flex-1 rounded-full transition-colors duration-300",
              i <= passed ? strengthColors[passed] : "bg-muted",
            )}
          />
        ))}
      </div>

      <p className="text-xs text-muted-foreground">
        Strength: <span className="font-medium">{strengthLabels[passed]}</span>
      </p>

      {/* Requirement checklist */}
      <ul className="space-y-1">
        {rules.map((rule) => {
          const ok = rule.test(password);
          return (
            <li
              key={rule.label}
              className={cn(
                "flex items-center gap-1.5 text-xs transition-colors duration-200",
                ok ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground",
              )}
            >
              {ok ? <Check size={12} /> : <X size={12} />}
              {rule.label}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
