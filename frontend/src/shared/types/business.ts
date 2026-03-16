export interface Business {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  plan: string;
  // Company profile — predefined columns
  description: string | null;
  services: string | null;
  target_audience: string | null;
  online_presence: string | null;
  brand_voice: string | null;
  goals: string | null;
  competitive_landscape: string | null;
  profile_source: string | null;
  created_at: string;
}

export interface ConnectedAccount {
  id: string;
  platform: string;
  employee_id: string;
  status: string;
  connected_at: string;
}
