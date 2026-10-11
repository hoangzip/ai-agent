import React from "react";
import { Loader2 } from "lucide-react";

export const LoadingState: React.FC<{ message?: string }> = ({ message = "Đang tải dữ liệu..." }) => (
  <div className="flex flex-col items-center justify-center p-12 text-center">
    <Loader2 className="w-8 h-8 text-primary animate-spin mb-3" />
    <p className="text-sm font-medium text-slate-600">{message}</p>
  </div>
);
