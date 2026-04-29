import { useState, useCallback } from "react";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import type { FeaturedCase, FeaturedCaseCreate, FeaturedCaseUpdate } from "@/api/types/featuredCases";

export function useFeaturedCases() {
  const [cases, setCases] = useState<FeaturedCase[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  const loadCases = useCallback(
    async (params?: { bbk_id?: string; page?: number; page_size?: number }) => {
      setLoading(true);
      try {
        const data = await featuredCasesApi.adminListCases(params);
        setCases(data.cases);
        setTotal(data.total);
      } catch (error) {
        console.error("Failed to load cases:", error);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const createCase = useCallback(async (caseItem: FeaturedCaseCreate) => {
    try {
      const result = await featuredCasesApi.adminCreateCase(caseItem);
      return result.data;
    } catch (error) {
      console.error("Failed to create case:", error);
      throw error;
    }
  }, []);

  const updateCase = useCallback(
    async (id: number, caseItem: Partial<FeaturedCaseUpdate>) => {
      try {
        const result = await featuredCasesApi.adminUpdateCase(id, caseItem);
        return result.data;
      } catch (error) {
        console.error("Failed to update case:", error);
        throw error;
      }
    },
    []
  );

  const deleteCase = useCallback(async (id: number) => {
    try {
      await featuredCasesApi.adminDeleteCase(id);
    } catch (error) {
      console.error("Failed to delete case:", error);
      throw error;
    }
  }, []);

  return {
    cases,
    loading,
    total,
    loadCases,
    createCase,
    updateCase,
    deleteCase,
  };
}