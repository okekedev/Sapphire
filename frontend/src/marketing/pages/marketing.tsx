import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  MessageSquare,
  Link2,
  BarChart3,
  ChevronDown,
  Send,
  Loader2,
  Plus,
  CheckCircle2,
  Phone,
  ImagePlus,
  Trash2,
  PenLine,
  X,
  Upload,
  FileImage,
  Clock,
  XCircle,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";
import { Spinner } from "@/shared/components/ui/spinner";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";

// APIs
import { listEmployees, listDepartments } from "@/shared/api/organization";
import { sendEmployeeChat, type ChatMessage } from "@/shared/api/chat";
import { listConnections, type PlatformConnection } from "@/shared/api/platforms";
import {
  uploadMedia,
  listMedia,
  deleteMedia,
  mediaFileUrl,
  createPost,
  listPosts,
  deletePost,
  type MediaFile,
  type ContentPost,
} from "@/marketing/api/content";

// ── Brand SVG Icons ──

function FacebookIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
    </svg>
  );
}


function LinkedInIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  );
}

function YouTubeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
    </svg>
  );
}


function InstagramIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C8.74 0 8.333.015 7.053.072 5.775.132 4.905.333 4.14.63c-.789.306-1.459.717-2.126 1.384S.935 3.35.63 4.14C.333 4.905.131 5.775.072 7.053.012 8.333 0 8.74 0 12s.015 3.667.072 4.947c.06 1.277.261 2.148.558 2.913.306.788.717 1.459 1.384 2.126.667.666 1.336 1.079 2.126 1.384.766.296 1.636.499 2.913.558C8.333 23.988 8.74 24 12 24s3.667-.015 4.947-.072c1.277-.06 2.148-.262 2.913-.558.788-.306 1.459-.718 2.126-1.384.666-.667 1.079-1.335 1.384-2.126.296-.765.499-1.636.558-2.913.06-1.28.072-1.687.072-4.947s-.015-3.667-.072-4.947c-.06-1.277-.262-2.149-.558-2.913-.306-.789-.718-1.459-1.384-2.126C21.319 1.347 20.651.935 19.86.63c-.765-.297-1.636-.499-2.913-.558C15.667.012 15.26 0 12 0zm0 2.16c3.203 0 3.585.016 4.85.071 1.17.055 1.805.249 2.227.415.562.217.96.477 1.382.896.419.42.679.819.896 1.381.164.422.36 1.057.413 2.227.057 1.266.07 1.646.07 4.85s-.015 3.585-.074 4.85c-.061 1.17-.256 1.805-.421 2.227-.224.562-.479.96-.899 1.382-.419.419-.824.679-1.38.896-.42.164-1.065.36-2.235.413-1.274.057-1.649.07-4.859.07-3.211 0-3.586-.015-4.859-.074-1.171-.061-1.816-.256-2.236-.421-.569-.224-.96-.479-1.379-.899-.421-.419-.69-.824-.9-1.38-.165-.42-.359-1.065-.42-2.235-.045-1.26-.061-1.649-.061-4.844 0-3.196.016-3.586.061-4.861.061-1.17.255-1.814.42-2.234.21-.57.479-.96.9-1.381.419-.419.81-.689 1.379-.898.42-.166 1.051-.361 2.221-.421 1.275-.045 1.65-.06 4.859-.06l.045.03zm0 3.678a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 1 0 0-12.324zM12 16c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm7.846-10.405a1.441 1.441 0 1 1-2.882 0 1.441 1.441 0 0 1 2.882 0z" />
    </svg>
  );
}

function YelpIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.16 12.594l-4.995 1.433c-.96.276-1.74-.8-1.176-1.63l2.056-2.94c.072-.104.15-.2.226-.3l.6-.8c.56-.75 1.646-.53 1.907.36l.9 3.06c.16.54-.16 1.1-.518 1.02zm-8.093 4.05l1.793-4.747c.397-1.06 1.868-1.06 2.226.02l1.5 4.478c.198.56-.224 1.14-.8 1.14h-3.64c-.697 0-1.28-.473-1.08-.89zm-2.293-3.03L6.22 15.55c-.59.316-1.274-.245-1.07-.878l1.12-3.5c.135-.422.624-.62 1.016-.414l3.503 1.84c.97.51.48 1.783-.515 1.52zM10.59 8.047L8.68 12.77c-.33.82-1.52.8-1.82-.03L5.19 8.285c-.2-.55.12-1.16.63-1.2l3.59-.28c.87-.07 1.57.63 1.18 1.24zm.36-2.53l.51-3.52c.1-.68.8-1.07 1.36-.74l3.57 2.1c.55.32.43 1.15-.2 1.33l-3.9 1.07c-.92.25-1.48-.7-1.34-1.24z" />
    </svg>
  );
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

