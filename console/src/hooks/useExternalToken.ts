// React hook for external token management
// Handles initial token fetch and periodic refresh

import { useEffect, useRef, useState } from "react";
import {
  isExternalTokenEnabled,
  ensureValidToken,
  getTokenConfig,
} from "../api/externalToken";

/**
 * Hook to manage external system token
 * - Initializes token on mount (if configured)
 * - Periodically checks and refreshes token (every 60 seconds)
 *
 * Returns:
 * - isInitialized: true when initial token fetch is complete (or if external token is disabled)
 */
export function useExternalToken(): { isInitialized: boolean } {
  const [isInitialized, setIsInitialized] = useState(false);
  const initializedRef = useRef(false);

  useEffect(() => {
    // If external token is not configured, mark as initialized immediately
    if (!isExternalTokenEnabled()) {
      setIsInitialized(true);
      return;
    }

    // Prevent double initialization in React StrictMode
    if (initializedRef.current) {
      return;
    }
    initializedRef.current = true;

    // Initialize token on mount
    const initToken = async (): Promise<void> => {
      try {
        await ensureValidToken();
      } catch (error) {
        console.warn("Failed to initialize external token:", error);
      } finally {
        // Always mark as initialized, even if failed
        // Failed requests will be handled by 401 retry logic
        setIsInitialized(true);
      }
    };

    initToken();

    // Periodic check and refresh (every 60 seconds)
    const intervalId = setInterval(() => {
      ensureValidToken().catch((error) => {
        console.warn("Failed to refresh external token:", error);
      });
    }, 60 * 1000);

    // Cleanup on unmount
    return () => {
      clearInterval(intervalId);
      initializedRef.current = false;
    };
  }, []);

  return { isInitialized };
}

/**
 * Hook to check if external token is enabled
 * Useful for conditional rendering or logic
 */
export function useIsExternalTokenEnabled(): boolean {
  const config = getTokenConfig();
  return !!config.systemCode && !!config.systemSecret && !!config.tokenApiUrl;
}