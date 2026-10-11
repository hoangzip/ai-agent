/**
 * Service: Điều phối Tự động Đồng bộ Dữ liệu Đám mây (Sync Service - Round 07 Fix 01)
 * File: apps/api/src/services/syncService.ts
 *
 * Chức năng:
 * 1. Quản lý nguồn đồng bộ Google Drive (sync_sources).
 * 2. Thực thi quy trình đồng bộ tự động / thủ công (triggerSync).
 * 3. Bắt tay với Google Drive driver, tải file (hỗ trợ cả Sheets native) và tích hợp với engine Round 04.
 * 4. Chống trùng lặp & Xung đột phiên bản (Idempotency & Version Conflict):
 *    - Cùng revision/checksum + status COMPLETED -> An toàn để SKIP.
 *    - Khác revision/checksum (file nguồn bị sửa trên Drive) -> Phát hiện CONFLICT,
 *      không âm thầm skip và không âm thầm ghi đè snapshot lịch sử.
 * 5. Concurrency Lock: Chặn các đợt đồng bộ chạy chồng bằng database lease lock kèm recovery timeout.
 * 6. Partial Failure Handling: Xử lý minh bạch các đợt chạy có file lỗi (PARTIAL), không tự ý gán COMPLETED 100%.
 * 7. Ghi nhận lịch sử chi tiết vào bảng sync_runs và audit_logs.
 */

import { getGoogleDriveDriver, GoogleDriveFile } from "./googleDriveService.js";
import { parseInventoryExcel } from "./excelParser.js";
import { importSnapshot } from "./inventoryService.js";

export const DEFAULT_GDRIVE_FOLDER_ID = "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk";
export const DEFAULT_GDRIVE_FOLDER_NAME = "Kiem ke hang hoa Vinamilk";

/**
 * Đảm bảo nguồn đồng bộ mặc định Google Drive đã tồn tại trong DB
 */
export async function ensureDefaultSyncSource(db: any, folderId: string = DEFAULT_GDRIVE_FOLDER_ID) {
  let source = await db
    .prepare("SELECT * FROM sync_sources WHERE provider = 'GOOGLE_DRIVE' AND folder_id = ? LIMIT 1")
    .bind(folderId)
    .first();

  if (!source) {
    const insertRes = await db
      .prepare(
        `INSERT INTO sync_sources (provider, folder_id, folder_name, is_active, sync_interval_minutes)
         VALUES ('GOOGLE_DRIVE', ?, ?, 1, 60)`
      )
      .bind(folderId, DEFAULT_GDRIVE_FOLDER_NAME)
      .run();

    const newId = insertRes.meta?.last_row_id || 1;
    source = await db
      .prepare("SELECT * FROM sync_sources WHERE id = ?")
      .bind(newId)
      .first();
  }

  return source;
}

/**
 * Lấy trạng thái đồng bộ hiện tại của hệ thống (kèm kiểm tra kết nối LIVE thực tế)
 */
export async function getSyncStatus(db: any, env?: any) {
  const source = await ensureDefaultSyncSource(db, env?.GDRIVE_FOLDER_ID || DEFAULT_GDRIVE_FOLDER_ID);
  const driver = getGoogleDriveDriver(env);

  let isLiveConnected = false;
  let connectionStatus: "SIMULATION" | "LIVE_ACTIVE" | "BLOCKED_FOR_LIVE" = "SIMULATION";
  let connectionError: string | null = null;

  if (driver.getMode() === "LIVE") {
    // P1-03 & P2-08: is_live_connected chỉ true khi đã xác minh API thực tế thành công
    const testResult = await driver.verifyConnection(source.folder_id);
    if (testResult.success) {
      isLiveConnected = true;
      connectionStatus = "LIVE_ACTIVE";
    } else {
      isLiveConnected = false;
      connectionStatus = "BLOCKED_FOR_LIVE";
      connectionError = testResult.error || "Chưa thể kết nối tới Google Drive LIVE (Thiếu Service Account credentials).";
    }
  } else {
    connectionStatus = "SIMULATION";
    isLiveConnected = false;
    // P2-09: Nếu chạy production mà thiếu credentials -> báo rõ ràng BLOCKED_FOR_LIVE
    if (env?.ENVIRONMENT === "production" && !env?.ENABLE_SIMULATION_DRIVER) {
      connectionStatus = "BLOCKED_FOR_LIVE";
      connectionError = "Môi trường Production chưa được cấp Google Service Account credentials.";
    }
  }

  // Lấy đợt đồng bộ gần nhất
  const lastRun = await db
    .prepare(
      `SELECT * FROM sync_runs 
       WHERE source_id = ? 
       ORDER BY started_at DESC, id DESC 
       LIMIT 1`
    )
    .bind(source.id)
    .first();

  // Thống kê tổng số đợt chạy
  const statsRow = await db
    .prepare(
      `SELECT 
         COUNT(*) as total_runs,
         SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as successful_runs,
         SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_runs,
         SUM(COALESCE(files_imported, 0)) as total_files_imported,
         SUM(COALESCE(files_skipped, 0)) as total_files_skipped
       FROM sync_runs 
       WHERE source_id = ?`
    )
    .bind(source.id)
    .first();

  return {
    source: {
      id: source.id,
      provider: source.provider,
      folder_id: source.folder_id,
      folder_name: source.folder_name,
      is_active: Boolean(source.is_active),
      sync_interval_minutes: source.sync_interval_minutes || 60,
      last_sync_at: source.last_sync_at
    },
    driver_mode: driver.getMode(),
    is_live_connected: isLiveConnected,
    connection_status: connectionStatus,
    connection_error: connectionError,
    scheduler_info: "Cloudflare Cron Trigger (0 * * * *) / Google Apps Script Time-Driven Trigger (Chu kỳ: 60 phút)",
    last_run: lastRun || null,
    metrics: {
      total_runs: Number(statsRow?.total_runs || 0),
      successful_runs: Number(statsRow?.successful_runs || 0),
      failed_runs: Number(statsRow?.failed_runs || 0),
      total_files_imported: Number(statsRow?.total_files_imported || 0),
      total_files_skipped: Number(statsRow?.total_files_skipped || 0)
    }
  };
}

