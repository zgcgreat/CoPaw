import { createGlobalStyle } from 'antd-style';

export default createGlobalStyle`
  .${(p) => p.theme.prefixCls}-processing-status-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 16px;
    background: ${(p) => p.theme.colorBgContainer};
    border-top: 1px solid ${(p) => p.theme.colorBorderSecondary};
    font-size: 13px;
    color: ${(p) => p.theme.colorTextSecondary};
  }

  .${(p) => p.theme.prefixCls}-processing-status-bar-status {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .${(p) => p.theme.prefixCls}-processing-status-bar-divider {
    width: 1px;
    height: 12px;
    background: ${(p) => p.theme.colorBorderSecondary};
  }

  .${(p) => p.theme.prefixCls}-processing-status-bar-tool-progress {
    .failed {
      color: ${(p) => p.theme.colorError};
    }
  }
`;
