export type Department =
  | "marketing"
  | "sales"
  | "operations"
  | "billing"
  | "administration"
  | "it";

export interface DepartmentInfo {
  id: Department;
  label: string;
  description: string;
  icon: string; // lucide icon name for reference
}

export const DEPARTMENTS: DepartmentInfo[] = [
  { id: "marketing", label: "Marketing", description: "Social media, content strategy, SEO campaigns, outreach", icon: "Megaphone" },
  { id: "sales", label: "Sales", description: "Lead qualification, pipeline management, outreach", icon: "DollarSign" },
  { id: "operations", label: "Operations", description: "Prospect research, website generation, app building", icon: "Settings" },
  { id: "billing", label: "Billing", description: "Invoicing, payments, subscriptions, revenue tracking", icon: "CreditCard" },
  { id: "administration", label: "Administration", description: "Phone system, after-hours forwarding, IVR configuration", icon: "Building2" },
  { id: "it", label: "IT", description: "Platform integrations, API connections, DevOps", icon: "Server" },
];

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  status?: "sending" | "complete" | "error";
}
