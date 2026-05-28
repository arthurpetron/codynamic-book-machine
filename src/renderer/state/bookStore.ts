import { useCallback, useEffect, useMemo, useState } from "react";
import { fallbackState, getElectronApi } from "../api/electronApi";
import type { BookAppState, CompileResult, DocumentStyle, SectionPayload } from "../api/types";

export type WorkspaceTab = "editor" | "agents" | "references";

export function useBookStore() {
  const api = useMemo(() => getElectronApi(), []);
  const [state, setState] = useState<BookAppState>(fallbackState);
  const [selectedId, setSelectedId] = useState<string | null>(fallbackState.selectedId ?? null);
  const [selectedSection, setSelectedSection] = useState<SectionPayload | null>(fallbackState.selectedSection ?? null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("editor");
  const [styles, setStyles] = useState<DocumentStyle[]>(fallbackState.styles ?? []);
  const [compileResult, setCompileResult] = useState<CompileResult | null>(fallbackState.compile ?? null);
  const [isCompilingBook, setIsCompilingBook] = useState(false);
  const [activityMessages, setActivityMessages] = useState<[string, string, string][]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const addActivity = useCallback((source: string, text: string) => {
    const nextMessage: [string, string, string] = ["now", source, text];
    setActivityMessages((messages) => [nextMessage, ...messages].slice(0, 20));
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

  const compileSection = useCallback(async (content: string) => {
    if (!selectedId) {
      return;
    }
    await api.app.saveSection(selectedId, content);
    const result = await api.app.compileSection(selectedId);
    setCompileResult(result);
    addActivity("Typeset -> Preview", `Compile ${result.status ?? "finished"}.`);
    await loadState(selectedId);
  }, [api, selectedId, loadState, addActivity]);

  const compileBook = useCallback(async () => {
    setIsCompilingBook(true);
    try {
      const result = await api.app.compileBook();
      setCompileResult(result);
      addActivity("Typeset -> Preview", `Book compile ${result.status ?? "finished"}.`);
      await loadState(selectedId);
    } catch (error) {
      addActivity("Typeset -> Preview", `Book compile failed: ${(error as Error).message}`);
    } finally {
      setIsCompilingBook(false);
    }
  }, [api, selectedId, loadState, addActivity]);

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
    activityMessages,
    isLoading,
    setActiveTab,
    loadState,
    selectSection,
    saveSection,
    createSection,
    compileSection,
    compileBook,
    requestReview,
    reviewProposal,
    setDocumentStyle,
    addActivity
  };
}
