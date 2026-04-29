import { Card, Form, InputNumber } from "@agentscope-ai/design";
import { useTranslation } from "react-i18next";
import styles from "../index.module.less";

const RL_PAUSE_FIELD = "llm_rate_limit_pause";
const RL_JITTER_FIELD = "llm_rate_limit_jitter";
const RL_MAX_QPM_FIELD = "llm_max_qpm";
const LLM_MAX_CONCURRENT_FIELD = "llm_max_concurrent";
const LLM_CHAT_MAX_CONCURRENT_FIELD = "llm_chat_max_concurrent";
const LLM_CRON_MAX_CONCURRENT_FIELD = "llm_cron_max_concurrent";
const LLM_ACQUIRE_TIMEOUT_FIELD = "llm_acquire_timeout";
const LLM_CHAT_ACQUIRE_TIMEOUT_FIELD = "llm_chat_acquire_timeout";
const LLM_CRON_ACQUIRE_TIMEOUT_FIELD = "llm_cron_acquire_timeout";

function optionalMinNumberRule(min: number, message: string) {
  return {
    validator: async (_: unknown, value: number | null | undefined) => {
      if (value == null) return;
      if (typeof value === "number" && value >= min) return;
      throw new Error(message);
    },
  };
}

function optionalIntegerRule(message: string) {
  return {
    validator: async (_: unknown, value: number | null | undefined) => {
      if (value == null) return;
      if (typeof value === "number" && Number.isInteger(value)) return;
      throw new Error(message);
    },
  };
}

export function LlmRateLimiterCard() {
  const { t } = useTranslation();
  const form = Form.useFormInstance();

  const acquireTimeoutGtPauseJitterRule = {
    validator: async (_: unknown, value: number | null | undefined) => {
      const pause = form.getFieldValue(RL_PAUSE_FIELD);
      const jitter = form.getFieldValue(RL_JITTER_FIELD);
      if (
        value == null ||
        typeof value !== "number" ||
        typeof pause !== "number" ||
        typeof jitter !== "number" ||
        value > pause + jitter
      ) {
        return;
      }
      throw new Error(t("agentConfig.llmAcquireTimeoutGtPauseJitter"));
    },
  };

  return (
    <Card
      className={styles.formCard}
      title={t("agentConfig.llmRateLimiterTitle")}
      style={{ marginTop: 16 }}
    >
      <Form.Item
        label={t("agentConfig.llmMaxConcurrent")}
        name={LLM_MAX_CONCURRENT_FIELD}
        rules={[
          {
            required: true,
            message: t("agentConfig.llmMaxConcurrentRequired"),
          },
          {
            type: "number",
            min: 1,
            message: t("agentConfig.llmMaxConcurrentRange"),
          },
          optionalIntegerRule(t("agentConfig.llmMaxConcurrentInteger")),
        ]}
        tooltip={t("agentConfig.llmMaxConcurrentTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={1}
          step={1}
          precision={0}
          placeholder={t("agentConfig.llmMaxConcurrentPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmChatMaxConcurrent")}
        name={LLM_CHAT_MAX_CONCURRENT_FIELD}
        rules={[
          optionalMinNumberRule(1, t("agentConfig.llmMaxConcurrentRange")),
          optionalIntegerRule(t("agentConfig.llmMaxConcurrentInteger")),
        ]}
        tooltip={t("agentConfig.llmChatMaxConcurrentTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={1}
          step={1}
          precision={0}
          placeholder={t("agentConfig.llmChatMaxConcurrentPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmCronMaxConcurrent")}
        name={LLM_CRON_MAX_CONCURRENT_FIELD}
        rules={[
          optionalMinNumberRule(1, t("agentConfig.llmMaxConcurrentRange")),
          optionalIntegerRule(t("agentConfig.llmMaxConcurrentInteger")),
        ]}
        tooltip={t("agentConfig.llmCronMaxConcurrentTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={1}
          step={1}
          precision={0}
          placeholder={t("agentConfig.llmCronMaxConcurrentPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmMaxQpm")}
        name={RL_MAX_QPM_FIELD}
        rules={[
          {
            required: true,
            message: t("agentConfig.llmMaxQpmRequired"),
          },
          {
            type: "number",
            min: 0,
            message: t("agentConfig.llmMaxQpmRange"),
          },
        ]}
        tooltip={t("agentConfig.llmMaxQpmTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          min={0}
          step={10}
          placeholder={t("agentConfig.llmMaxQpmPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmRateLimitPause")}
        name="llm_rate_limit_pause"
        rules={[
          {
            required: true,
            message: t("agentConfig.llmRateLimitPauseRequired"),
          },
          {
            type: "number",
            min: 1.0,
            message: t("agentConfig.llmRateLimitPauseMin"),
          },
        ]}
        tooltip={t("agentConfig.llmRateLimitPauseTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          step={0.5}
          placeholder={t("agentConfig.llmRateLimitPausePlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmRateLimitJitter")}
        name="llm_rate_limit_jitter"
        rules={[
          {
            required: true,
            message: t("agentConfig.llmRateLimitJitterRequired"),
          },
          {
            type: "number",
            min: 0.0,
            message: t("agentConfig.llmRateLimitJitterMin"),
          },
        ]}
        tooltip={t("agentConfig.llmRateLimitJitterTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          step={0.5}
          placeholder={t("agentConfig.llmRateLimitJitterPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmAcquireTimeout")}
        name={LLM_ACQUIRE_TIMEOUT_FIELD}
        dependencies={[RL_PAUSE_FIELD, RL_JITTER_FIELD]}
        rules={[
          {
            required: true,
            message: t("agentConfig.llmAcquireTimeoutRequired"),
          },
          {
            type: "number",
            min: 10.0,
            message: t("agentConfig.llmAcquireTimeoutMin"),
          },
          acquireTimeoutGtPauseJitterRule,
        ]}
        tooltip={t("agentConfig.llmAcquireTimeoutTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          step={10}
          placeholder={t("agentConfig.llmAcquireTimeoutPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmChatAcquireTimeout")}
        name={LLM_CHAT_ACQUIRE_TIMEOUT_FIELD}
        dependencies={[RL_PAUSE_FIELD, RL_JITTER_FIELD]}
        rules={[
          optionalMinNumberRule(10.0, t("agentConfig.llmAcquireTimeoutMin")),
          acquireTimeoutGtPauseJitterRule,
        ]}
        tooltip={t("agentConfig.llmChatAcquireTimeoutTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          step={10}
          placeholder={t("agentConfig.llmChatAcquireTimeoutPlaceholder")}
        />
      </Form.Item>

      <Form.Item
        label={t("agentConfig.llmCronAcquireTimeout")}
        name={LLM_CRON_ACQUIRE_TIMEOUT_FIELD}
        dependencies={[RL_PAUSE_FIELD, RL_JITTER_FIELD]}
        rules={[
          optionalMinNumberRule(10.0, t("agentConfig.llmAcquireTimeoutMin")),
          acquireTimeoutGtPauseJitterRule,
        ]}
        tooltip={t("agentConfig.llmCronAcquireTimeoutTooltip")}
      >
        <InputNumber
          style={{ width: "100%" }}
          step={10}
          placeholder={t("agentConfig.llmCronAcquireTimeoutPlaceholder")}
        />
      </Form.Item>
    </Card>
  );
}
