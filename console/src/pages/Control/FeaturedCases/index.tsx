import { useState, useEffect } from "react";
import { Button, Card, Table, Modal, Input, Select } from "antd";
import { Form } from "@agentscope-ai/design";
import { PageHeader } from "@/components/PageHeader";
import { useFeaturedCases } from "./components/hooks";
import { createCaseColumns } from "./components/columns";
import { CaseDrawer } from "./components/CaseDrawer";
import type { FeaturedCase } from "@/api/types/featuredCases";
import styles from "./index.module.less";

function FeaturedCasesPage() {
  const { cases, loading, total, loadCases, createCase, updateCase, deleteCase } =
    useFeaturedCases();

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingCase, setEditingCase] = useState<FeaturedCase | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FeaturedCase>();

  // Pagination
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
  });

  // Filter
  const [bbkIdFilter, setBbkIdFilter] = useState<string | undefined>(undefined);

  // Load data on mount
  useEffect(() => {
    loadCases({
      bbk_id: bbkIdFilter,
      page: pagination.current,
      page_size: pagination.pageSize,
    });
  }, [loadCases, pagination.current, pagination.pageSize, bbkIdFilter]);

  // ==================== Handlers ====================

  const handleCreate = () => {
    setEditingCase(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (caseItem: FeaturedCase) => {
    setEditingCase(caseItem);
    form.setFieldsValue(caseItem);
    setDrawerOpen(true);
  };

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: "确认删除",
      content: `确定要删除该案例吗？`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: async () => {
        await deleteCase(id);
        loadCases({
          bbk_id: bbkIdFilter,
          page: pagination.current,
          page_size: pagination.pageSize,
        });
      },
    });
  };

  const handleClose = () => {
    setDrawerOpen(false);
    setEditingCase(null);
  };

  const handleSubmit = async (values: FeaturedCase) => {
    setSaving(true);
    try {
      if (editingCase) {
        await updateCase(editingCase.id, values);
      } else {
        await createCase(values);
      }
      setDrawerOpen(false);
      loadCases({
        bbk_id: bbkIdFilter,
        page: pagination.current,
        page_size: pagination.pageSize,
      });
    } catch (error) {
      // Error handled in hooks
    } finally {
      setSaving(false);
    }
  };

  const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
    setPagination({
      current: pag.current || 1,
      pageSize: pag.pageSize || 20,
    });
  };

  // ==================== Columns ====================

  const columns = createCaseColumns({
    onEdit: handleEdit,
    onDelete: handleDelete,
  });

  return (
    <div className={styles.featuredCasesPage}>
      <PageHeader
        items={[{ title: "控制" }, { title: "精选案例管理" }]}
        extra={
          <Button type="primary" onClick={handleCreate}>
            + 新建案例
          </Button>
        }
      />

      <Card className={styles.tableCard}>
        <Table
          columns={columns}
          dataSource={cases}
          loading={loading}
          rowKey="id"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={handleTableChange}
        />
      </Card>

      <CaseDrawer
        open={drawerOpen}
        editingCase={editingCase}
        form={form}
        saving={saving}
        onClose={handleClose}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

export default FeaturedCasesPage;