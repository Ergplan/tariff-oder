/**
 * Shared API contract for the web app.  `api.d.ts` is generated from `openapi.json`, which
 * itself is exported from the FastAPI service (`tariff-api openapi`).  CI fails when either
 * file drifts from the running service (`scripts/check-drift.mjs`).
 */
import type { components, paths } from "./api";

export type { components, paths };

export type Schemas = components["schemas"];

export type SourceSummary = Schemas["SourceSummary"];
export type SourceDetail = Schemas["SourceDetail"];
export type SourceList = Schemas["SourceList"];
export type SourcePageList = Schemas["SourcePageList"];
export type SourcePageOut = Schemas["SourcePageOut"];
export type SourceRegistration = Schemas["SourceRegistration"];
export type JobSummary = Schemas["JobSummary"];
export type JobDetail = Schemas["JobDetail"];
export type JobList = Schemas["JobList"];
export type StatusReport = Schemas["StatusReport"];
export type Readiness = Schemas["Readiness"];
export type ErrorResponse = Schemas["ErrorResponse"];
export type Me = Schemas["Me"];
export type RegistryOut = Schemas["RegistryOut"];
export type SourceState = Schemas["SourceState"];
export type JobStatus = Schemas["JobStatus"];
export type DatasetKind = Schemas["DatasetKind"];
export type UserRole = Schemas["UserRole"];
export type LocalisationOut = Schemas["LocalisationOut"];
export type LocalisationRegionOut = Schemas["LocalisationRegionOut"];
export type RegionAnnotation = Schemas["RegionAnnotation"];
export type LocalisationDecision = Schemas["LocalisationDecision"];
export type ReadingProfileOut = Schemas["ReadingProfileOut"];
export type ReadingProfileList = Schemas["ReadingProfileList"];
export type StructureSummary = Schemas["StructureSummary"];
export type StructureCellList = Schemas["StructureCellList"];
export type StructureCellOut = Schemas["StructureCellOut"];
export type ClauseValueList = Schemas["ClauseValueList"];
export type ClauseValueOut = Schemas["ClauseValueOut"];
export type CandidateOut = Schemas["CandidateOut"];
export type CandidateList = Schemas["CandidateList"];
export type FindingList = Schemas["FindingList"];
export type CategorySummaryList = Schemas["CategorySummaryList"];
export type CategorySummaryOut = Schemas["CategorySummaryOut"];
export type TableRows = Schemas["TableRows"];
export type ReviewQueue = Schemas["ReviewQueue"];
export type ExtractionSummary = Schemas["ExtractionSummary"];
export type ValidationSummary = Schemas["ValidationSummary"];
export type ExtractionRunList = Schemas["ExtractionRunList"];
export type ConditionList = Schemas["ConditionList"];
export type ReviewQueueDetail = Schemas["ReviewQueueDetail"];
export type ReviewQueueCandidate = Schemas["ReviewQueueCandidate"];
export type ReviewChecklist = Schemas["ReviewChecklist"];
export type ChecklistItem = Schemas["ChecklistItem"];
export type ReviewDecisionRequest = Schemas["ReviewDecisionRequest"];
export type ReviewDecisionOut = Schemas["ReviewDecisionOut"];
export type DecisionResult = Schemas["DecisionResult"];
export type DecisionList = Schemas["DecisionList"];
export type CandidateEvidenceOut = Schemas["CandidateEvidenceOut"];
export type BatchApproveResult = Schemas["BatchApproveResult"];
export type ReviewTelemetry = Schemas["ReviewTelemetry"];
export type PublishPreview = Schemas["PublishPreview"];
export type PublishRequest = Schemas["PublishRequest"];
export type PublishGap = Schemas["PublishGap"];
export type ReleaseOut = Schemas["ReleaseOut"];
export type ReleaseList = Schemas["ReleaseList"];
export type PublicationSummary = Schemas["PublicationSummary"];
export type TariffExplorer = Schemas["TariffExplorer"];
export type ExplorerCategory = Schemas["ExplorerCategory"];
export type NetworkExplorer = Schemas["NetworkExplorer"];
export type NetworkFamilyView = Schemas["NetworkFamilyView"];
export type PublishedFactOut = Schemas["PublishedFactOut"];
export type CitationOut = Schemas["CitationOut"];
export type CompletenessBanner = Schemas["CompletenessBanner"];
export type ExplorerReleaseList = Schemas["ExplorerReleaseList"];

/** Pipeline states of Section 6.2, in order; terminal/exception states listed separately. */
export const PIPELINE_STATES: SourceState[] = [
  "uploaded",
  "inventoried",
  "triaged",
  "parsed",
  "localised",
  "gridded",
  "extracted",
  "validated",
  "awaiting_review",
  "published",
];
export const EXCEPTION_STATES: SourceState[] = ["failed", "cancelled", "rejected", "superseded", "needs_reprocessing"];
