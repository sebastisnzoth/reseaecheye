export type Lang = 'es' | 'pt' | 'en';
export type EvidenceLevel = 'verified_exact' | 'verified_visual' | 'unverified' | string;

export interface ProviderRun {
  id: string;
  provider: string;
  status: string;
  message: string;
  result_count: number;
  checked_at: string;
  duration_ms: number;
}

export interface Match {
  id: string;
  provider: string;
  source_url: string | null;
  page_url: string | null;
  image_url: string | null;
  thumbnail_url: string | null;
  thumbnail_url_signed?: string;
  domain: string | null;
  title: string | null;
  published_at: string | null;
  published_at_note: string | null;
  match_type: string;
  evidence_level: EvidenceLevel;
  similarity: number | null;
  phash_distance: number | null;
  sha256_match: boolean;
  metric_explanation: string | null;
  license: string | null;
  notes: string | null;
}

export interface ExifFact {
  field: string;
  value: string;
  status: 'fact' | 'inference' | 'unknown' | string;
  note?: string;
}

export interface Metadata {
  available: boolean;
  facts: ExifFact[];
  inferences: ExifFact[];
  unknowns: string[];
  gps_present: boolean;
  gps: Record<string, unknown> | null;
  gps_authorized: boolean;
  exiftool_available: boolean;
  exiftool: Record<string, unknown>;
  disclaimer: string;
}

export interface Forensics {
  status: string;
  score: number;
  ela: { anomalous_block_pct: number; mean_error: number; max_error: number; score: number; method: string };
  compression: { format: string; bits_per_pixel: number; quantization_table_hash: string | null; signals: string[] };
  noise_inconsistency_pct: number;
  signals: { id: string; label: string; value: string; status: string }[];
  disclaimer: string;
  not_conclusive: boolean;
}

export interface Ocr {
  status: string;
  engine: string | null;
  lines: { text: string; confidence: number; box: number[][] }[];
  text?: string;
  terms: string[];
  message: string;
  disclaimer: string;
}

export interface Scene {
  brightness_mean: number;
  brightness_std: number;
  clipped_highlights_pct: number;
  clipped_shadows_pct: number;
  specular_candidate_regions: number;
  edge_density_pct: number;
  dominant_colors: { rgb: number[]; share_pct: number }[];
  notes: string[];
}

export interface Comparison {
  sha256: { a: string; b: string; equal: boolean };
  phash: { a: string; b: string; distance: number | null; similarity_pct: number | null; bits: number; metric: string };
  dimensions: { a: number[]; b: number[]; size_change: { from: number[]; to: number[]; area_ratio: number } | null };
  pixels: { changed_pct: number; mean_absolute_error: number; changed_regions: { x: number; y: number; width: number; height: number; area_px: number }[]; method: string };
  crop_detection: { status: string; method?: string; confidence?: number; offset?: number[]; scale?: number; note: string };
  scale_estimate: number | null;
  compression: { a: string | null; b: string | null; quantization_equal: boolean | null; note: string };
  classification: string;
  disclaimer: string;
  diff_url?: string;
}

export interface Report {
  generated_at: string;
  first_known_appearance: { status: string; date?: string; source_url?: string; provider?: string; note?: string; reason?: string };
  verified_matches: Match[];
  visual_similarities: Match[];
  unverified_results: Match[];
  duplicates: { source_url: string | null; provider: string; evidence_level: string; similarity_pct: number | null }[];
  limitations: string[];
  conclusions: string[];
  sources_consulted: { provider: string; status: string; message: string }[];
  evidence_legend: Record<string, string>;
}

export interface Investigation {
  id: string;
  created_at: string;
  updated_at: string;
  status: 'queued' | 'processing' | 'done' | 'failed' | string;
  stage: string;
  progress: number;
  error: string | null;
  lang: string;
  source_kind: string;
  source_url: string | null;
  original_filename: string | null;
  mime: string | null;
  size_bytes: number;
  sha256: string;
  phash: string | null;
  width: number;
  height: number;
  keywords: string;
  allow_gps: boolean;
  allow_external: boolean;
  retention_hours: number;
  expires_at: string | null;
  metadata: Metadata;
  forensics: Forensics;
  ocr: Ocr;
  scene: Scene;
  comparison: Comparison | null;
  manual_links: { label: string; url: string; note: string; key?: string; note_key?: string }[];
  report: Report | null;
  matches: Match[];
  provider_runs: ProviderRun[];
  display_url?: string;
  diff_url?: string;
  report_urls?: { json: string; pdf: string };
}

export interface HistoryItem {
  id: string;
  created_at: string;
  status: string;
  stage: string;
  progress: number;
  sha256: string;
  width: number;
  height: number;
  original_filename: string | null;
  source_url: string | null;
  lang: string;
  expires_at: string | null;
  error: string | null;
  verified_matches: number;
  total_matches: number;
  thumbnail_url: string;
}

export interface AppConfig {
  name: string;
  version: string;
  languages: string[];
  accepted_formats: string[];
  max_upload_mb: number;
  retention_hours: number;
  external_providers_enabled: boolean;
  providers: { name: string; label: string; kind: string }[];
  ocr: { tesseract: boolean; rapidocr: boolean };
  exiftool: boolean;
  honesty_notice: string;
}
