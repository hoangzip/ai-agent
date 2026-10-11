import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = "Đã xảy ra lỗi",
  message,
  onRetry
}) => (
  <div className="flex flex-col items-center justify-center p-12 text-center bg-rose-50/50 border border-rose-100 rounded-xl my-4">
    <div className="w-10 h-10 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mb-3">
      <AlertCircle className="w-5 h-5" />
    </div>
    <h4 className="text-base font-semibold text-rose-900 mb-1">{title}</h4>
    <p className="text-sm text-rose-600 max-w-md mb-4">{message}</p>
    {onRetry && (
      <button
        onClick={onRetry}
        className="inline-flex items-center space-x-2 px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-medium hover:bg-rose-700 transition"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        <span>Thử lại</span>
      </button>
    )}
  </div>
);
