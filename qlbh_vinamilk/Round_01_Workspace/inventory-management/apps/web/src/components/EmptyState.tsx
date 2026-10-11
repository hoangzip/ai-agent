import React from "react";
import { FolderOpen } from "lucide-react";

interface EmptyStateProps {
  title?: string;
  description: string;
  actionText?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = "Không có dữ liệu",
  description,
  actionText,
  onAction
}) => (
  <div className="flex flex-col items-center justify-center p-12 text-center bg-white border border-dashed border-slate-200 rounded-xl my-4">
    <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 flex items-center justify-center mb-3">
      <FolderOpen className="w-6 h-6" />
    </div>
    <h4 className="text-sm font-semibold text-slate-800 mb-1">{title}</h4>
    <p className="text-xs text-slate-500 max-w-sm mb-4">{description}</p>
    {actionText && onAction && (
      <button
        onClick={onAction}
        className="px-3.5 py-1.5 bg-primary text-white text-xs font-medium rounded-lg hover:bg-primary-700 transition"
      >
        {actionText}
      </button>
    )}
  </div>
);