// ── Marketing Platform Config ──

const MARKETING_PLATFORMS: {
  key: string;
  label: string;
  icon: (props: { className?: string }) => React.ReactNode;
  brandColor: string;
  category: string;
}[] = [
  { key: "facebook", label: "Facebook", icon: FacebookIcon, brandColor: "text-[#1877F2]", category: "Social" },
  { key: "instagram", label: "Instagram", icon: InstagramIcon, brandColor: "text-[#E4405F]", category: "Social" },
  { key: "linkedin", label: "LinkedIn", icon: LinkedInIcon, brandColor: "text-[#0A66C2]", category: "Social" },
  { key: "youtube", label: "YouTube", icon: YouTubeIcon, brandColor: "text-[#FF0000]", category: "Social" },
  { key: "google_analytics", label: "Google Analytics", icon: GoogleIcon, brandColor: "text-[#E37400]", category: "Analytics" },
  { key: "google_search_console", label: "Search Console", icon: GoogleIcon, brandColor: "text-[#4285F4]", category: "Analytics" },
  { key: "google_business_profile", label: "Google Business", icon: GoogleIcon, brandColor: "text-[#4285F4]", category: "Listings" },
  { key: "yelp", label: "Yelp", icon: YelpIcon, brandColor: "text-[#D32323]", category: "Listings" },
];

// ── Main Component ──

