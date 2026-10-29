export interface Me {
  logged_in: boolean;
  setup_done: boolean;
  theme: string;
  chat_url: string;
  learner_url: string;
}

export interface ChatSummary {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}
