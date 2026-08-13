/** Shared UI and API types for the ecommerce content workspace. */
export type Mode='copy'|'image'|'all'; export type Status='idle'|'queued'|'running'|'succeeded'|'failed'|'timeout';
export interface FormData {title:string;category:string;platform:string;tone:string;price_positioning:string;target_audience:string;attributes:Record<string,string>;selling_points:string[];constraints:string[];custom_image_prompt:string;custom_video_prompt:string}
export interface Media {media_url?:string|null;local_path?:string;image_prompt?:string;video_prompt?:string;prompt?:string;status?:string}
export interface Result {optimized_title:string;selling_points:string[];description:string;social_copy:string;seo_keywords:string[];quality_score?:Record<string,{score?:number;reason?:string}|number|boolean>;rewrite_reason?:string;rewrite_history?:unknown[];platform:string;image?:Media;video?:Media}
export interface ProviderSettings {backend:string;model:string;api_url:string;query_url?:string;api_key_configured:boolean;api_key?:string;managed_by_env?:boolean}
export interface ModelSettings {text:ProviderSettings;image:ProviderSettings;video:ProviderSettings}