export default function MarketingPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const bizId = business?.id ?? "";

  const [accountsOpen, setAccountsOpen] = useState(false);
  const [studioOpen, setStudioOpen] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);

  // Get marketing department + head employee
  const { data: departments } = useQuery({
    queryKey: ["departments", bizId],
    queryFn: () => listDepartments(bizId),
    enabled: !!bizId,
  });

  const marketingDept = departments?.find(
    (d) => d.name.toLowerCase() === "marketing",
  );

  const { data: allEmployees } = useQuery({
    queryKey: ["employees", bizId],
    queryFn: () => listEmployees({ business_id: bizId }),
    enabled: !!bizId,
  });

  const marketingHead = allEmployees?.find(
    (e) => e.department_id === marketingDept?.id && e.is_head,
  );

  // Posts for "last posted" dates
  const { data: postsData } = useQuery({
    queryKey: ["content-posts", bizId],
    queryFn: () => listPosts(bizId, undefined, 100),
    enabled: !!bizId,
  });

  // Build last-posted-per-platform map
  const lastPostedMap = new Map<string, string>();
  for (const post of postsData?.posts ?? []) {
    if (post.status === "posted" && post.posted_at) {
      for (const platform of post.platform_targets) {
        const existing = lastPostedMap.get(platform);
        if (!existing || post.posted_at > existing) {
          lastPostedMap.set(platform, post.posted_at);
        }
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Marketing</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Content publishing, tracking numbers, and campaign attribution
          </p>
        </div>
        <Link
          to="/marketing/reports"
          className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <BarChart3 className="h-4 w-4" />
          Reports
        </Link>
      </div>

      {/* Section 1: Connected Accounts */}
      <CollapsibleSection
        icon={<Link2 size={18} />}
        title="Connected Accounts"
        open={accountsOpen}
        onToggle={() => setAccountsOpen((v) => !v)}
      >
        <ConnectedAccountsSection businessId={bizId} lastPostedMap={lastPostedMap} />
      </CollapsibleSection>

      {/* Section 2: Content Studio */}
      <CollapsibleSection
        icon={<PenLine size={18} />}
        title="Content Studio"
        open={studioOpen}
        onToggle={() => setStudioOpen((v) => !v)}
      >
        <ContentStudioSection businessId={bizId} lastPostedMap={lastPostedMap} />
      </CollapsibleSection>

      {/* Section 3: Chat */}
      <CollapsibleSection
        icon={<MessageSquare size={18} />}
        title="Chat"
        subtitle={marketingHead ? `Talk to ${marketingHead.name}` : undefined}
        open={chatOpen}
        onToggle={() => setChatOpen((v) => !v)}
      >
        {marketingHead ? (
          <ChatSection businessId={bizId} employeeId={marketingHead.id} employeeName={marketingHead.name} />
        ) : (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No marketing department head found.
          </p>
        )}
      </CollapsibleSection>
    </div>
  );
}

// ── Collapsible Section ──

function CollapsibleSection({
  icon,
  title,
  subtitle,
  open,
  onToggle,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-muted/50"
      >
        <span className="flex items-center gap-2.5">
          <span className="text-primary">{icon}</span>
          <span className="font-semibold">{title}</span>
          {subtitle && (
            <span className="text-xs text-muted-foreground">{subtitle}</span>
          )}
        </span>
        <ChevronDown
          size={16}
          className={cn(
            "text-muted-foreground transition-transform duration-200",
            open && "rotate-180",
          )}
        />
      </button>
      {open && <div className="border-t border-border px-5 py-5">{children}</div>}
    </div>
  );
}

// ── Content Studio Section ──

function ContentStudioSection({
  businessId,
  lastPostedMap,
}: {
  businessId: string;
  lastPostedMap: Map<string, string>;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Local state
  const [postContent, setPostContent] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<string>>(new Set());
  const [selectedMediaIds, setSelectedMediaIds] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);

  // Queries
  const { data: connections } = useQuery({
    queryKey: ["platform-connections", businessId],
    queryFn: () => listConnections(businessId),
    enabled: !!businessId,
  });

  const { data: mediaData, isLoading: mediaLoading } = useQuery({
    queryKey: ["media-files", businessId],
    queryFn: () => listMedia(businessId),
    enabled: !!businessId,
  });

  const { data: postsData, isLoading: postsLoading } = useQuery({
    queryKey: ["content-posts", businessId],
    queryFn: () => listPosts(businessId),
    enabled: !!businessId,
  });

  const connectedPlatforms = new Set((connections ?? []).map((c) => c.platform));

  // Mutations
  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadMedia(businessId, file),
    onSuccess: (media) => {
      queryClient.invalidateQueries({ queryKey: ["media-files"] });
      setSelectedMediaIds((prev) => [...prev, media.id]);
    },
  });

  const createPostMut = useMutation({
    mutationFn: (data: { content: string; platforms: string[]; mediaIds: string[] }) =>
      createPost(businessId, {
        content: data.content,
        platform_targets: data.platforms,
        media_ids: data.mediaIds,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["content-posts"] });
      setPostContent("");
      setSelectedPlatforms(new Set());
      setSelectedMediaIds([]);
    },
  });

  const deletePostMut = useMutation({
    mutationFn: (postId: string) => deletePost(businessId, postId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["content-posts"] }),
  });

  const deleteMediaMut = useMutation({
    mutationFn: (mediaId: string) => deleteMedia(businessId, mediaId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["media-files"] }),
  });

  // Handlers
  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        if (file.size > 10 * 1024 * 1024) continue;
        if (!file.type.startsWith("image/")) continue;
        uploadMut.mutate(file);
      }
    },
    [uploadMut],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const togglePlatform = (key: string) => {
    setSelectedPlatforms((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleMediaSelection = (id: string) => {
    setSelectedMediaIds((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id],
    );
  };

  const handleSaveDraft = () => {
    if (!postContent.trim()) return;
    createPostMut.mutate({
      content: postContent.trim(),
      platforms: Array.from(selectedPlatforms),
      mediaIds: selectedMediaIds,
    });
  };

  const media = mediaData?.files ?? [];
  const posts = postsData?.posts ?? [];

  return (
    <div className="space-y-6">
      {/* Compose */}
      <div>
        <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Compose your post
        </label>
        <textarea
          value={postContent}
          onChange={(e) => setPostContent(e.target.value)}
          placeholder="What do you want to share?"
          rows={4}
          maxLength={5000}
          className="w-full rounded-lg border border-border bg-background px-4 py-3 text-sm outline-none transition-colors focus:border-primary resize-none"
        />
        <p className="mt-1 text-right text-[10px] text-muted-foreground">
          {postContent.length}/5000
        </p>
      </div>

      {/* Image Upload */}
      <div>
        <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Attach Images
        </label>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 transition-colors",
            dragOver
              ? "border-primary bg-primary/5"
              : "border-border hover:border-muted-foreground/40 hover:bg-muted/30",
          )}
        >
          {uploadMut.isPending ? (
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          ) : (
            <Upload size={20} className="text-muted-foreground" />
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            Drag & drop or click to upload
          </p>
          <p className="text-[10px] text-muted-foreground/60">
            JPG, PNG, GIF, WebP — max 10 MB
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
      </div>

      {/* Selected images preview */}
      {selectedMediaIds.length > 0 && (
        <div>
          <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Attached ({selectedMediaIds.length})
          </label>
          <div className="flex flex-wrap gap-2">
            {selectedMediaIds.map((id) => {
              const mf = media.find((m) => m.id === id);
              return (
                <div key={id} className="group relative h-16 w-16 overflow-hidden rounded-md border border-border">
                  <img
                    src={mediaFileUrl(businessId, id)}
                    alt={mf?.filename ?? ""}
                    className="h-full w-full object-cover"
                  />
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleMediaSelection(id);
                    }}
                    className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100"
                  >
                    <X size={14} className="text-white" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Media Library */}
      {media.length > 0 && (
        <div>
          <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Media Library
          </label>
          <div className="grid grid-cols-6 gap-2 sm:grid-cols-8 lg:grid-cols-10">
            {media.map((mf) => {
              const isSelected = selectedMediaIds.includes(mf.id);
              return (
                <div
                  key={mf.id}
                  className="group relative"
                >
                  <button
                    type="button"
                    onClick={() => toggleMediaSelection(mf.id)}
                    className={cn(
                      "relative h-16 w-full overflow-hidden rounded-md border-2 transition-all",
                      isSelected
                        ? "border-primary ring-1 ring-primary"
                        : "border-transparent hover:border-muted-foreground/30",
                    )}
                  >
                    <img
                      src={mediaFileUrl(businessId, mf.id)}
                      alt={mf.filename}
                      className="h-full w-full object-cover"
                    />
                    {isSelected && (
                      <div className="absolute right-0.5 top-0.5 rounded-full bg-primary p-0.5">
                        <CheckCircle2 size={10} className="text-primary-foreground" />
                      </div>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteMediaMut.mutate(mf.id)}
                    className="absolute -right-1 -top-1 hidden rounded-full bg-destructive p-0.5 text-destructive-foreground group-hover:block"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Platform selector */}
      <div>
        <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Post to
        </label>
        {connectedPlatforms.size === 0 ? (
          <p className="text-xs text-muted-foreground">
            No connected accounts. Connect platforms in the section above.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {MARKETING_PLATFORMS.filter((p) => connectedPlatforms.has(p.key)).map(
              ({ key, label, icon: Icon, brandColor }) => {
                const isSelected = selectedPlatforms.has(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => togglePlatform(key)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                      isSelected
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:bg-muted/50",
                    )}
                  >
                    <Icon className={cn("h-3.5 w-3.5", isSelected ? "text-primary" : brandColor)} />
                    {label}
                  </button>
                );
              },
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSaveDraft}
          disabled={!postContent.trim() || createPostMut.isPending}
          className={cn(
            "flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors",
            postContent.trim() && !createPostMut.isPending
              ? "bg-primary text-primary-foreground hover:bg-primary/90"
              : "bg-muted text-muted-foreground cursor-not-allowed",
          )}
        >
          {createPostMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <ImagePlus size={14} />
          )}
          Save Draft
        </button>
        <p className="text-[10px] text-muted-foreground">
          Use Chat below to ask the marketing head to publish your drafts.
        </p>
      </div>

      {/* Recent Posts */}
      {posts.length > 0 && (
        <div>
          <label className="mb-2 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Recent Posts
          </label>
          <div className="space-y-1.5">
            {posts.slice(0, 10).map((post) => (
              <div
                key={post.id}
                className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5 transition-colors hover:bg-muted/30"
              >
                <PostStatusIcon status={post.status} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{post.content}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {post.platform_targets.length > 0 && (
                      <span className="text-[10px] text-muted-foreground">
                        {post.platform_targets.join(", ")}
                      </span>
                    )}
                    {post.media_ids.length > 0 && (
                      <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                        <FileImage size={9} />
                        {post.media_ids.length}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(post.created_at).toLocaleDateString()}
                  </span>
                  {post.status === "draft" && (
                    <button
                      type="button"
                      onClick={() => deletePostMut.mutate(post.id)}
                      className="rounded p-1 text-muted-foreground/50 transition-colors hover:bg-destructive/10 hover:text-destructive"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PostStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "posted":
      return <CheckCircle2 size={14} className="shrink-0 text-emerald-500" />;
    case "failed":
      return <XCircle size={14} className="shrink-0 text-destructive" />;
    default:
      return <Clock size={14} className="shrink-0 text-amber-500" />;
  }
}

// ── Chat Section ──

function ChatSection({
  businessId,
  employeeId,
  employeeName,
}: {
  businessId: string;
  employeeId: string;
  employeeName: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const mutation = useMutation({
    mutationFn: (userMessage: string) =>
      sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages,
        user_message: userMessage,
      }),
    onSuccess: (data, userMessage) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: userMessage },
        { role: "assistant", content: data.content },
      ]);
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, mutation.isPending]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || mutation.isPending) return;
    setInput("");
    mutation.mutate(trimmed);
  };

  return (
    <div className="flex flex-col">
      {/* Messages */}
      <div ref={scrollRef} className="max-h-96 min-h-[200px] overflow-y-auto space-y-3 mb-4">
        {messages.length === 0 && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <MessageSquare size={20} className="text-primary" />
            </div>
            <p className="text-sm font-medium">Chat with {employeeName}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Ask about campaigns, SEO, content ideas, or tell them to publish your drafts.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex",
              msg.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            <div
              className={cn(
                "max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted",
              )}
            >
              {msg.role === "assistant" && (
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {employeeName}
                </p>
              )}
              {msg.role === "assistant" ? (
                <MarkdownMessage content={msg.content} />
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {mutation.isPending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-2.5">
              <Loader2 size={14} className="animate-spin text-muted-foreground" />
              <span className="text-xs text-muted-foreground">{employeeName} is thinking...</span>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex items-center gap-2 border-t border-border pt-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder={`Message ${employeeName}...`}
          disabled={mutation.isPending}
          className="flex-1 rounded-lg border border-border bg-background px-4 py-2.5 text-sm outline-none transition-colors focus:border-primary"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending}
          className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg transition-colors",
            input.trim() && !mutation.isPending
              ? "bg-primary text-primary-foreground hover:bg-primary/90"
              : "bg-muted text-muted-foreground cursor-not-allowed",
          )}
        >
          <Send size={16} />
        </button>
      </div>

      {mutation.isError && (
        <p className="mt-2 text-xs text-destructive">
          {mutation.error instanceof Error ? mutation.error.message : "Failed to send message"}
        </p>
      )}
    </div>
  );
}

// ── Connected Accounts Section ──

function ConnectedAccountsSection({
  businessId,
  lastPostedMap,
}: {
  businessId: string;
  lastPostedMap: Map<string, string>;
}) {
  const { data: connections, isLoading } = useQuery({
    queryKey: ["platform-connections", businessId],
    queryFn: () => listConnections(businessId),
    enabled: !!businessId,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const connectedMap = new Map<string, PlatformConnection>();
  for (const conn of connections ?? []) {
    connectedMap.set(conn.platform, conn);
  }

  const categories = new Map<string, typeof MARKETING_PLATFORMS>();
  for (const platform of MARKETING_PLATFORMS) {
    if (!categories.has(platform.category)) categories.set(platform.category, []);
    categories.get(platform.category)!.push(platform);
  }

  return (
    <div className="space-y-5">
      {Array.from(categories.entries()).map(([category, platforms]) => (
        <div key={category}>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {category}
          </p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {platforms.map(({ key, label, icon: Icon, brandColor }) => {
              const connected = connectedMap.get(key);
              const lastPosted = lastPostedMap.get(key);
              return (
                <div
                  key={key}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors",
                    connected
                      ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-800 dark:bg-emerald-900/10"
                      : "border-border bg-card hover:bg-muted/30",
                  )}
                >
                  <Icon className={cn("h-5 w-5 shrink-0", connected ? "text-emerald-600" : brandColor)} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{label}</p>
                    {connected ? (
                      <p className="text-[10px] text-emerald-600 dark:text-emerald-400">
                        Connected
                        {lastPosted && (
                          <span className="text-muted-foreground ml-1">
                            · Last post: {new Date(lastPosted).toLocaleDateString()}
                          </span>
                        )}
                      </p>
                    ) : (
                      <p className="text-[10px] text-muted-foreground">Not connected</p>
                    )}
                  </div>
                  {connected ? (
                    <CheckCircle2 size={14} className="shrink-0 text-emerald-500" />
                  ) : (
                    <Plus size={14} className="shrink-0 text-muted-foreground" />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
