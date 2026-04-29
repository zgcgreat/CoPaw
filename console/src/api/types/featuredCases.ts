/**
 * Featured Cases API types (simplified - no case_id)
 */

export interface CaseStep {
  title: string;
  content: string;
}

export interface CaseDetail {
  iframe_url: string;
  iframe_title: string;
  steps: CaseStep[];
}

export interface FeaturedCase {
  id: number;
  source_id: string;
  bbk_id?: string | null;
  label: string;
  value: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order: number;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface FeaturedCaseCreate {
  bbk_id?: string | null;
  label: string;
  value: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
}

export interface FeaturedCaseUpdate {
  bbk_id?: string | null;
  label?: string;
  value?: string;
  image_url?: string;
  iframe_url?: string;
  iframe_title?: string;
  steps?: CaseStep[];
  sort_order?: number;
  is_active?: boolean;
}

export interface FeaturedCaseListResponse {
  cases: FeaturedCase[];
  total: number;
}

// Display format (from /featured-cases endpoint)
export interface FeaturedCaseDisplay {
  id: number;
  label: string;
  value: string;
  image_url?: string;
  sort_order: number;
  detail?: CaseDetail;
}