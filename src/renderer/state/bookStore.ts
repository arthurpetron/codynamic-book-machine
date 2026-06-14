import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fallbackState, getElectronApi } from "../api/electronApi";
import type { BookAppState, CompileResult, DocumentStyle, HypervisorPhase, SectionPayload } from "../api/types";

export type WorkspaceTab = "editor" | "agents" | "references";
export type SectionAgentRunState = "working" | "idle";
export interface CompileHistoryItem {
  id: string;
  target: "section" | "book";
  status: string;
  pdfPath?: string;
  errors: number;
  createdAt: string;
}

export function useBookStore() {
  const api = useMemo(() => getElectronApi(), []);
  const hasNativeApi = typeof window !== "undefined" && Boolean(window.cbm);
  const [state, setState] = useState<BookAppState>(fallbackState);
  const [selectedId, setSelectedId] = useState<string | null>(hasNativeApi ? null : (fallbackState.selectedId ?? null));
  const [selectedSection, setSelectedSection] = useState<SectionPayload | null>(hasNativeApi ? null : (fallbackState.selectedSection ?? null));
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("editor");
  const [styles, setStyles] = useState<DocumentStyle[]>(fallbackState.styles ?? []);
  const [compileResult, setCompileResult] = useState<CompileResult | null>(fallbackState.compile ?? null);
  const [isCompilingBook, setIsCompilingBook] = useState(false);
  const [isCompilingSection, setIsCompilingSection] = useState(false);
  const [compileHistory, setCompileHistory] = useState<CompileHistoryItem[]>([]);
  const [activityMessages, setActivityMessages] = useState<string[]>([]);
  const [sectionAgentRunState, setSectionAgentRunState] = useState<Record<string, SectionAgentRunState>>({});
  const [hypervisorEnabled, setHypervisorEnabled] = useState(false);
  const [isHypervisorWorking, setIsHypervisorWorking] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const hypervisorEnabledRef = useRef(false);
  const hypervisorHandledSectionIdsRef = useRef<Set<string>>(new Set());
  const hypervisorPhaseRef = useRef<HypervisorPhase>("draft");
  const hypervisorRevisionQueueRef = useRef<string[]>([]);
  const isHypervisorWorkingRef = useRef(false);

  const addActivity = useCallback((source: string, text: string) => {
    const normalized = source.includes("->")
      ? source.split("->").map((part) => part.trim()).filter(Boolean)
      : [];
    const fromAgent = normalized[0] || source.trim() || "desktop_app";
    const toAgent = normalized[1] || "book";
    const nextMessage = `${fromAgent} --> ${toAgent}: ${text}`;
    setActivityMessages((messages) => [...messages, nextMessage].slice(-20));
  }, []);

  const recordCompile = useCallback((target: "section" | "book", result: CompileResult) => {
    setCompileHistory((history) => [{
      id: `${target}-${Date.now()}`,
      target,
      status: result.status ?? "unknown",
      pdfPath: result.pdf_path,
      errors: result.errors?.length ?? 0,
      createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    }, ...history].slice(0, 8));
  }, []);

  const loadState = useCallback(async (nextSelectedId?: string | null) => {
    setIsLoading(true);
    const requestedSelectedId = nextSelectedId ?? selectedId;
    try {
      const snapshot = await api.app.state(requestedSelectedId);
      setState(snapshot);
      setSelectedId(snapshot.selectedId ?? nextSelectedId ?? null);
      setSelectedSection(snapshot.selectedSection ?? null);
      setCompileResult(snapshot.compile ?? null);
    } catch (error) {
      const message = (error as Error).message || "";
      if (requestedSelectedId && message.includes("Unknown section id")) {
        try {
          const snapshot = await api.app.state(null);
          setState(snapshot);
          setSelectedId(snapshot.selectedId ?? null);
          setSelectedSection(snapshot.selectedSection ?? null);
          setCompileResult(snapshot.compile ?? null);
          addActivity("Desktop -> Book", `Recovered from stale section id: ${requestedSelectedId}.`);
        } catch (retryError) {
          addActivity("Desktop -> Book", `Failed to recover app state: ${(retryError as Error).message}`);
        }
      } else {
        addActivity("Desktop -> Book", `Failed to load app state: ${message}`);
      }
    } finally {
      setIsLoading(false);
    }
  }, [api, selectedId, addActivity]);

  const selectSection = useCallback(async (sectionId: string) => {
    setSelectedId(sectionId);
    try {
      const section = await api.app.section(sectionId);
      setSelectedSection(section);
    } catch (error) {
      addActivity("Desktop -> Book", `Failed to load section: ${(error as Error).message}`);
    }
  }, [api, addActivity]);

  const saveSection = useCallback(async (content: string) => {
    if (!selectedId) {
      return;
    }
    try {
      const section = await api.app.saveSection(selectedId, content);
      setSelectedSection(section);
      addActivity("Editor -> Book", `Saved ${selectedId}.`);
    } catch (error) {
      addActivity("Editor -> Book", `Save failed: ${(error as Error).message}`);
    }
  }, [api, selectedId, addActivity]);

  const startSectionAgent = useCallback(async (sectionId?: string) => {
    const targetId = sectionId ?? selectedId;
    if (!targetId) {
      return;
    }
    setSectionAgentRunState((states) => ({ ...states, [targetId]: "working" }));
    try {
      addActivity("Section Agent -> Book", `Planning next tasks for ${targetId}.`);
      const result = await api.app.startSectionAgent(targetId);
      if (targetId === selectedId) {
        setSelectedSection(result.section);
      }
      addActivity("Section Agent -> Book", `Queued an introspective action plan for ${targetId}.`);
      setSectionAgentRunState((states) => ({ ...states, [targetId]: "idle" }));
      await loadState(targetId);
    } catch (error) {
      addActivity("Section Agent -> Book", `Section agent failed: ${(error as Error).message}`);
      setSectionAgentRunState((states) => ({ ...states, [targetId]: "idle" }));
      throw error;
    }
  }, [api, selectedId, loadState, addActivity]);

  const nextHypervisorTarget = useCallback((excluded: Set<string> = new Set()) => {
    const items = state.outline.flatMap((chapter) => chapter.items ?? []);
    const includeIds = hypervisorPhaseRef.current === "revision"
      ? new Set(hypervisorRevisionQueueRef.current)
      : null;
    const candidates = items.filter((item) => !excluded.has(item.id) && (!includeIds || includeIds.has(item.id)));
    if (!candidates.length) {
      return undefined;
    }
    return candidates.find((item) => item.score == null)?.id
      ?? [...candidates].sort((left, right) => (left.score ?? 0) - (right.score ?? 0))[0]?.id;
  }, [state.outline]);

  const runHypervisorCycle = useCallback(async () => {
    if (!hypervisorEnabledRef.current || isHypervisorWorkingRef.current) {
      return;
    }
    isHypervisorWorkingRef.current = true;
    setIsHypervisorWorking(true);
    try {
      while (hypervisorEnabledRef.current) {
        const excluded = hypervisorHandledSectionIdsRef.current;
        let targetId: string | undefined = nextHypervisorTarget(excluded);

        if (!targetId) {
          if (hypervisorPhaseRef.current === "draft") {
            addActivity("Hypervisor -> Book", "Draft pass complete. Reviewing assembled document for revision targets.");
            const review = await api.app.reviewHypervisorDocument(5);
            hypervisorRevisionQueueRef.current = review.selectedSectionIds ?? [];
            if (hypervisorRevisionQueueRef.current.length > 0) {
              hypervisorPhaseRef.current = "revision";
              hypervisorHandledSectionIdsRef.current = new Set();
              addActivity("Hypervisor -> Book", `Revision pass queued for ${hypervisorRevisionQueueRef.current.length} section(s).`);
              continue;
            }
          }
          hypervisorEnabledRef.current = false;
          setHypervisorEnabled(false);
          addActivity("Hypervisor -> Book", "Hypervisor completed all queued draft and revision work.");
          break;
        }

        setSelectedId(targetId);
        setSectionAgentRunState((states) => ({ ...states, [targetId as string]: "working" }));
        api.app.section(targetId)
          .then(setSelectedSection)
          .catch((error) => addActivity("Hypervisor -> Book", `Failed to preselect ${targetId}: ${(error as Error).message}`));

        const phase = hypervisorPhaseRef.current;
        addActivity("Hypervisor -> Book", `Dispatching ${phase} section-agent pass for ${targetId}.`);
        const result = await api.app.runHypervisor({
          excludeSectionIds: [...excluded],
          includeSectionIds: hypervisorRevisionQueueRef.current,
          phase,
        });

        if (result.phase === "compile_repair") {
          setSectionAgentRunState((states) => ({ ...states, [targetId as string]: "idle" }));
          const repairCount = result.executedRepairs?.length ?? 0;
          const retryStatus = result.retryCompile?.status;
          const responsible = result.retryCompile?.responsible_section_titles?.length
            ? result.retryCompile.responsible_section_titles.join(", ")
            : result.retryCompile?.responsible_section_ids?.join(", ");
          const repairMessage = repairCount > 0
            ? `Processed urgent compile failure, ran ${repairCount} repair task(s)${retryStatus ? `, retry ${retryStatus}` : ""}${responsible ? `; responsible section(s): ${responsible}` : ""}.`
            : "Processed urgent compile failure, but no responsible section repair task was available.";
          addActivity("Hypervisor -> Typeset", repairMessage);
          await loadState(selectedId);
          continue;
        }

        if (result.complete || !result.targetSectionId) {
          setSectionAgentRunState((states) => ({ ...states, [targetId as string]: "idle" }));
          if (phase === "draft") {
            addActivity("Hypervisor -> Book", "Draft pass complete. Reviewing assembled document for revision targets.");
            const review = await api.app.reviewHypervisorDocument(5);
            hypervisorRevisionQueueRef.current = review.selectedSectionIds ?? [];
            if (hypervisorRevisionQueueRef.current.length > 0) {
              hypervisorPhaseRef.current = "revision";
              hypervisorHandledSectionIdsRef.current = new Set();
              addActivity("Hypervisor -> Book", `Revision pass queued for ${hypervisorRevisionQueueRef.current.length} section(s).`);
              continue;
            }
          }
          hypervisorEnabledRef.current = false;
          setHypervisorEnabled(false);
          addActivity("Hypervisor -> Book", "Hypervisor completed all queued draft and revision work.");
          break;
        }

        if (result.targetSectionId !== targetId) {
          setSectionAgentRunState((states) => ({ ...states, [targetId as string]: "idle", [result.targetSectionId as string]: "working" }));
          targetId = result.targetSectionId;
        }
        excluded.add(result.targetSectionId);
        if (result.sectionAgent?.section) {
          setSelectedSection(result.sectionAgent.section);
        }
        addActivity("Hypervisor -> Book", `Completed ${phase} section-agent pass for ${result.targetSectionId}.`);
        await loadState(result.targetSectionId);
        setSectionAgentRunState((states) => ({ ...states, [targetId as string]: "idle" }));
      }
    } catch (error) {
      addActivity("Hypervisor -> Book", `Hypervisor failed: ${(error as Error).message}`);
      hypervisorEnabledRef.current = false;
      setHypervisorEnabled(false);
    } finally {
      isHypervisorWorkingRef.current = false;
      setIsHypervisorWorking(false);
    }
  }, [api, loadState, addActivity, nextHypervisorTarget]);

  const toggleHypervisor = useCallback(() => {
    const nextEnabled = !hypervisorEnabled;
    hypervisorEnabledRef.current = nextEnabled;
    setHypervisorEnabled(nextEnabled);
    if (!nextEnabled) {
      addActivity("Hypervisor -> Book", "Hypervisor disabled.");
      return;
    }
    hypervisorHandledSectionIdsRef.current = new Set();
    hypervisorPhaseRef.current = "draft";
    hypervisorRevisionQueueRef.current = [];
    addActivity("Hypervisor -> Book", "Hypervisor enabled. It will draft all sections once, review the assembled document, then revise a selected subset.");
  }, [hypervisorEnabled, addActivity]);

  const createSection = useCallback(async (parentId: string | undefined, title: string) => {
    const section = await api.app.createSection(parentId, title);
    addActivity("Outline -> Book", `Created ${section.title}.`);
    await loadState(section.id);
    setActiveTab("editor");
  }, [api, loadState, addActivity]);

  const createChapter = useCallback(async (title: string) => {
    await api.app.createChapter(title);
    addActivity("Outline -> Book", `Created chapter ${title}.`);
    await loadState(null);
  }, [api, loadState, addActivity]);

  const updateOutlineNode = useCallback(async (nodeId: string, title: string) => {
    await api.app.updateOutlineNode(nodeId, title);
    addActivity("Outline -> Book", `Renamed outline node to ${title}.`);
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  const importOutline = useCallback(async (mode: "current" | "new") => {
    try {
      const result = await api.app.importOutline(mode);
      if (!result) {
        return;
      }
      const output = result.output || `Imported outline from ${result.sourcePath}.`;
      addActivity("Importer -> Outline", output);
      if (!output.toLowerCase().startsWith("import failed:")) {
        await loadState(null);
      }
    } catch (error) {
      addActivity("Importer -> Outline", `Import failed: ${(error as Error).message}`);
    }
  }, [api, loadState, addActivity]);

  const createVersionFromOutline = useCallback(async () => {
    try {
      const result = await api.app.createVersionFromOutline();
      if (result.error) {
        addActivity("Library -> Book", `Version creation failed: ${result.error}`);
        return;
      }
      addActivity("Library -> Book", result.message || `Created clean version ${result.record?.book_id ?? ""} from outline.`);
      await loadState(null);
    } catch (error) {
      addActivity("Library -> Book", `Version creation failed: ${(error as Error).message}`);
    }
  }, [api, loadState, addActivity]);

  const compileSection = useCallback(async (content: string) => {
    if (!selectedId) {
      return;
    }
    setIsCompilingSection(true);
    setCompileResult({ status: "compiling" });
    await api.app.saveSection(selectedId, content);
    try {
      const result = await api.app.compileSection(selectedId);
      addActivity("Typeset -> Preview", `Section compile ${result.status ?? "finished"}.`);
      await loadState(selectedId);
      setCompileResult(result);
      recordCompile("section", result);
    } catch (error) {
      const result = { status: "failed", errors: [(error as Error).message] };
      setCompileResult(result);
      recordCompile("section", result);
      addActivity("Typeset -> Preview", `Section compile failed: ${(error as Error).message}`);
    } finally {
      setIsCompilingSection(false);
    }
  }, [api, selectedId, loadState, addActivity, recordCompile]);

  const compileBook = useCallback(async () => {
    setIsCompilingBook(true);
    setCompileResult({ status: "compiling" });
    addActivity("Typeset -> Preview", "Book compile started.");
    try {
      const result = await api.app.compileBook();
      addActivity("Typeset -> Preview", `Book compile ${result.status ?? "finished"}.`);
      await loadState(selectedId);
      setCompileResult(result);
      recordCompile("book", result);
    } catch (error) {
      const result = { status: "failed", errors: [(error as Error).message] };
      setCompileResult(result);
      recordCompile("book", result);
      addActivity("Typeset -> Preview", `Book compile failed: ${(error as Error).message}`);
    } finally {
      setIsCompilingBook(false);
    }
  }, [api, selectedId, loadState, addActivity, recordCompile]);

  const requestReview = useCallback(async () => {
    await api.app.requestReview("book");
    addActivity("Operator -> Hypervisor", "Full review requested across outline, drafts, dependencies, and PDF compile state.");
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  const reviewProposal = useCallback(async (proposalId: string, action: "accept" | "reject") => {
    if (action === "accept") {
      await api.app.acceptProposal(proposalId, "Accepted from proposal review.");
    } else {
      await api.app.rejectProposal(proposalId, "Rejected from proposal review.");
    }
    addActivity("Proposal Review -> Book", `${action === "accept" ? "Accepted" : "Rejected"} ${proposalId}.`);
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  const reviseProposal = useCallback(async (proposalId: string, content: string) => {
    await api.app.reviseProposal(proposalId, content, "Revised from proposal review.");
    addActivity("Proposal Review -> Book", `Revised ${proposalId}.`);
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  const setDocumentStyle = useCallback(async (styleId: string) => {
    const settings = await api.app.updateDesignSettings({ style_id: styleId });
    setState((current) => ({ ...current, design: settings }));
    addActivity("Document Design -> Typeset", `Document style set to ${styleId}.`);
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  const updateDesignSettings = useCallback(async (updates: Record<string, string | number | boolean>) => {
    const settings = await api.app.updateDesignSettings(updates);
    setState((current) => ({ ...current, design: settings }));
    addActivity("Document Design -> Typeset", "Updated document settings.");
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  useEffect(() => {
    loadState(null);
    api.typeset?.styles().then(setStyles).catch((error) => {
      addActivity("Document Design -> Typeset", `Failed to load styles: ${(error as Error).message}`);
    });
    api.app.onBookChanged(({ bookId }) => {
      addActivity("Library -> Book", `Opened ${bookId}.`);
      loadState(null);
    });
    api.app.onLibraryMessage(({ message }) => addActivity("Library -> Book", message));
  }, []);

  useEffect(() => {
    if (hypervisorEnabled && !isHypervisorWorking) {
      const timer = window.setTimeout(() => {
        void runHypervisorCycle();
      }, 350);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, [hypervisorEnabled, isHypervisorWorking, runHypervisorCycle]);

  return {
    api,
    state,
    selectedId,
    selectedSection,
    activeTab,
    styles,
    compileResult,
    isCompilingBook,
    isCompilingSection,
    compileHistory,
    activityMessages,
    sectionAgentRunState,
    hypervisorEnabled,
    isHypervisorWorking,
    isLoading,
    setActiveTab,
    loadState,
    selectSection,
    saveSection,
    startSectionAgent,
    toggleHypervisor,
    createSection,
    createChapter,
    updateOutlineNode,
    importOutline,
    createVersionFromOutline,
    compileSection,
    compileBook,
    requestReview,
    reviewProposal,
    reviseProposal,
    setDocumentStyle,
    updateDesignSettings,
    addActivity
  };
}
