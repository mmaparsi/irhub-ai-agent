export type Role = "admin" | "sales" | "supplier_acquisition";

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
};

export type Agent = {
  id: string;
  slug: string;
  name: string;
  name_fa: string;
  description: string;
  system_prompt: string;
  allowed_tools: string[];
  model_strong: string;
  model_fast: string;
  temperature: number;
  is_active: boolean;
  source: string;
  created_at: string;
  updated_at: string;
};

export type ToolInfo = {
  name: string;
  description: string;
  kind: string;
  provider: string;
  is_enabled: boolean;
};

export type Conversation = {
  id: string;
  title: string;
  status: string;
  agent_id: string | null;
  agent_name: string | null;
  channel?: string;
  party?: string;
  created_at: string;
};

export type ChatMessage = {
  id: string;
  role: string;
  content: string;
  seq: number;
  created_at: string;
};

export type Approval = {
  id: string;
  action_type: string;
  payload: Record<string, unknown>;
  status: string;
  execution_status: string;
  decision_note: string;
  created_at: string;
  decided_at: string | null;
  executed_at: string | null;
  requested_by_name: string | null;
  agent_name: string | null;
};

export type Lead = {
  id: string;
  title: string;
  source: string;
  status: string;
  score: number;
  notes: string;
  company_name: string;
  city: string;
  industry: string;
  website?: string;
  party?: string;
  contacts: { name: string; email: string; phone: string; title: string }[];
  deals: { title: string; value: number; currency: string; stage: string; discount_percent: number }[];
  created_at: string;
};

export type KnowledgeDoc = {
  id: string;
  title: string;
  source: string;
  status: string;
  excerpt: string;
  created_at: string;
};

export type Dashboard = {
  agents: number;
  pending_approvals: number;
  leads: number;
  documents: number;
  running_tasks?: number;
  mock_llm: boolean;
  max_discount_percent: number;
};

export type AgentInput = {
  slug?: string;
  name: string;
  name_fa: string;
  description: string;
  system_prompt: string;
  allowed_tools: string[];
  model_strong: string;
  model_fast: string;
  temperature: number;
  is_active: boolean;
};
