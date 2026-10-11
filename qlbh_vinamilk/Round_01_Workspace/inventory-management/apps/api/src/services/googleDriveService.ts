/**
 * Service: Kết nối Google Drive & Tải File Kiểm kê (Google Drive Service - Round 07 Fix 01)
 * File: apps/api/src/services/googleDriveService.ts
 *
 * Chức năng:
 * 1. Quản lý cấu hình Google Drive Folder (Folder ID: 1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk).
 * 2. Kiến trúc Dual-Driver Adapter (Mục 10 Master Prompt):
 *    - Live Driver: Kết nối Google Drive API v3 có hỗ trợ nextPageToken (>100 files),
 *      hỗ trợ cả file XLSX và Google Sheets native (qua endpoint export),
 *      và xác minh kết nối thực tế qua verifyConnection().
 *    - Simulation Driver: Quét dữ liệu kiểm thử thực tế từ fixtures, phục vụ QC/Dev
 *      nhưng có guard ngăn chặn tự ý chạy trên production.
 * 3. Bóc tách metadata file (id, name, mimeType, size, modifiedTime, md5Checksum, version).
 * 4. Tải nội dung nhị phân (ArrayBuffer) của file .xlsx.
 */

declare const process: any;

export interface GoogleDriveFile {
  id: string;
  name: string;
  mimeType: string;
  sizeBytes: number;
  modifiedTime: string;
  md5Checksum?: string;
  version?: string;
  isSheetNative?: boolean;
}

export interface GoogleDriveDriver {
  getMode(): "LIVE" | "SIMULATION";
  listFiles(folderId: string): Promise<GoogleDriveFile[]>;
  downloadFile(fileId: string, mimeType?: string): Promise<ArrayBuffer>;
  verifyConnection(folderId: string): Promise<{ success: boolean; error?: string }>;
}

export interface LiveDriverOptions {
  serviceAccountKey?: string | object | null;
  accessToken?: string | null;
  apiKey?: string | null;
}

