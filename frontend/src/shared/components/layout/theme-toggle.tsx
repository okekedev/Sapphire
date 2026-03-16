import { Sun, Moon, Monitor } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { useThemeStore } from "@/shared/stores/theme-store";

const icons = { light: Sun, dark: Moon, system: Monitor } as const;
const labels = { light: "Light", dark: "Dark", system: "System" } as const;

export function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const toggle = useThemeStore((s) => s.toggleTheme);
  const Icon = icons[theme];

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      title={`Theme: ${labels[theme]}`}
    >
      <Icon className="h-4 w-4" />
    </Button>
  );
}
