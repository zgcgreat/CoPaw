import { getApiUrl, clearAuthToken } from "./config";
import { buildAuthHeaders } from "./authHeaders";
import {
  isExternalTokenEnabled,
  ensureValidToken,
  clearExternalToken,
} from "./externalToken";

function getErrorMessageFromBody(
  text: string,
  contentType: string,
): string | null {
  if (!text) {
    return null;
  }

  if (!contentType.includes("application/json")) {
    return text;
  }

  try {
    const payload = JSON.parse(text) as {
      detail?: unknown;
      message?: unknown;
      error?: unknown;
    };

    if (typeof payload.detail === "string" && payload.detail) {
      return payload.detail;
    }
    if (typeof payload.message === "string" && payload.message) {
      return payload.message;
    }
    if (typeof payload.error === "string" && payload.error) {
      return payload.error;
    }
  } catch {
    return text;
  }

  return text;
}

function buildHeaders(method?: string, extra?: HeadersInit): Headers {
  // Normalize extra to a Headers instance for consistent handling
  const headers = extra instanceof Headers ? extra : new Headers(extra);

  // Only add Content-Type for methods that typically have a body
  if (method && ["POST", "PUT", "PATCH"].includes(method.toUpperCase())) {
    // Don't override if caller explicitly set Content-Type
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  for (const [key, value] of Object.entries(buildAuthHeaders())) {
    if (!headers.has(key)) {
      headers.set(key, value);
    }
  }

  return headers;
}

export async function request<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = getApiUrl(path);
  const method = options.method || "GET";
  const headers = buildHeaders(method, options.headers);

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    // Handle 401: try refresh external token and retry, or redirect to login
    if (response.status === 401) {
      // If external token is enabled, try to refresh and retry
      if (isExternalTokenEnabled()) {
        try {
          const newToken = await ensureValidToken(true); // Force refresh
          // Retry with new token
          const newHeaders = buildHeaders(method, options.headers);
          newHeaders.set("Authorization", `Bearer ${newToken}`);

          const retryResponse = await fetch(url, {
            ...options,
            headers: newHeaders,
          });

          if (retryResponse.ok) {
            // Handle successful retry response
            if (retryResponse.status === 204) {
              return undefined as T;
            }
            const retryContentType =
              retryResponse.headers.get("content-type") || "";
            if (!retryContentType.includes("application/json")) {
              return (await retryResponse.text()) as unknown as T;
            }
            return (await retryResponse.json()) as T;
          }

          // Retry also failed with 401, clear external token
          if (retryResponse.status === 401) {
            clearExternalToken();
          }
        } catch {
          // Refresh failed, clear external token
          clearExternalToken();
        }
      }

      // Fallback to original logic: clear auth token and redirect to login
      clearAuthToken();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
      throw new Error("Not authenticated");
    }

    // Handle other errors
    const text = await response.text().catch(() => "");
    const contentType = response.headers.get("content-type") || "";
    const errorMessage = getErrorMessageFromBody(text, contentType);

    // Preserve raw body for parseErrorDetail() to extract structured fields
    const finalMessage = errorMessage
      ? `${errorMessage} - ${text}`
      : `Request failed: ${response.status} ${response.statusText}`;

    throw new Error(finalMessage);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return (await response.text()) as unknown as T;
  }

  return (await response.json()) as T;
}