function pemToDer(pem: string): ArrayBuffer {
  const b64 = pem
    .replace(/-----BEGIN[A-Z\s]+-----/g, "")
    .replace(/-----END[A-Z\s]+-----/g, "")
    .replace(/\s+/g, "");
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function base64UrlEncode(data: string | Uint8Array): string {
  let b64: string;
  if (typeof data === "string") {
    b64 = btoa(data);
  } else {
    let bin = "";
    for (let i = 0; i < data.length; i++) bin += String.fromCharCode(data[i]);
    b64 = btoa(bin);
  }
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/**
 * Tự động tạo và ký JWT cho Google Service Account bằng Web Crypto API
 */
export async function createServiceAccountSignedJwt(serviceAccount: {
  client_email: string;
  private_key: string;
  token_uri?: string;
}): Promise<string> {
  const der = pemToDer(serviceAccount.private_key);
  const key = await crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const payload = {
    iss: serviceAccount.client_email,
    scope: "https://www.googleapis.com/auth/drive.readonly",
    aud: serviceAccount.token_uri || "https://oauth2.googleapis.com/token",
    exp: now + 3600,
    iat: now
  };

  const encodedHeader = base64UrlEncode(JSON.stringify(header));
  const encodedPayload = base64UrlEncode(JSON.stringify(payload));
  const message = `${encodedHeader}.${encodedPayload}`;

  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(message)
  );

  return `${message}.${base64UrlEncode(new Uint8Array(signature))}`;
}

/**
 * Trao đổi signed JWT lấy OAuth2 Access Token từ Google
 */
export async function fetchServiceAccountAccessToken(serviceAccount: {
  client_email: string;
  private_key: string;
  token_uri?: string;
}): Promise<{ access_token: string; expires_in: number }> {
  const jwt = await createServiceAccountSignedJwt(serviceAccount);
  const tokenUri = serviceAccount.token_uri || "https://oauth2.googleapis.com/token";

  const res = await fetch(tokenUri, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: jwt
    })
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Google OAuth2 Token API từ chối (${res.status}): ${errText}`);
  }

  const data: any = await res.json();
  return {
    access_token: data.access_token,
    expires_in: data.expires_in || 3600
  };
}

/**
 * Driver Kết nối Trực tiếp Google Drive API v3 (Live Driver)
 * Hỗ trợ tự cấp mới Google Service Account Access Token lâu dài qua Web Crypto RS256
 */
export class LiveGoogleDriveDriver implements GoogleDriveDriver {
  private serviceAccountKey?: any | null = null;
  private accessToken?: string | null = null;
  private apiKey?: string | null = null;
  private cachedToken: string | null = null;
  private cachedExpiresAt: number = 0;

  constructor(options?: LiveDriverOptions | null) {
    if (options?.serviceAccountKey) {
      if (typeof options.serviceAccountKey === "string") {
        try {
          this.serviceAccountKey = JSON.parse(options.serviceAccountKey);
        } catch {
          this.serviceAccountKey = options.serviceAccountKey;
        }
      } else {
        this.serviceAccountKey = options.serviceAccountKey;
      }
    }
    this.accessToken = options?.accessToken || null;
    this.apiKey = options?.apiKey || null;
  }

  getMode(): "LIVE" {
    return "LIVE";
  }

  /**
   * Lấy header xác thực có hiệu lực (tự động refresh token nếu dùng Service Account)
   */
  async getEffectiveAuthHeader(): Promise<{ headers: Record<string, string>; urlKeyParam?: string }> {
    if (this.serviceAccountKey) {
      const now = Date.now();
      if (!this.cachedToken || this.cachedExpiresAt - now < 5 * 60 * 1000) {
        const tokenRes = await fetchServiceAccountAccessToken(this.serviceAccountKey);
        this.cachedToken = tokenRes.access_token;
        this.cachedExpiresAt = now + (tokenRes.expires_in || 3600) * 1000;
      }
      return { headers: { Authorization: `Bearer ${this.cachedToken}` } };
    }

    if (this.accessToken) {
      return { headers: { Authorization: `Bearer ${this.accessToken}` } };
    }

    if (this.apiKey) {
      return { headers: {}, urlKeyParam: this.apiKey };
    }

    throw new Error("Chưa cấu hình Google Service Account credentials (GDRIVE_SERVICE_ACCOUNT_KEY). Trạng thái: BLOCKED_FOR_LIVE.");
  }

  /**
   * Xác minh kết nối thực tế tới Google Drive API
   */
  async verifyConnection(folderId: string): Promise<{ success: boolean; error?: string }> {
    if (!this.serviceAccountKey && !this.accessToken && !this.apiKey) {
      return {
        success: false,
        error: "Chưa cấu hình Google Service Account credentials (GDRIVE_SERVICE_ACCOUNT_KEY). Trạng thái tích hợp: BLOCKED_FOR_LIVE."
      };
    }

    try {
      const auth = await this.getEffectiveAuthHeader();
      const query = encodeURIComponent(`'${folderId}' in parents and trashed = false`);
      let url = `https://www.googleapis.com/drive/v3/files?q=${query}&fields=files(id)&pageSize=1`;
      if (auth.urlKeyParam) {
        url += `&key=${auth.urlKeyParam}`;
      }

      const res = await fetch(url, { headers: auth.headers });
      if (!res.ok) {
        const errText = await res.text();
        return {
          success: false,
          error: `Google Drive API từ chối (${res.status}): ${errText}`
        };
      }

      return { success: true };
    } catch (err: any) {
      return {
        success: false,
        error: `Lỗi kết nối hoặc chứng thực Google Drive: ${err.message || String(err)}`
      };
    }
  }

  /**
   * Quét danh sách file trong thư mục Google Drive có hỗ trợ phân trang nextPageToken (>100 files)
   * và cảnh báo rõ ràng khi vượt quá giới hạn an toàn 2.000 files (P2-02)
   */
  async listFiles(folderId: string): Promise<GoogleDriveFile[]> {
    const auth = await this.getEffectiveAuthHeader();

    // Hỗ trợ cả file XLSX (.xlsx, mimeType Excel) và Google Sheets native (P2-04)
    const query = encodeURIComponent(
      `'${folderId}' in parents and trashed = false and (name contains '.xlsx' or mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or mimeType = 'application/vnd.google-apps.spreadsheet')`
    );

    const allFiles: GoogleDriveFile[] = [];
    let pageToken: string | null = null;
    let pageCount = 0;
    const maxPages = 20; // Hỗ trợ tối đa 20 trang x 100 file = 2.000 files (P2-01)

    do {
      pageCount++;
      let url = `https://www.googleapis.com/drive/v3/files?q=${query}&fields=nextPageToken,files(id,name,mimeType,size,modifiedTime,md5Checksum,version)&pageSize=100`;
      if (pageToken) {
        url += `&pageToken=${encodeURIComponent(pageToken)}`;
      }
      if (auth.urlKeyParam) {
        url += `&key=${auth.urlKeyParam}`;
      }

      const res = await fetch(url, { headers: auth.headers });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Google Drive API trả về lỗi (${res.status}): ${errText}`);
      }

      const data: any = await res.json();
      const files: any[] = data.files || [];

      for (const f of files) {
        const isSheetNative = f.mimeType === "application/vnd.google-apps.spreadsheet";
        allFiles.push({
          id: f.id,
          name: isSheetNative && !f.name.endsWith(".xlsx") ? `${f.name}.xlsx` : f.name,
          mimeType: f.mimeType,
          sizeBytes: f.size ? parseInt(f.size, 10) : 0,
          modifiedTime: f.modifiedTime || new Date().toISOString(),
          md5Checksum: f.md5Checksum,
          version: f.version,
          isSheetNative
        });
      }

      pageToken = data.nextPageToken || null;
      if (pageToken && pageCount >= maxPages) {
        // P2-02: Không âm thầm cắt ngắn danh sách! Báo lỗi rõ ràng để xử lý
        throw new Error(
          `Vượt quá giới hạn phân trang an toàn (${maxPages} trang / 2.000 file). Danh sách tệp bị cắt ngang. Vui lòng phân nhóm hoặc dọn dẹp thư mục Google Drive.`
        );
      }
    } while (pageToken && pageCount < maxPages);

    return allFiles;
  }

  /**
   * Tải nội dung nhị phân (ArrayBuffer) của file
   * Nếu là Google Sheets native, tự động gọi API /export sang XLSX (P2-04)
   */
  async downloadFile(fileId: string, mimeType?: string): Promise<ArrayBuffer> {
    const auth = await this.getEffectiveAuthHeader();

    let url: string;
    if (mimeType === "application/vnd.google-apps.spreadsheet") {
      url = `https://www.googleapis.com/drive/v3/files/${fileId}/export?mimeType=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`;
    } else {
      url = `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`;
    }
    if (auth.urlKeyParam) {
      url += (url.includes("?") ? "&" : "?") + `key=${auth.urlKeyParam}`;
    }

    const res = await fetch(url, { headers: auth.headers });
    if (!res.ok) {
      throw new Error(`Không thể tải file ${fileId} từ Google Drive (${res.status})`);
    }

    return await res.arrayBuffer();
  }
}

