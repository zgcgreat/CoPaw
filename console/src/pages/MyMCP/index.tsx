import { Card, Empty, Typography } from "antd";

const { Title } = Typography;

export default function MyMCPPage() {
  return (
    <Card>
      <Title level={4}>我的 MCP</Title>
      <Empty description="功能开发中，敬请期待" />
    </Card>
  );
}
