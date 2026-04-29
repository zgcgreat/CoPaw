import {
  Drawer,
  Form,
  Input,
  Switch,
  Button,
  Select,
} from "@agentscope-ai/design";
import { MinusCircleOutlined, PlusOutlined } from "@ant-design/icons";
import { useEffect } from "react";
import type { FormInstance } from "antd";
import type { FeaturedCase, CaseStep } from "@/api/types/featuredCases";
import { useIframeStore } from "@/stores/iframeStore";
import { DEFAULT_BBK_ID } from "@/constants/identity";
import { BBK_ID_MAP } from "@/constants/bbk";

interface CaseDrawerProps {
  open: boolean;
  editingCase: FeaturedCase | null;
  form: FormInstance<FeaturedCase>;
  saving: boolean;
  onClose: () => void;
  onSubmit: (values: FeaturedCase) => void;
}

const DEFAULT_CASE: Partial<FeaturedCase> = {
  is_active: true,
  bbk_id: "",
  iframe_url: "",
  iframe_title: "",
  steps: [],
};

export function CaseDrawer({
  open,
  editingCase,
  form,
  saving,
  onClose,
  onSubmit,
}: CaseDrawerProps) {
  // 设置默认值从 iframeStore
  useEffect(() => {
    if(open && !editingCase){
      const { bbk } = useIframeStore.getState();
      console.log('store----bbk', bbk)
      form.setFieldsValue({ bbk_id: bbk || DEFAULT_BBK_ID });
    }
  }, [open, editingCase, form]);

  return (
    <Drawer
      width={600}
      placement="right"
      title={editingCase ? "编辑案例" : "新建案例"}
      open={open}
      onClose={onClose}
      destroyOnClose
      footer={
        <div style={{ display: "flex", gap: 8 }}>
          <Button onClick={onClose}>取消</Button>
          <Button type="primary" loading={saving} onClick={() => form.submit()}>
            保存
          </Button>
        </div>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={onSubmit}
        initialValues={DEFAULT_CASE}
      >
        {/* source_id NOT displayed - comes from X-Source-Id header */}

        <Form.Item name="bbk_id" label="机构">
          <Select
            disabled
            options={BBK_ID_MAP}
          />
        </Form.Item>

        <Form.Item
          name="label"
          label="标题"
          rules={[{ required: true, message: "请输入标题" }]}
        >
          <Input.TextArea
            placeholder="案例卡片显示的标题"
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
        </Form.Item>

        <Form.Item
          name="value"
          label="提问内容"
          rules={[{ required: true, message: "请输入提问内容" }]}
        >
          <Input.TextArea
            placeholder="用户点击案例后的提问内容"
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
        </Form.Item>

        <Form.Item name="image_url" label="图片 URL">
          <Input placeholder="https://..." />
        </Form.Item>

        <Form.Item name="is_active" label="启用" valuePropName="checked">
          <Switch />
        </Form.Item>

        <Form.Item name="iframe_url" label="iframe URL">
          <Input placeholder="https://..." />
        </Form.Item>

        <Form.Item name="iframe_title" label="iframe 标题">
          <Input placeholder="详情面板标题" />
        </Form.Item>

        {/* Steps */}
        <Form.Item label="步骤说明">
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...restField }) => (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      marginBottom: 12,
                      padding: 12,
                      background: "#f7f7fc",
                      borderRadius: 4,
                    }}
                  >
                    <Form.Item
                      {...restField}
                      name={[name, "title"]}
                      label="步骤标题"
                      rules={[{ required: true, message: "请输入步骤标题" }]}
                    >
                      <Input placeholder="步骤1：..." />
                    </Form.Item>
                    <Form.Item
                      {...restField}
                      name={[name, "content"]}
                      label="步骤内容"
                      rules={[{ required: true, message: "请输入步骤内容" }]}
                    >
                      <Input.TextArea
                        placeholder="步骤详细说明"
                        autoSize={{ minRows: 2, maxRows: 6 }}
                      />
                    </Form.Item>
                    <MinusCircleOutlined
                      onClick={() => remove(name)}
                      style={{ color: "#ff4d4f", cursor: "pointer" }}
                    />
                  </div>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add({ title: "", content: "" } as CaseStep)}
                  block
                  icon={<PlusOutlined />}
                >
                  添加步骤
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>
      </Form>
    </Drawer>
  );
}