/**
 * Driver Mô phỏng / Kiểm thử Google Drive (Simulation Driver)
 * Được thiết kế đặc biệt theo mục 10 của Master Prompt:
 * "Thiếu credentials Round 07/10 -> hoàn thiện code + mock/fixture tests và xin quyền bổ sung."
 */
export class SimulationGoogleDriveDriver implements GoogleDriveDriver {
  private mockFiles: Map<string, { meta: GoogleDriveFile; buffer: ArrayBuffer }>;

  constructor(initialFiles: Array<{ meta: GoogleDriveFile; buffer: ArrayBuffer }> = []) {
    this.mockFiles = new Map();
    for (const f of initialFiles) {
      this.mockFiles.set(f.meta.id, f);
    }
  }

  getMode(): "SIMULATION" {
    return "SIMULATION";
  }

  async verifyConnection(_folderId: string): Promise<{ success: boolean; error?: string }> {
    return { success: true };
  }

  private async loadDefaultFixturesIfEmpty() {
    if (this.mockFiles.size > 0) return;

    try {
      const cwd = typeof process !== "undefined" && typeof process.cwd === "function" ? process.cwd() : "";
      const fsPkg = "node:fs";
      const pathPkg = "node:path";
      const fsMod: any = await import(/* @vite-ignore */ fsPkg);
      const pathMod: any = await import(/* @vite-ignore */ pathPkg);

      const candidateDirs = [
        pathMod.resolve(cwd, "fixtures/Kiem ke"),
        pathMod.resolve(cwd, "../fixtures/Kiem ke"),
        pathMod.resolve(cwd, "../../fixtures/Kiem ke"),
        pathMod.resolve(cwd, "../../../Data Source/Kiem ke"),
        pathMod.resolve(cwd, "../../Data Source/Kiem ke")
      ];

      for (const dir of candidateDirs) {
        if (fsMod.existsSync(dir)) {
          const files = fsMod.readdirSync(dir).filter((f: string) => f.endsWith(".xlsx"));
          if (files.length > 0) {
            files.sort().forEach((filename: string, idx: number) => {
              const fullPath = pathMod.join(dir, filename);
              const nodeBuffer = fsMod.readFileSync(fullPath);
              const arrayBuffer = nodeBuffer.buffer.slice(
                nodeBuffer.byteOffset,
                nodeBuffer.byteOffset + nodeBuffer.byteLength
              );
              const stat = fsMod.statSync(fullPath);
              const id = `gdrive_${1001 + idx}`;
              this.mockFiles.set(id, {
                meta: {
                  id,
                  name: filename,
                  mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                  sizeBytes: arrayBuffer.byteLength,
                  modifiedTime: stat.mtime.toISOString(),
                  version: "1",
                  isSheetNative: false
                },
                buffer: arrayBuffer
              });
            });
            break;
          }
        }
      }
    } catch {
      // Ignored if fs not available
    }
  }