/**
 * Lấy lịch sử các đợt đồng bộ (sync_runs) có phân trang
 */
export async function getSyncRuns(db: any, options: { page?: number; limit?: number } = {}) {
  const page = Math.max(1, options.page || 1);
  const limit = Math.min(100, Math.max(1, options.limit || 20));
  const offset = (page - 1) * limit;

  const countRow = await db
    .prepare("SELECT COUNT(*) as total FROM sync_runs")
    .first();
  const total = Number(countRow?.total || 0);

  let rows: any[] = [];
  try {
    rows = (await db
      .prepare(
        `SELECT r.id, r.source_id, r.triggered_by, r.status, r.outcome,
                r.files_detected, r.files_imported, r.files_skipped, r.files_conflict,
                r.error_message, r.started_at, r.finished_at,
                s.folder_id, s.folder_name, s.provider
         FROM sync_runs r
         LEFT JOIN sync_sources s ON r.source_id = s.id
         ORDER BY r.started_at DESC, r.id DESC
         LIMIT ? OFFSET ?`
      )
      .bind(limit, offset)
      .all())?.results || [];
  } catch {
    rows = (await db
      .prepare(
        `SELECT r.id, r.source_id, r.triggered_by, r.status,
                r.files_detected, r.files_imported, r.files_skipped, r.files_conflict,
                r.error_message, r.started_at, r.finished_at,
                s.folder_id, s.folder_name, s.provider
         FROM sync_runs r
         LEFT JOIN sync_sources s ON r.source_id = s.id
         ORDER BY r.started_at DESC, r.id DESC
         LIMIT ? OFFSET ?`
      )
      .bind(limit, offset)
      .all())?.results || [];
  }

  // Chuẩn hóa trường outcome cho từng bản ghi (nhất quán DB, API và UI)
  for (const r of rows) {
    if (!r.outcome) {
      if (r.error_message?.includes("PARTIAL") || (r.files_imported > 0 && r.files_skipped > 0)) {
        r.outcome = "PARTIAL";
      } else if (r.status === "COMPLETED") {
        r.outcome = "SUCCESS";
      } else if (r.files_conflict > 0) {
        r.outcome = "CONFLICT";
      } else {
        r.outcome = "FAILED";
      }
    }
  }

  return {
    items: rows,
    pagination: {
      page,
      limit,
      total,
      total_pages: Math.ceil(total / limit)
    }
  };
}

/**
 * Thu nhận khóa đồng bộ nguyên tử (Atomic Concurrency Lease Lock)
 * Sử dụng PRIMARY KEY trên source_id trong bảng sync_locks để đảm bảo tính nguyên tử tuyệt đối trong D1 / SQLite.
 */
