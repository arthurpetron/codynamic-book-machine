import { useCallback, useEffect, useMemo, useState } from "react";
import { fallbackState, getElectronApi } from "../api/electronApi";
import type { BookAppState, CompileResult, DocumentStyle, SectionPayload } from "../api/types";

export type WorkspaceTab = "editor" | "agents" | "references";
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
  const [state, setState] = useState<BookAppState>(fallbackState);
  const [selectedId, setSelectedId] = useState<string | null>(fallbackState.selectedId ?? null);
  const [selectedSection, setSelectedSection] = useState<SectionPayload | null>(fallbackState.selectedSection ?? null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("editor");
  const [styles, setStyles] = useState<DocumentStyle[]>(fallbackState.styles ?? []);
  const [compileResult, setCompileResult] = useState<CompileResult | null>(fallbackState.compile ?? null);
  const [isCompilingBook, setIsCompilingBook] = useState(false);
  const [isCompilingSection, setIsCompilingSection] = useState(false);
  const [compileHistory, setCompileHistory] = useState<CompileHistoryItem[]>([]);
  const [activityMessages, setActivityMessages] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const addActivity = useCallback((source: string, text: string) => {
    const nextMessage = `${source} --> book: ${text}`;
    setActivityMessages((messages) => [nextMessage, ...messages].slice(0, 20));
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
    try {
      const snapshot = await api.app.state(nextSelectedId ?? selectedId);
      setState(snapshot);
      setSelectedId(snapshot.selectedId ?? nextSelectedId ?? null);
      setSelectedSection(snapshot.selectedSection ?? null);
      setCompileResult(snapshot.compile ?? null);
    } catch (error) {
      addActivity("Desktop -> Book", `Failed to load app state: ${(error as Error).message}`);
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
    const result = await api.app.importOutline(mode);
    if (!result) {
      return;
    }
    addActivity("Importer -> Outline", result.output || `Imported outline from ${result.sourcePath}.`);
    await loadState(null);
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
    if (!api.typeset) {
      return;
    }
    const result = await api.typeset.setStyle(styleId, state.bookRoot);
    addActivity("Document Design -> Typeset", result.output || `Document style set to ${styleId}.`);
    await loadState(selectedId);
  }, [api, state.bookRoot, selectedId, loadState, addActivity]);

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
    isLoading,
    setActiveTab,
    loadState,
    selectSection,
    saveSection,
    createSection,
    createChapter,
    updateOutlineNode,
    importOutline,
    compileSection,
    compileBook,
    requestReview,
    reviewProposal,
    reviseProposal,
    setDocumentStyle,
    addActivity
  };
}