  addFile(meta: GoogleDriveFile, buffer: ArrayBuffer) {
    this.mockFiles.set(meta.id, { meta, buffer });
  }

  removeFile(fileId: string) {
    this.mockFiles.delete(fileId);
  }

  clearFiles() {
    this.mockFiles.clear();
  }

  async listFiles(_folderId: string): Promise<GoogleDriveFile[]> {
    await this.loadDefaultFixturesIfEmpty();
    return Array.from(this.mockFiles.values()).map((item) => item.meta);
  }

  async downloadFile(fileId: string, _mimeType?: string): Promise<ArrayBuffer> {
    await this.loadDefaultFixturesIfEmpty();
    const item = this.mockFiles.get(fileId);
    if (!item) {
      throw new Error(`Không tìm thấy file trên Google Drive (Mô phỏng): ID ${fileId}`);
    }
    return item.buffer;
  }
}

let activeDriver: GoogleDriveDriver = new SimulationGoogleDriveDriver();

export function setGoogleDriveDriver(driver: GoogleDriveDriver) {
  activeDriver = driver;
}

export function getGoogleDriveDriver(env?: any): GoogleDriveDriver {
  if (env?.__TEST_DRIVER__) {
    return env.__TEST_DRIVER__;
  }

  // P2-09: Bảo đảm không tự động dùng SIMULATION trên môi trường production nếu không có cờ cho phép rõ ràng
  if (env?.ENVIRONMENT === "production" && !env?.ENABLE_SIMULATION_DRIVER) {
    return new LiveGoogleDriveDriver({
      serviceAccountKey: env?.GDRIVE_SERVICE_ACCOUNT_KEY,
      accessToken: env?.GDRIVE_ACCESS_TOKEN,
      apiKey: env?.GDRIVE_API_KEY
    });
  }

  // Nếu env có Service Account Key, Token hoặc API key thật -> khởi tạo Live Driver
  if (env?.GDRIVE_SERVICE_ACCOUNT_KEY || env?.GDRIVE_ACCESS_TOKEN || env?.GDRIVE_API_KEY) {
    return new LiveGoogleDriveDriver({
      serviceAccountKey: env?.GDRIVE_SERVICE_ACCOUNT_KEY,
      accessToken: env?.GDRIVE_ACCESS_TOKEN,
      apiKey: env?.GDRIVE_API_KEY
    });
  }

  return activeDriver;
}
