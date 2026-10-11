/**
 * Cloudflare Pages Function Proxy
 * Định tuyến toàn bộ request /api/* tới API Worker backend khi triển khai cùng domain (Same-Origin).
 */

interface Env {
  API_WORKER?: { fetch: typeof fetch };
  API_WORKER_URL?: string;
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env } = context;
  const url = new URL(request.url);

  // Phương án 1: Service Binding trực tiếp (Zero network latency, bảo mật cao nhất)
  if (env.API_WORKER && typeof env.API_WORKER.fetch === "function") {
    return env.API_WORKER.fetch(request);
  }

  // Phương án 2: Reverse Proxy qua URL Worker đã cấu hình (API_WORKER_URL)
  if (env.API_WORKER_URL) {
    const upstreamUrl = new URL(url.pathname + url.search, env.API_WORKER_URL);
    const proxyRequest = new Request(upstreamUrl.toString(), request);
    return fetch(proxyRequest);
  }

  // Fallback thông báo cấu hình
  return new Response(
    JSON.stringify({
      success: false,
      error: {
        code: "PAGES_ROUTING_UNCONFIGURED",
        message: "Chưa cấu hình API_WORKER service binding hoặc API_WORKER_URL trong Cloudflare Pages Environment.",
        details: {
          path: url.pathname,
          hint: "Cấu hình Service Binding 'API_WORKER' hoặc biến môi trường 'API_WORKER_URL' trong Pages Settings."
        }
      }
    }),
    {
      status: 502,
      headers: { "Content-Type": "application/json; charset=utf-8" }
    }
  );
};
