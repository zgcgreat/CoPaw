// Dream logs API types

export interface FileStats {
  size_before: number;
  size_after: number;
  size_saved: number;
  lines_before: number;
  lines_after: number;
  lines_removed: number;
  backup_path: string;
}

export interface DreamLogRecord {
  id: string;
  timestamp: string;
  trigger: "cron" | "manual";
  status: "success" | "failed" | "rollback";
  files_optimized: string[];
  file_stats: Record<string, FileStats>;
  total_size_saved: number;
  total_files_changed: number;
  duration_ms: number;
  model_used: string;
  input_tokens: number;
  output_tokens: number;
  summary: string;
  error?: string;
}

export interface DreamLogsStats {
  total_executions: number;
  success_count: number;
  failed_count: number;
  total_size_saved: number;
  total_files_changed: number;
  avg_duration_ms: number;
  last_execution?: string;
}

export interface DreamLogsResponse {
  records: DreamLogRecord[];
  stats: DreamLogsStats;
  total: number;
  page: number;
  page_size: number;
}

export interface DiffResponse {
  filename: string;
  content_before: string;
  content_after: string;
  size_before: number;
  size_after: number;
  size_saved: number;
}

export interface TriggerResponse {
  success: boolean;
  message: string;
  record_id?: string;
}

export interface RollbackResponse {
  success: boolean;
  message: string;
  files_rolled_back: string[];
}

// Backup types
export interface BackupFileInfo {
  filename: string;
  original_file: string;
  record_id: string;
  timestamp: string;
  size: number;
  created_at: string;
}

export interface BackupListResponse {
  files: BackupFileInfo[];
  total_size: number;
  total_files: number;
}

export interface DeleteBackupResponse {
  success: boolean;
  message: string;
  files_deleted: string[];
}

export interface BackupContentResponse {
  filename: string;
  content: string;
  size: number;
  original_file: string;
}

// Orphan files types
export interface OrphanFileInfo {
  filename: string;
  size: number;
  created_at: string;
  modified_at: string;
  path: string;
  full_path: string;
}

export interface OrphanFilesResponse {
  files: OrphanFileInfo[];
  total_size: number;
  total_files: number;
  workspace_dir: string;
}

export interface OrphanFileContentResponse {
  filename: string;
  content: string;
  size: number;
  file_type: "text" | "image" | "binary" | "error";
  is_loadable: boolean;
  error_message?: string;
}