import React, { useState, useEffect } from "react";
import Style from "./style";
import { featuredCasesApi } from "@/api/modules/featuredCases";
import caseIcon from '../../../assets/icons/default_case.svg'

export interface FeaturedCase {
  id: number;
  label: string;
  value: string;
  image?: string;
}

export interface FeaturedCasesProps {
  cases?: FeaturedCase[];
  onFillInput?: (text: string) => void;
  onViewCase?: (id: number) => void;
}

const DEFAULT_CASES: FeaturedCase[] = [
  {
    id: 1,
    label: "默认案例",
    value: "default",
    image: caseIcon,
  },
];

function MoreIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <path
        d="M4 6.667L8 11L12 6.667"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function KYCIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12.37" height="10.11" rx="1" fill="white" />
      <circle cx="5.07" cy="7.07" r="1.53" fill="white" />
      <rect x="7.9" y="9.17" width="4.2" height="2.5" rx="0.5" fill="white" />
      <rect
        x="7.07"
        y="4.63"
        width="3.31"
        height="1.04"
        rx="0.5"
        fill="white"
      />
      <rect x="9.6" y="6.21" width="2.74" height="1.04" rx="0.5" fill="white" />
    </svg>
  );
}

export default function FeaturedCases(props: FeaturedCasesProps) {
  const { onFillInput, onViewCase } = props;
  const [cases, setCases] = useState<FeaturedCase[]>([]);
  const [loading, setLoading] = useState(true);

  // Load cases from API on mount
  useEffect(() => {
    const loadCases = async () => {
      try {
        const apiCases = await featuredCasesApi.listCases();
        if(apiCases && apiCases.length > 0){
          const featuredCases: FeaturedCase[] = apiCases.map((c) => ({
            id: c.id,
            label: c.label,
            value: c.value,
            image: c.image_url,
          }));
          setCases(featuredCases);
        }else{
          setCases(DEFAULT_CASES);
        }
      } catch (error) {
        console.error("Failed to load cases:", error);
        // Keep empty array on error
        setCases([]);
      } finally {
        setLoading(false);
      }
    };

    loadCases();
  }, []);

  const handleCardClick = (caseItem: FeaturedCase) => {
    onFillInput?.(caseItem.value);
  };

  const handleViewCase = (e: React.MouseEvent, caseItem: FeaturedCase) => {
    e.stopPropagation();
    onViewCase?.(caseItem.id);
  };

  const handleUseSame = (e: React.MouseEvent, caseItem: FeaturedCase) => {
    e.stopPropagation();
    onFillInput?.(caseItem.value);
  };

  if (loading) {
    return (
      <>
        <Style />
        <div className="featured-cases">
          <div className="featured-cases-header">
            <div className="featured-cases-title">
              <span className="featured-cases-title-icon">
                <img src={caseIcon} alt="" />
              </span>
              精选案例
            </div>
          </div>
          <div className="featured-cases-scroll">
            <div className="featured-cases-loading">加载中...</div>
          </div>
        </div>
      </>
    );
  }

  if (cases.length === 0) {
    return null;
  }

  return (
    <>
      <Style />
      <div className="featured-cases">
        <div className="featured-cases-header">
          <div className="featured-cases-title">
            <span className="featured-cases-title-icon">
              <img src={caseIcon} alt="" />
            </span>
            精选案例
          </div>
          {cases.length > 5 && (
            <div className="featured-cases-more">
              查看更多
              <MoreIcon />
            </div>
          )}
        </div>
        <div className="featured-cases-scroll">
          {cases.map((caseItem) => (
            <div
              key={caseItem.id}
              className="featured-cases-card"
              onClick={() => handleCardClick(caseItem)}
              role="button"
              tabIndex={0}
            >
              {caseItem.image && (
                <img
                  className="featured-cases-card-image"
                  src={caseItem.image}
                  alt=""
                />
              )}
              <div className="featured-cases-card-text">{caseItem.label}</div>
              <div className="featured-cases-overlay">
                <button
                  className="featured-cases-overlay-btn"
                  onClick={(e) => handleViewCase(e, caseItem)}
                  type="button"
                >
                  <span className="featured-cases-overlay-btn-icon">
                    <KYCIcon />
                  </span>
                  看案例
                </button>
                <button
                  className="featured-cases-overlay-btn"
                  onClick={(e) => handleUseSame(e, caseItem)}
                  type="button"
                >
                  <span className="featured-cases-overlay-btn-icon">
                    <KYCIcon />
                  </span>
                  做同款
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}