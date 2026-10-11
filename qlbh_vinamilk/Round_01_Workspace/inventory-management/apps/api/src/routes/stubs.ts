import { createErrorResponse } from "../middleware/errorHandler.js";

export function handleUnimplementedModule(
  moduleName: string,
  targetRound: string,
  requestId: string
): Response {
  return createErrorResponse({
    status: 501,
    code: "NOT_IMPLEMENTED",
    message: `Chức năng '${moduleName}' chưa được kích hoạt. Module này được lên lịch triển khai tại ${targetRound}.`,
    details: {
      module: moduleName,
      scheduled_round: targetRound
    },
    requestId
  });
}
