import type { ColumnType } from "antd/es/table";
import type { FeaturedCase } from "@/api/types/featuredCases";
import { BBK_ID_MAP } from "@/constants/bbk";

interface CreateCaseColumnsOptions {
  onEdit: (caseItem: FeaturedCase) => void;
  onDelete: (id: number) => void;
}

export function createCaseColumns({
  onEdit,
  onDelete,
}: CreateCaseColumnsOptions): ColumnType<FeaturedCase>[] {
  return [
    // {
    //   title: "ID",
    //   dataIndex: "id",
    //   key: "id",
    //   width: 80,
    // },
    {
      title: "机构",
      dataIndex: "bbk_id",
      key: "bbk_id",
      width: 120,
      render: (bbkId: string | null) => {
        const org = BBK_ID_MAP.find((item) => item.value === bbkId);
        return org ? org.label : bbkId || <span style={{ color: "#999"}}>-</span>;
      },
    },
    {
      title: "标题",
      dataIndex: "label",
      key: "label",
      ellipsis: true,
    },
    {
      title: "排序",
      dataIndex: "sort_order",
      key: "sort_order",
      width: 80,
    },
    {
      title: "状态",
      dataIndex: "is_active",
      key: "is_active",
      width: 80,
      render: (active: boolean) =>
        active ? (
          <span style={{ color: "#52c41a" }}>启用</span>
        ) : (
          <span style={{ color: "#999" }}>禁用</span>
        ),
    },
    {
      title: "操作",
      key: "action",
      width: 120,
      render: (_, record) => (
        <span>
          <a onClick={() => onEdit(record)} style={{ marginRight: 12 }}>
            编辑
          </a>
          <a
            onClick={() => onDelete(record.id)}
            style={{ color: "#ff4d4f" }}
          >
            删除
          </a>
        </span>
      ),
    },
  ];
}