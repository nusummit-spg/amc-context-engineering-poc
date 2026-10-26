// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// ===========================================================================

/**
 * Feature Flags Configuration.
 * Allows instant rollback and staged activation across environments.
 */
export const FEATURES = {
  /**
   * Phase 2: Feedback Issues & Triage sidebar navigation.
   * When true:
   * - Admin & Governance in the sidebar becomes an expandable group with Overview and Feedback Issues & Triage.
   * - Feedback Issues & Triage renders at its own route (activePage: "admin_feedback_issues").
   * - AdminView keeps 4 tabs (tab 5 Feedback Issues & Triage is removed from AdminView).
   * When false:
   * - AdminView retains all 5 tabs and Admin & Governance is a single workspace tab.
   */
  FEEDBACK_SIDEBAR_NAV_ENABLED:
    import.meta.env.VITE_FEEDBACK_SIDEBAR_NAV_ENABLED !== undefined
      ? String(import.meta.env.VITE_FEEDBACK_SIDEBAR_NAV_ENABLED).toLowerCase() === "true"
      : true,

  /**
   * Phase 3: "My Feedback" personal view.
   * When true:
   * - "My Feedback" is rendered in Sidebar Workspace navigation for all authenticated users.
   * - Accessible via activePage === "my_feedback".
   * - Backed by GET /api/feedback/mine.
   */
  MY_FEEDBACK_PAGE_ENABLED:
    import.meta.env.VITE_MY_FEEDBACK_PAGE_ENABLED !== undefined
      ? String(import.meta.env.VITE_MY_FEEDBACK_PAGE_ENABLED).toLowerCase() === "true"
      : true,

  /**
   * Phase 4: Category-aware status banner in Feedback Modal / Container.
   * When true:
   * - Status banner renders category_breakdown pills (code, label, count multiplier).
   * - Caps at top-5 with +N more toggle for remaining categories.
   */
  FEEDBACK_CATEGORY_BREAKDOWN_BANNER_ENABLED:
    import.meta.env.VITE_FEEDBACK_CATEGORY_BREAKDOWN_BANNER_ENABLED !== undefined
      ? String(import.meta.env.VITE_FEEDBACK_CATEGORY_BREAKDOWN_BANNER_ENABLED).toLowerCase() === "true"
      : true,
};


