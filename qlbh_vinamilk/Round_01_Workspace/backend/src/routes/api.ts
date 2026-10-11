/**
 * File: backend/src/routes/api.ts
 * Cloudflare Pages Functions / Worker Router Skeleton
 * Xử lý các endpoint: /api/health, /api/snapshots, /api/snapshots/:id, /api/compare
 */

export interface Env {
  DB: any; // Cloudflare D1 Database binding
}

export async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  // 1. Health check
  if (path === "/api/health" && method === "GET") {
    return new Response(JSON.stringify({
      status: "ok",
      version: "1.0.0",
      service: "inventory-management-backend",
      timestamp: new Date().toISOString()
    }), {
      headers: { "Content-Type": "application/json; charset=utf-8" }
    });
  }

  // 2. Danh sách snapshots (hỗ trợ filter theo date, store_code, shift, pagination)
  if (path === "/api/snapshots" && method === "GET") {
    const page = parseInt(url.searchParams.get("page") || "1", 10);
    const limit = Math.min(parseInt(url.searchParams.get("limit") || "20", 10), 100);
    const offset = (page - 1) * limit;
    const date = url.searchParams.get("date");
    const storeCode = url.searchParams.get("store_code");

    let query = "SELECT * FROM inventory_snapshots WHERE is_deleted = 0";
    const params: any[] = [];

    if (date) {
      query += " AND inventory_date = ?";
      params.push(date);
    }
    if (storeCode) {
      query += " AND store_code = ?";
      params.push(storeCode);
    }

    query += " ORDER BY inventory_date DESC, id DESC LIMIT ? OFFSET ?";
    params.push(limit, offset);

    const { results } = await env.DB.prepare(query).bind(...params).all();
    const countResult = await env.DB.prepare(
      "SELECT COUNT(*) as total FROM inventory_snapshots WHERE is_deleted = 0"
    ).first();

    return new Response(JSON.stringify({
      data: results,
      pagination: {
        page,
        limit,
        total: countResult ? countResult.total : 0
      }
    }), {
      headers: { "Content-Type": "application/json; charset=utf-8" }
    });
  }

  // 3. Chi tiết Snapshot
  const snapshotDetailMatch = path.match(/^\/api\/snapshots\/(\d+)$/);
  if (snapshotDetailMatch && method === "GET") {
    const id = parseInt(snapshotDetailMatch[1], 10);
    const snapshot = await env.DB.prepare(
      "SELECT * FROM inventory_snapshots WHERE id = ? AND is_deleted = 0"
    ).bind(id).first();

    if (!snapshot) {
      return new Response(JSON.stringify({ error: "Không tìm thấy chứng từ kiểm kê" }), {
        status: 404,
        headers: { "Content-Type": "application/json; charset=utf-8" }
      });
    }

    return new Response(JSON.stringify({ data: snapshot }), {
      headers: { "Content-Type": "application/json; charset=utf-8" }
    });
  }

  // 4. Chi tiết các Items của Snapshot
  const snapshotItemsMatch = path.match(/^\/api\/snapshots\/(\d+)\/items$/);
  if (snapshotItemsMatch && method === "GET") {
    const id = parseInt(snapshotItemsMatch[1], 10);
    const { results } = await env.DB.prepare(
      "SELECT * FROM inventory_items WHERE snapshot_id = ? ORDER BY stt ASC"
    ).bind(id).all();

    return new Response(JSON.stringify({ data: results }), {
      headers: { "Content-Type": "application/json; charset=utf-8" }
    });
  }

  // 404 Not Found fallback
  return new Response(JSON.stringify({ error: "Endpoint không tồn tại" }), {
    status: 404,
    headers: { "Content-Type": "application/json; charset=utf-8" }
  });
}
