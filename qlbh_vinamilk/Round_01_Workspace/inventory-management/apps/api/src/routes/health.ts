import { createSuccessResponse } from "../middleware/errorHandler.js";

export function handleHealthCheck(request: Request, env: any, requestId: string): Response {
  return createSuccessResponse({
    status: "ok",
    service: "inventory-management-api",
    timestamp: new Date().toISOString()
  }, 200, { requestId });
}
