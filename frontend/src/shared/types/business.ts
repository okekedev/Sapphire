export interface Business {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  plan: string;
  narrative: string | null;
  created_at: string;
}

export interface ConnectedAccount {
  id: string;
  platform: string;
  employee_id: string;
  status: string;
  connected_at: string;
}
