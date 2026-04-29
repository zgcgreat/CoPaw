import React from "react";
import Style from "./style";

export interface DragUploadOverlayProps {
  visible: boolean;
  onClose: () => void;
}

function UploadIcon() {
  return (
    <svg width="43" height="35" viewBox="0 0 43 35" fill="none">
      <path
        d="M21.5 0L39.3 17.5H28.6V35H14.4V17.5H3.7L21.5 0Z"
        fill="#3769FC"
        fillOpacity="0.15"
      />
      <path
        d="M21.5 2L37.1 17.5H27.5V33H15.5V17.5H5.9L21.5 2Z"
        fill="#3769FC"
        fillOpacity="0.3"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path
        d="M2 2L16 16M16 2L2 16"
        stroke="#808191"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function DragUploadOverlay({
  visible,
  onClose,
}: DragUploadOverlayProps) {
  if (!visible) return null;

  return (
    <>
      <Style />
      <div className="drag-upload-overlay">
        <div className="drag-upload-card">
          <button className="drag-upload-close" onClick={onClose} type="button">
            <CloseIcon />
          </button>
          <div className="drag-upload-icon">
            <UploadIcon />
          </div>
          <div className="drag-upload-title">点击或拖放文件到该区域</div>
          <div className="drag-upload-desc">
            支持txt, md, png，jpg等格式
          </div>
        </div>
      </div>
    </>
  );
}