export async function acquireSyncLock(
  db: any,
  sourceId: number,
  leaseDurationMs: number = 10 * 60 * 1000 // 10 phút lease
): Promise<{ acquired: boolean; lockToken: string; error?: string }> {
  try {
    await db
      .prepare(
        `CREATE TABLE IF NOT EXISTS sync_locks (
          source_id INTEGER PRIMARY KEY,
          lock_token TEXT NOT NULL,
          run_id INTEGER,
          locked_at TEXT NOT NULL,
          lease_expires_at TEXT NOT NULL
        )`
      )
      .run();
  } catch {
    // Ignored
  }

  const lockToken = typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `lock_${Date.now()}_${Math.random()}`;
  const nowIso = new Date().toISOString();
  const expiresIso = new Date(Date.now() + leaseDurationMs).toISOString();

  // BƯỚC 1: Thử INSERT nguyên tử dựa trên PRIMARY KEY / UNIQUE constraint
  try {
    await db
      .prepare(
        `INSERT INTO sync_locks (source_id, lock_token, locked_at, lease_expires_at)
         VALUES (?, ?, ?, ?)`
      )
      .bind(sourceId, lockToken, nowIso, expiresIso)
      .run();

    return { acquired: true, lockToken };
  } catch (insertErr: any) {
    const errMsg = String(insertErr?.message || insertErr);
    if (!errMsg.includes("UNIQUE") && !errMsg.includes("constraint")) {
      throw insertErr;
    }
  }

  // BƯỚC 2: UNIQUE vi phạm -> Kiểm tra và thu hồi khóa quá hạn (Stale Lease Recovery) bằng UPDATE nguyên tử có điều kiện
  const updateRes = await db
    .prepare(
      `UPDATE sync_locks
       SET lock_token = ?,
           locked_at = ?,
           lease_expires_at = ?
       WHERE source_id = ? AND lease_expires_at < ?`
    )
    .bind(lockToken, nowIso, expiresIso, sourceId, nowIso)
    .run();

  const changes = updateRes?.meta?.changes ?? (updateRes as any)?.changes ?? 0;
  if (changes > 0) {
    return { acquired: true, lockToken };
  }

  // BƯỚC 3: Khóa đang còn hạn và do tiến trình khác giữ -> Từ chối nguyên tử!
  return {
    acquired: false,
    lockToken: "",
    error: `Đang có một tiến trình đồng bộ khác thực thi cho nguồn dữ liệu #${sourceId}. Vui lòng chờ đợt trước hoàn tất.`
  };
}

/**
 * Giải phóng khóa đồng bộ nguyên tử
 */
export async function releaseSyncLock(db: any, sourceId: number, lockToken: string): Promise<void> {
  if (!lockToken) return;
  try {
    await db
      .prepare("DELETE FROM sync_locks WHERE source_id = ? AND lock_token = ?")
      .bind(sourceId, lockToken)
      .run();
  } catch {
    // Ignored
  }
}

/**
 * Thực thi quy trình đồng bộ dữ liệu từ Google Drive
 * (Có Atomic Concurrency Lock, Driver Injection, Dedup theo Revision, Outcome Tracking)
 */
