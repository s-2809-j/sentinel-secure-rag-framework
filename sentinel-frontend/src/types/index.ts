// ─── Auth ────────────────────────────────────────────────────────────────────

export interface LoginResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  expiresIn: number;
  username: string;
  role: string;
}

export interface AuthUser {
  accessToken: string;
  refreshToken: string;
  username: string;
  role: string;
}

// ─── Admin ────────────────────────────────────────────────────────────

export interface UserSummary {
  id: string;
  username: string;
  email: string;
  role: string;
  active: boolean;
}

// ─── Chat ────────────────────────────────────────────────────────────────────

export interface ChatResponse {
  requestId:    string;
  success:      boolean;
  /** Status string e.g. "Response generated successfully." — NOT the AI answer */
  message:      string;
  /** AI answer (string) on success; blocked payload object when blocked; null on error */
  data:         string | ChatBlockedPayload | null;
  /** Numeric session ID returned by Spring Boot — use for subsequent messages */
  sessionId:    string;
  timestamp:    string;
  blocked?:     boolean;
  riskScore?:   number;
}

export interface ChatBlockedPayload {
  blocked:    boolean;
  reason?:    string;
  risk_score?: number;
}
// ─── Document Analysis ───────────────────────────────────────────────────────

export interface AnalysisData {
  riskScore: number;
  riskLevel: string;
  findings: unknown[];
  recommendation: string;
}

export interface AnalysisResponse {
  requestId: string;
  success: boolean;
  message: string;
  data: AnalysisData;
  timestamp: string;
}

// ─── Knowledge Upload ────────────────────────────────────────────────────────

export type UploadStatus = 'SUCCESS' | 'FAILED' | 'PARTIAL';

export interface UploadData {
  status: UploadStatus;
  chunkCount: number;
  embeddingCount: number;
  ingestionMessage: string;
}

export interface UploadResponse {
  requestId: string;
  success: boolean;
  message: string;
  data: UploadData;
  timestamp: string;
}

// ─── Audit ───────────────────────────────────────────────────────────────────

export interface AuditLog {
  id: number;
  userId: string | null;
  action: string;
  endpoint: string;
  requestId: string | null;
  ipAddress: string;
  statusCode: number;
  timestamp: string;
  details: string | null;
}

export interface AuditPageResponse {
  content: AuditLog[];
  totalPages: number;
  totalElements: number;
  number: number;
  size: number;
}
