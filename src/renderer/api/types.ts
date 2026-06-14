export type Tone = "good" | "warn" | "idle" | string;

export interface OutlineItem {
  id: string;
  number?: string | number;
  title: string;
  score?: number | null;
  tone?: Tone;
  agent?: string;
  source?: string;
}

export interface OutlineChapter {
  id?: string;
  chapter: string;
  title: string;
  expanded?: boolean;
  items: OutlineItem[];
}

export interface SectionPayload extends OutlineItem {
  type?: string;
  summary?: string;
  contentFile?: string;
  source: string;
}

export interface DocumentStyle {
  styleId?: string;
  style_id?: string;
  label: string;
  description?: string;
}

export interface AgentStatus {
  active: number;
  total: number;
  confidence: number;
  pendingProposals: number;
}

export interface EditProposal {
  proposal_id: string;
  agent_id: string;
  target_path: string;
  status: "pending" | "accepted" | "rejected" | "revised" | string;
  rationale?: string;
  diff?: string;
  proposed_content?: string;
}

export interface Artifact {
  artifact_id?: string;
  kind?: string;
  path: string;
  title?: string | null;
  label?: string;
}

export interface ReferenceEntry {
  id?: string;
  title?: string;
  author?: string;
  year?: string | number;
}

export interface CompileResult {
  status?: string;
  pdf_path?: string;
  errors?: string[];
}

export interface VerificationEvent {
  event_id?: string;
  event_type?: string;
  agent_id?: string;
  subject?: string;
  status?: string;
  rationale?: string;
}

export interface UserChatMessage {
  message_id: string;
  from_agent?: string;
  subject: string;
  body: string;
  status: "pending" | "answered" | "dismissed" | string;
  answer?: string;
}

export interface BookAppState {
  bookRoot?: string;
  book?: {
    id?: string;
    title?: string;
    summary?: string;
  };
  outline: OutlineChapter[];
  selectedId?: string | null;
  selectedSection?: SectionPayload | null;
  design?: Record<string, string>;
  styles?: DocumentStyle[];
  messages?: string[];
  agentStatus?: AgentStatus;
  artifacts?: Artifact[];
  proposals?: EditProposal[];
  references?: ReferenceEntry[];
  compile?: CompileResult | null;
  verification?: VerificationEvent[];
}

export interface BookRecord {
  book_id: string;
  title: string;
  root: string;
  status: string;
}

export interface BookLibraryState {
  active?: string | null;
  books: BookRecord[];
}

export interface ElectronApi {
  app: {
    state(selectedId?: string | null): Promise<BookAppState>;
    section(sectionId: string): Promise<SectionPayload>;
    saveSection(sectionId: string, content: string): Promise<SectionPayload>;
    compileSection(sectionId: string): Promise<CompileResult>;
    compileBook(): Promise<CompileResult>;
    requestReview(subject?: string): Promise<VerificationEvent>;
    createSection(parentId: string | undefined, title: string): Promise<SectionPayload>;
    createChapter(title: string): Promise<Record<string, unknown>>;
    updateOutlineNode(nodeId: string, title: string): Promise<Record<string, unknown>>;
    acceptProposal(proposalId: string, note?: string): Promise<EditProposal>;
    rejectProposal(proposalId: string, note?: string): Promise<EditProposal>;
    reviseProposal(proposalId: string, content: string, note?: string): Promise<EditProposal>;
    importOutline(mode: "current" | "new"): Promise<{ sourcePath: string; output: string } | null>;
    library(): Promise<BookLibraryState>;
    openBook(bookId: string): Promise<BookRecord>;
    newBook(title: string): Promise<BookRecord>;
    onBookChanged(callback: (payload: { bookId: string }) => void): void;
    onLibraryMessage(callback: (payload: { message: string }) => void): void;
  };
  typeset?: {
    styles(): Promise<DocumentStyle[]>;
    setStyle(styleId: string, bookRoot?: string): Promise<{ output: string }>;
  };
  userChat?: {
    list(): Promise<UserChatMessage[]>;
    answer(messageId: string, answer: string): Promise<UserChatMessage>;
    dismiss(messageId: string): Promise<UserChatMessage>;
  };
}

declare global {
  interface Window {
    cbm?: ElectronApi;
  }
}