export async function triggerSync(
  db: any,
  env?: any,
  options: {
    triggeredBy?: "SCHEDULED" | "MANUAL";
    userId?: number;
    folderId?: string;
    driver?: any;
  } = {}
) {
  const triggeredBy = options.triggeredBy || "MANUAL";
  const userId = options.userId || 1;
  const folderId = options.folderId || env?.GDRIVE_FOLDER_ID || DEFAULT_GDRIVE_FOLDER_ID;

  const source = await ensureDefaultSyncSource(db, folderId);
  const driver = options.driver || (env?.__TEST_DRIVER__ ?? getGoogleDriveDriver(env));

  // 1. P1-02: Atomic Concurrency Lock
  const lock = await acquireSyncLock(db, source.id, 10 * 60 * 1000);
  if (!lock.acquired) {
    const err: any = new Error(
      lock.error || `Đợt đồng bộ đang được thực thi cho nguồn #${source.id}. Vui lòng chờ đợt trước hoàn tất.`
    );
    err.code = "SYNC_ALREADY_RUNNING";
    err.status = 409;
    throw err;
  }

  const lockToken = lock.lockToken;
  let runId = 0;

  try {
    // 2. Tạo bản ghi sync_run ở trạng thái RUNNING
    const insertRunRes = await db
      .prepare(
        `INSERT INTO sync_runs (source_id, triggered_by, status, files_detected, files_imported, files_skipped, files_conflict, started_at)
         VALUES (?, ?, 'RUNNING', 0, 0, 0, 0, datetime('now', 'utc'))`
      )
      .bind(source.id, triggeredBy)
      .run();

    runId = insertRunRes.meta?.last_row_id || 1;

    try {
      await db
        .prepare("UPDATE sync_locks SET run_id = ? WHERE source_id = ? AND lock_token = ?")
        .bind(runId, source.id, lockToken)
        .run();
    } catch {
      // Ignored
    }

  let filesDetected = 0;
  let filesImported = 0;
  let filesSkipped = 0;
  let filesConflict = 0;
  let filesFailed = 0;
  const processDetails: any[] = [];
  let errorMessage: string | null = null;
  let finalStatus: "COMPLETED" | "FAILED" = "COMPLETED";
  let outcome: "SUCCESS" | "PARTIAL" | "FAILED" | "CONFLICT" = "SUCCESS";

  try {
    // 3. Quét danh sách file từ Google Drive (có hỗ trợ nextPageToken và Google Sheets export)
    const driveFiles: GoogleDriveFile[] = await driver.listFiles(source.folder_id);
    filesDetected = driveFiles.length;

    // 4. Duyệt từng file để kiểm tra và nạp
    for (const file of driveFiles) {
      const detail: any = {
        file_id: file.id,
        filename: file.name,
        size_bytes: file.sizeBytes,
        action: "SKIPPED",
        reason: ""
      };

      try {
        // 4a. Tải nội dung nhị phân của file (hỗ trợ cả Sheets native qua export)
        const fileBuffer = await driver.downloadFile(file.id, file.mimeType);

        // 4b. Bóc tách và kiểm tra hợp đồng dữ liệu Excel 15 cột
        const parsed = await parseInventoryExcel(fileBuffer, file.name);
        if (!parsed.isValid) {
          filesFailed++;
          detail.action = "FAILED";
          detail.reason = `Dữ liệu không hợp lệ: ${(parsed.errors || []).map((e: any) => e.message).join("; ")}`;
          processDetails.push(detail);
          continue;
        }

        const currentRevision = file.version || file.md5Checksum || parsed.file_sha256;

        // 4c. P1-02: Kiểm tra Document Identity & Source Revision / Hash
        const existingSnapshot = await db
          .prepare(
            `SELECT id, full_code, ticket_number, status, is_deleted, source_file_id, source_revision, file_sha256, content_hash 
             FROM inventory_files 
             WHERE (source_file_id = ? OR full_code = ? OR (source_filename = ? AND status = 'COMPLETED')) 
               AND is_deleted = 0 
             LIMIT 1`
          )
          .bind(file.id, parsed.metadata.full_code, file.name)
          .first();

        if (existingSnapshot) {
          const isSameRevision =
            (existingSnapshot.source_revision && existingSnapshot.source_revision === currentRevision) ||
            existingSnapshot.file_sha256 === parsed.file_sha256 ||
            existingSnapshot.content_hash === parsed.content_hash;

          if (isSameRevision && existingSnapshot.status === "COMPLETED") {
            // Nguồn KHÔNG ĐỔI -> An toàn để SKIP (Idempotency chuẩn)
            filesSkipped++;
            detail.action = "SKIPPED";
            detail.reason = `Nguồn không thay đổi (Khớp revision #${existingSnapshot.ticket_number} - ${existingSnapshot.full_code})`;
            processDetails.push(detail);
            continue;
          } else {
            // Nguồn BỊ THAY ĐỔI TRÊN DRIVE (khác revision hoặc khác content_hash nhưng cùng ID hoặc cùng mã chứng từ)
            // Tuyệt đối không âm thầm skip và không âm thầm ghi đè snapshot lịch sử!
            filesConflict++;
            detail.action = "CONFLICT";
            detail.reason = `Phát hiện xung đột phiên bản: Tệp trên Google Drive đã bị thay đổi (Rev: ${currentRevision || "Mới"}). Không ghi đè snapshot #${existingSnapshot.ticket_number} đã hoàn tất.`;
            processDetails.push(detail);
            continue;
          }
        }

        // 4d. Nhập khẩu vào Staging và tự động duyệt (autoCommit)
        try {
          const importResult = await importSnapshot(db, parsed, {
            userId,
            autoCommit: true,
            sourceType: "GDRIVE_SYNC",
            sourceFileId: file.id,
            sourceRevision: currentRevision
          });

          filesImported++;
          detail.action = "IMPORTED";
          detail.snapshot_id = importResult.id;
          detail.ticket_number = importResult.ticket_number;
          detail.total_quantity = importResult.total_quantity;
        } catch (importErr: any) {
          if (importErr.code === "CONFLICT") {
            filesConflict++;
            detail.action = "CONFLICT";
            detail.reason = importErr.message || "Xung đột dữ liệu mã chứng từ";
          } else if (importErr.code === "ALREADY_IMPORTED") {
            filesSkipped++;
            detail.action = "SKIPPED";
            detail.reason = importErr.message || "Chứng từ đã tồn tại";
          } else {
            throw importErr;
          }
        }
      } catch (fileErr: any) {
        filesFailed++;
        detail.action = "FAILED";
        detail.reason = fileErr.message || String(fileErr);
      }

      processDetails.push(detail);
    }

    // 5. P2-01: Phân loại outcome nhất quán (SUCCESS, PARTIAL, FAILED, CONFLICT)
    if (filesFailed > 0) {
      if (filesImported > 0 || filesSkipped > 0) {
        outcome = "PARTIAL";
        finalStatus = "FAILED";
        errorMessage = `Hoàn tất một phần (PARTIAL): Nạp thành công ${filesImported}, bỏ qua ${filesSkipped}, xung đột ${filesConflict}, lỗi ${filesFailed} file.`;
      } else {
        outcome = "FAILED";
        finalStatus = "FAILED";
        errorMessage = `Toàn bộ ${filesFailed} file đều thất bại khi xử lý.`;
      }
    } else if (filesConflict > 0 && filesImported === 0 && filesSkipped === 0) {
      outcome = "CONFLICT";
      finalStatus = "FAILED";
      errorMessage = `Phát hiện xung đột phiên bản trên toàn bộ ${filesConflict} file kiểm kê.`;
    } else if (filesConflict > 0 && (filesImported > 0 || filesSkipped > 0)) {
      outcome = "PARTIAL";
      finalStatus = "COMPLETED";
      errorMessage = `Hoàn tất một phần (PARTIAL): Nạp ${filesImported}, bỏ qua ${filesSkipped}, xung đột ${filesConflict} file.`;
    } else {
      outcome = "SUCCESS";
      finalStatus = "COMPLETED";
    }
  } catch (err: any) {
    finalStatus = "FAILED";
    errorMessage = `Lỗi tiến trình quét Google Drive: ${err.message || String(err)}`;
  }

  // 6. Cập nhật kết quả đợt chạy vào sync_runs (kèm outcome)
  try {
    await db
      .prepare(
        `UPDATE sync_runs 
         SET status = ?, 
             outcome = ?,
             files_detected = ?, 
             files_imported = ?, 
             files_skipped = ?, 
             files_conflict = ?, 
             error_message = ?, 
             finished_at = datetime('now', 'utc')
         WHERE id = ?`
      )
      .bind(
        finalStatus,
        outcome,
        filesDetected,
        filesImported,
        filesSkipped,
        filesConflict,
        errorMessage,
        runId
      )
      .run();
  } catch {
    await db
      .prepare(
        `UPDATE sync_runs 
         SET status = ?, 
             files_detected = ?, 
             files_imported = ?, 
             files_skipped = ?, 
             files_conflict = ?, 
             error_message = ?, 
             finished_at = datetime('now', 'utc')
         WHERE id = ?`
      )
      .bind(
        finalStatus,
        filesDetected,
        filesImported,
        filesSkipped,
        filesConflict,
        errorMessage,
        runId
      )
      .run();
  }

  // 7. Cập nhật thời điểm last_sync_at cho sync_sources
  await db
    .prepare("UPDATE sync_sources SET last_sync_at = datetime('now', 'utc') WHERE id = ?")
    .bind(source.id)
    .run();

  // 8. Ghi log kiểm toán audit_logs
  await db
    .prepare(
      `INSERT INTO audit_logs (user_id, action, target_type, target_id, details)
       VALUES (?, 'SYNC_GOOGLE_DRIVE', 'SYNC_RUN', ?, ?)`
    )
    .bind(
      userId,
      String(runId),
      JSON.stringify({
        triggered_by: triggeredBy,
        driver_mode: driver.getMode(),
        files_detected: filesDetected,
        files_imported: filesImported,
        files_skipped: filesSkipped,
        files_conflict: filesConflict,
        files_failed: filesFailed,
        status: finalStatus,
        outcome
      })
    )
    .run();

  return {
    run_id: runId,
    status: finalStatus,
    outcome,
    driver_mode: driver.getMode(),
    folder_id: source.folder_id,
    triggered_by: triggeredBy,
    summary: {
      files_detected: filesDetected,
      files_imported: filesImported,
      files_skipped: filesSkipped,
      files_conflict: filesConflict,
      files_failed: filesFailed
    },
    error_message: errorMessage,
    details: processDetails
  };
  } finally {
    // Luôn giải phóng atomic lock khi kết thúc (dù thành công hay gặp lỗi)
    await releaseSyncLock(db, source.id, lockToken);
  }
}
