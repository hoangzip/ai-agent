/**
 * Vinamilk Inventory Management - Google Apps Script Time-Driven Trigger
 * Script: Code.gs (Round 07 Fix 01 - P1-01 Automated Scheduler)
 *
 * Tính năng:
 * 1. Tự động chạy định kỳ mỗi 60 phút qua Google Apps Script Time-driven trigger (miễn phí 100% trong quota).
 * 2. Quét các tệp Excel kiểm kê trong Google Drive Folder 1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk.
 * 3. Kích hoạt Webhook API tới hệ thống Vinamilk Inventory Backend qua POST /api/v1/sync/scheduled.
 */

var CONFIG = {
  FOLDER_ID: "1HOsA7gWKghPVUcq2JgUhS9xgiccjp4bk",
  API_BASE_URL: "https://inventory-management-api.your-account.workers.dev",
  SYNC_INTERVAL_HOURS: 1
};

/**
 * Hàm lấy Webhook Secret bảo mật từ Google Apps Script Script Properties
 * Tuyệt đối không hardcode secret trong mã nguồn.
 */
function getWebhookSecret() {
  var secret = PropertiesService.getScriptProperties().getProperty("SYNC_WEBHOOK_SECRET");
  if (!secret) {
    throw new Error("Chưa cấu hình SYNC_WEBHOOK_SECRET trong Script Properties của Google Apps Script.");
  }
  return secret;
}

/**
 * Hàm thực thi đồng bộ định kỳ chính
 */
function runScheduledSync() {
  Logger.log("[GAS_SYNC] Bắt đầu chu kỳ quét thư mục Google Drive: " + CONFIG.FOLDER_ID);
  
  try {
    var webhookSecret = getWebhookSecret();
    var folder = DriveApp.getFolderById(CONFIG.FOLDER_ID);
    var files = folder.getFiles();
    var fileCount = 0;
    
    while (files.hasNext()) {
      var file = files.next();
      fileCount++;
      Logger.log("  - Tìm thấy tệp: " + file.getName() + " (" + file.getSize() + " bytes)");
    }
    
    Logger.log("[GAS_SYNC] Phát hiện tổng cộng " + fileCount + " tệp trong thư mục.");
    
    // Gọi API Webhook kích hoạt đồng bộ
    var url = CONFIG.API_BASE_URL + "/api/v1/sync/scheduled";
    var options = {
      method: "post",
      contentType: "application/json",
      headers: {
        "X-Webhook-Secret": webhookSecret
      },
      payload: JSON.stringify({
        source: "GOOGLE_APPS_SCRIPT_TIME_TRIGGER",
        folderId: CONFIG.FOLDER_ID,
        fileCount: fileCount,
        timestamp: new Date().toISOString()
      }),
      muteHttpExceptions: true
    };
    
    var response = UrlFetchApp.fetch(url, options);
    var responseCode = response.getResponseCode();
    var responseBody = response.getContentText();
    
    Logger.log("[GAS_SYNC] Phản hồi API (" + responseCode + "): " + responseBody);
  } catch (err) {
    Logger.log("[GAS_SYNC_ERROR] Lỗi thực thi: " + err.toString());
  }
}

/**
 * Thiết lập Time-driven Trigger chạy mỗi 1 giờ
 */
function setupHourlyTrigger() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "runScheduledSync") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }
  
  ScriptApp.newTrigger("runScheduledSync")
    .timeBased()
    .everyHours(CONFIG.SYNC_INTERVAL_HOURS)
    .create();
    
  Logger.log("[GAS_TRIGGER] Đã thiết lập Trigger tự động chạy mỗi " + CONFIG.SYNC_INTERVAL_HOURS + " giờ.");
}
