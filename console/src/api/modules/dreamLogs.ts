// Dream logs API module

import { request } from "../request";
import type {
  DreamLogsResponse,
  DreamLogsStats,
  DiffResponse,
  TriggerResponse,
  RollbackResponse,
  BackupListResponse,
  DeleteBackupResponse,
  BackupContentResponse,
  OrphanFilesResponse,
  OrphanFileContentResponse,
} from "../types/dreamLogs";

export const dreamLogsApi = {
  /**
   * List dream optimization records
   */
  list: async (page: number = 1, pageSize: number = 20): Promise<DreamLogsResponse> =>
    request(`/dream-logs?page=${page}&page_size=${pageSize}`),

  /**
   * Get aggregate statistics
   */
  stats: async (): Promise<DreamLogsStats> => request("/dream-logs/stats"),

  /**
   * Get file diff
   */
  diff: async (recordId: string, filename: string): Promise<DiffResponse> =>
    request(`/dream-logs/diff/${recordId}/${filename}`),

  /**
   * Trigger dream optimization manually (async, returns immediately)
   */
  trigger: async (): Promise<TriggerResponse> =>
    request("/dream-logs/trigger", { method: "POST" }),

  /**
   * Rollback files from a dream optimization
   */
  rollback: async (recordId: string, files?: string[]): Promise<RollbackResponse> =>
    request(`/dream-logs/rollback/${recordId}`, {
      method: "POST",
      body: JSON.stringify({ files }),
    }),

  /**
   * List backup files
   */
  listBackups: async (): Promise<BackupListResponse> =>
    request("/dream-logs/backups"),

  /**
   * Delete all backup files
   */
  deleteAllBackups: async (): Promise<DeleteBackupResponse> =>
    request("/dream-logs/backups", { method: "DELETE" }),

  /**
   * Delete a specific backup file
   */
  deleteBackup: async (filename: string): Promise<DeleteBackupResponse> =>
    request(`/dream-logs/backups/${filename}`, { method: "DELETE" }),

  /**
   * Get backup file content for preview
   */
  getBackupContent: async (filename: string): Promise<BackupContentResponse> =>
    request(`/dream-logs/backups/${filename}/content`),

  // Orphan files API
  /**
   * List orphan files in workspace directory
   */
  listOrphanFiles: async (): Promise<OrphanFilesResponse> =>
    request("/dream-logs/orphan-files"),

  /**
   * Get orphan file content for preview
   */
  getOrphanFileContent: async (filepath: string): Promise<OrphanFileContentResponse> =>
    request(`/dream-logs/orphan-files/${filepath}/content`),

  /**
   * Delete an orphan file
   */
  deleteOrphanFile: async (filepath: string): Promise<DeleteBackupResponse> =>
    request(`/dream-logs/orphan-files/${filepath}`, { method: "DELETE" }),
};